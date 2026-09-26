.PHONY: install dev test lint fmt build image

install:
	cd backend && uv sync
	cd frontend && pnpm install

dev:  ## Run everything locally; open http://app-a.localhost:5173
	./scripts/dev.sh

test:
	cd backend && uv run pytest
	cd frontend && pnpm test

lint:
	cd backend && uv run ruff check . && uv run ruff format --check .
	cd frontend && pnpm lint && pnpm typecheck

fmt:
	cd backend && uv run ruff format . && uv run ruff check --fix .

build:
	cd frontend && pnpm build

image:  ## Production image, all actors in one container on :8000
	docker compose up --build lab
