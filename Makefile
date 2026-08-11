.PHONY: help up down logs psql install migrate revision api ingest find validate eval report test lint fmt
.DEFAULT_GOAL := help

BACKEND := backend
UV := uv

help:  ## show this help
	@grep -hE '^[a-z-]+:.*?## ' $(MAKEFILE_LIST) | awk -F':.*?## ' '{printf "  \033[36m%-10s\033[0m %s\n", $$1, $$2}'

up:  ## start postgres + pgvector, wait until it accepts connections
	docker compose up -d --wait

down:  ## stop containers (the pgdata volume survives)
	docker compose down

logs:  ## tail postgres logs
	docker compose logs -f postgres

psql:  ## open a psql shell in the container
	docker compose exec postgres psql -U $${POSTGRES_USER:-rag} -d $${POSTGRES_DB:-rag}

install:  ## sync the virtualenv from pyproject.toml
	cd $(BACKEND) && $(UV) sync --extra dev

migrate:  ## alembic upgrade head
	cd $(BACKEND) && $(UV) run alembic upgrade head

revision:  ## autogenerate a migration: make revision M="add x"
	cd $(BACKEND) && $(UV) run alembic revision --autogenerate -m "$(M)"

api:  ## run the API with reload
	cd $(BACKEND) && $(UV) run uvicorn app.main:app --reload

ingest:  ## ingest the corpus: make ingest [P=../data/raw] [FORCE=1]
	cd $(BACKEND) && $(UV) run python -m scripts.ingest_corpus --path $(or $(P),../data/raw) $(if $(FORCE),--force,)

find:  ## look up chunk ids for the golden set: make find Q="phụ cấp"
	cd $(BACKEND) && $(UV) run python -m scripts.find_chunks --q "$(Q)"

validate:  ## validate the golden set + the frozen corpus lock
	cd $(BACKEND) && $(UV) run python -m eval.datasets.validate

eval:  ## run a pipeline over the golden set: make eval P=naive-v1 [ARGS="--overwrite"]
	cd $(BACKEND) && $(UV) run python -m eval.runner --pipeline $(or $(P),naive-v1) $(ARGS)

report:  ## rebuild results/leaderboard.md from every results/*.json
	cd $(BACKEND) && $(UV) run python -m eval.report

test:  ## pytest
	cd $(BACKEND) && $(UV) run pytest

lint:  ## ruff + mypy
	cd $(BACKEND) && $(UV) run ruff check . && $(UV) run mypy app eval scripts
	cd $(BACKEND) && $(UV) run ruff format --check .

fmt:  ## ruff format + autofix
	cd $(BACKEND) && $(UV) run ruff format . && $(UV) run ruff check --fix .
