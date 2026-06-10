.PHONY: help up down build migrate test lint clean status

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-15s\033[0m %s\n", $$1, $$2}'

up: ## Start all services
	cd docker && docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d

down: ## Stop all services
	cd docker && docker compose down

build: ## Rebuild all containers
	cd docker && docker compose up -d --build

migrate: ## Run database migrations
	cd docker && docker compose exec backend alembic upgrade head

test: test-backend test-frontend ## Run all tests

test-backend: ## Run backend tests
	cd backend && python -m pytest --tb=short -q

test-frontend: ## Run frontend tests
	cd frontend && npx vitest run

lint: lint-backend lint-frontend ## Run all linters

lint-backend: ## Run backend linter
	cd backend && python -m ruff check app/

lint-frontend: ## Run frontend type check
	cd frontend && npx tsc --noEmit

clean: ## Remove generated files
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	rm -rf backend/.coverage backend/htmlcov

status: ## Show service status
	cd docker && docker compose ps

logs: ## Tail logs (usage: make logs SERVICE=backend)
	cd docker && docker compose logs -f $(SERVICE)
