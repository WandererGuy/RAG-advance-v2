#!/usr/bin/env bash
# Start the whole demo stack: postgres -> migrations -> API -> Streamlit UI.
# Usage: ./scripts/start.sh          (starts everything, tails nothing)
#        ./scripts/start.sh --stop   (stops API + UI, leaves postgres up)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

RUN_DIR="$ROOT/.run"
API_PORT="${API_PORT:-8000}"
UI_PORT="${UI_PORT:-8501}"
HEALTH="http://127.0.0.1:$API_PORT/api/v1/health"

stop() {
  for name in api ui; do
    pidfile="$RUN_DIR/$name.pid"
    if [[ -f "$pidfile" ]]; then
      pid="$(cat "$pidfile")"
      if kill -0 "$pid" 2>/dev/null; then
        # uvicorn --reload and streamlit both spawn children; kill the group
        kill -TERM -- "-$(ps -o pgid= "$pid" | tr -d ' ')" 2>/dev/null || kill "$pid" 2>/dev/null || true
        echo "stopped $name (pid $pid)"
      fi
      rm -f "$pidfile"
    fi
  done
  # Servers started by hand (make api / make ui) hold no pidfile here, so clear
  # the ports directly too — otherwise the new API loses the bind and the health
  # check below passes against the *old* process.
  free_port "$API_PORT" api
  free_port "$UI_PORT" ui
}

free_port() {
  local port="$1" label="$2" pids
  pids="$(lsof -t -i ":$port" -sTCP:LISTEN 2>/dev/null || true)"
  [[ -z "$pids" ]] && return 0
  echo "port $port ($label) still held by pid(s) $(echo "$pids" | tr '\n' ' ')— stopping"
  # shellcheck disable=SC2086
  kill -TERM $pids 2>/dev/null || true
  for _ in $(seq 10); do
    lsof -t -i ":$port" -sTCP:LISTEN >/dev/null 2>&1 || return 0
    sleep 0.5
  done
  # shellcheck disable=SC2086
  kill -KILL $pids 2>/dev/null || true
  sleep 1
}

if [[ "${1:-}" == "--stop" ]]; then
  stop
  exit 0
fi

if [[ ! -f .env ]]; then
  echo "no .env at repo root — copy .env.example and fill it in first" >&2
  exit 1
fi

mkdir -p "$RUN_DIR"
stop  # never leave a stale server bound to the port

echo "==> postgres"
make up

echo "==> migrations"
make migrate

echo "==> api (port $API_PORT)"
# Bypasses `make api`, which pins no port — uvicorn would stay on its default 8000
# while the health check below waited on $API_PORT.
setsid env UVICORN_PORT="$API_PORT" \
  sh -c 'cd backend && uv run uvicorn app.main:app --reload --port "$UVICORN_PORT"' \
  >"$RUN_DIR/api.log" 2>&1 &
echo $! >"$RUN_DIR/api.pid"

echo -n "    waiting for $HEALTH "
for _ in $(seq 60); do
  if curl -sf "$HEALTH" >/dev/null 2>&1; then
    echo "ok"
    break
  fi
  if ! kill -0 "$(cat "$RUN_DIR/api.pid")" 2>/dev/null; then
    echo
    echo "api died on startup — last lines of $RUN_DIR/api.log:" >&2
    tail -20 "$RUN_DIR/api.log" >&2
    exit 1
  fi
  echo -n "."
  sleep 1
done

if ! curl -sf "$HEALTH" >/dev/null 2>&1; then
  echo
  echo "api did not become healthy in 60s — see $RUN_DIR/api.log" >&2
  exit 1
fi

echo "==> ui (port $UI_PORT)"
# --server.port is passed through the Makefile's streamlit invocation; without it
# streamlit silently picks the next free port and the URL printed below is wrong.
setsid env STREAMLIT_SERVER_PORT="$UI_PORT" STREAMLIT_SERVER_HEADLESS=true \
  make ui >"$RUN_DIR/ui.log" 2>&1 &
echo $! >"$RUN_DIR/ui.pid"

for _ in $(seq 30); do
  curl -sf -o /dev/null "http://127.0.0.1:$UI_PORT" && break
  sleep 1
done
if ! curl -sf -o /dev/null "http://127.0.0.1:$UI_PORT"; then
  echo "ui did not come up on $UI_PORT — see $RUN_DIR/ui.log" >&2
  tail -20 "$RUN_DIR/ui.log" >&2
  exit 1
fi

cat <<EOF

  API   http://127.0.0.1:$API_PORT/docs
  UI    http://127.0.0.1:$UI_PORT
EOF

# On a remote box those 127.0.0.1 URLs are useless from your own browser — they
# resolve to *your* machine. PUBLIC_HOST is not auto-detected: IMDS is blocked here,
# and a guessed hostname printed as a working URL is worse than none.
if [[ -n "${PUBLIC_HOST:-}" ]]; then
  cat <<EOF

  from your own browser:
  UI    http://$PUBLIC_HOST:$UI_PORT
  (the API stays on localhost — reach it through the UI, or use an SSH tunnel)
EOF
fi

cat <<EOF
  logs  $RUN_DIR/api.log · $RUN_DIR/ui.log
  stop  ./scripts/start.sh --stop
EOF
