.PHONY: help up down logs psql install migrate revision api test lint fmt
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

test:  ## pytest
	cd $(BACKEND) && $(UV) run pytest

lint:  ## ruff + mypy
	cd $(BACKEND) && $(UV) run ruff check . && $(UV) run mypy app
	cd $(BACKEND) && $(UV) run ruff format --check .

fmt:  ## ruff format + autofix
	cd $(BACKEND) && $(UV) run ruff format . && $(UV) run ruff check --fix .
