# Running it — ports, stopping, remote hosts

The everyday path is in the [README](../README.md): `./scripts/start.sh`, then
http://127.0.0.1:8501. This file holds what you need only when a port is taken, when a server is
still running after you thought you stopped it, or when the box is not the one in front of you.

## Ports

Both ports are overridable:

```bash
API_PORT=8080 UI_PORT=8600 ./scripts/start.sh
```

## Stopping

```bash
./scripts/start.sh --stop
```

This frees the ports **by port, not just by pidfile**, so it also clears an API or UI that was
started by hand with `make api` / `make ui` in another terminal. Postgres keeps running — stop it
with `make down`.

To run the pieces separately instead, `make api` and `make ui` still work in two terminals. Every
target runs from the repository root; the Makefile handles the `cd backend`.

## Running on a remote box

The `127.0.0.1` URLs — and the `0.0.0.0` / `localhost` ones Streamlit prints — only work in a
browser *on the server itself*. `0.0.0.0` is a bind address meaning "listen on every interface",
not a destination you can visit; from your laptop both it and `localhost` point at your laptop,
where nothing is running.

Use the server's own address instead (`http://<server-ip>:8501`). **On EC2 the script detects that
address for you** — it asks the instance metadata service for the public IPv4 and prints a
`from your own browser:` URL alongside the local ones. That URL still needs port 8501 open in the
instance's security group. Anywhere else (or behind a proxy, or with a DNS name you prefer), set
`PUBLIC_HOST=<server-ip-or-hostname>` yourself and it is used as-is.

The **API binds to localhost only** and is not reachable that way. That is deliberate: it has no
auth, and every `/chat` call spends a metered key. The Streamlit page calls the API from the server
side, so the UI works regardless. To hit the API yourself, tunnel it:

```bash
ssh -L 8000:127.0.0.1:8000 <user>@<server>
```
