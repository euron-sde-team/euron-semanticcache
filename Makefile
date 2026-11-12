# Euron SemanticCache: developer entry points. `make` lists every target.
SHELL := /usr/bin/env bash
.DEFAULT_GOAL := help

COMPOSE_DIR := deploy/compose
FLOCI       := docker compose -f $(COMPOSE_DIR)/compose.yaml -f $(COMPOSE_DIR)/compose.floci.yaml
VENV        := .venv
PY          := $(VENV)/bin/python
TF_IMAGE    := hashicorp/terraform:1.16.6
TF_ENVS     := local-floci aws-dev aws-prod
TEST_REDIS_PORT ?= 6391
export SC_TEST_REDIS_URL ?= redis://localhost:$(TEST_REDIS_PORT)/15

.PHONY: help install env up down logs ps key demo e2e e2e-chaos e2e-browser screenshots test test-console \
        lint typecheck build tf-fmt tf-validate test-redis openapi clean

help: ## Show this help
	@awk 'BEGIN {FS = ":.*##"; printf "\nUsage: make \033[36m<target>\033[0m\n\n"} /^[a-zA-Z0-9_-]+:.*##/ { printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2 }' $(MAKEFILE_LIST)

install: ## Create the virtualenv and install Python and console dependencies
	python3 -m venv $(VENV)
	$(VENV)/bin/pip install -q --upgrade pip
	$(VENV)/bin/pip install -q -e packages/core -e apps/api -e apps/mock-llm \
	  pytest pytest-asyncio pytest-cov httpx ruff mypy boto3 pyyaml pillow
	corepack enable && pnpm install

env: ## Generate deploy/compose/.env with random local-only secrets
	@scripts/gen-local-env.sh

up: env ## Start the full stack on emulated AWS (Floci): Terraform, Redis, mock LLM, 2 API replicas, console
	$(FLOCI) up -d --build
	@echo "console http://localhost:3100   api http://localhost:8180/docs   mock-llm http://localhost:8190   floci http://localhost:4666"

down: ## Stop the stack and delete its volumes
	-$(FLOCI) down -v --remove-orphans

logs: ## Tail logs (SERVICE=api|api-replica|mock-llm|console|...)
	$(FLOCI) logs -f --tail 100 $(SERVICE)

ps: ## Show stack status
	$(FLOCI) ps

key: ## Create a new all-scopes API key (printed once); NAMESPACE=acme binds it to one tenant
	@$(FLOCI) exec -T api semanticcache-api keys:create --name cli --scopes '*' $(if $(NAMESPACE),--namespace $(NAMESPACE),)

demo: ## Send a realistic mix of repeated and paraphrased questions through the running stack
	@$(PY) scripts/demo/seed.py

e2e: ## Full-stack end-to-end assertions against the running stack
	@$(PY) scripts/demo/e2e.py

e2e-chaos: ## Adversarial e2e: load, restarts, a downed provider, tenant isolation, replica coherence
	@$(PY) scripts/demo/e2e_chaos.py

e2e-browser: ## Chromium browser QA with Playwright against the running stack
	pnpm --filter @semanticcache/e2e exec playwright install chromium
	pnpm e2e

screenshots: ## Regenerate README screenshots and the tour GIF (stack must be up and seeded)
	pnpm --filter @semanticcache/e2e exec playwright install chromium
	pnpm --filter @semanticcache/e2e screenshots
	$(PY) scripts/demo/make_tour_gif.py

test-redis: ## Start the throwaway Redis used by the test suite (port $(TEST_REDIS_PORT))
	@docker inspect sc-test-redis >/dev/null 2>&1 || docker run -d --name sc-test-redis -p $(TEST_REDIS_PORT):6379 redis:7.4-alpine >/dev/null
	@docker start sc-test-redis >/dev/null 2>&1 || true

test: test-redis ## Python unit and integration tests (needs Docker for Redis)
	$(PY) -m pytest packages/core
	$(PY) -m pytest apps/api
	$(PY) -m pytest apps/mock-llm

test-console: ## Console unit tests
	pnpm console:test

lint: ## Ruff and ESLint
	$(VENV)/bin/ruff check .
	$(VENV)/bin/ruff format --check .
	pnpm console:lint

typecheck: ## mypy (strict) and tsc
	$(VENV)/bin/mypy packages/core
	$(VENV)/bin/mypy apps/api
	$(VENV)/bin/mypy apps/mock-llm
	pnpm console:typecheck

build: ## Build the console and the Docker images
	pnpm console:build
	docker compose -f $(COMPOSE_DIR)/compose.yaml build

openapi: ## Regenerate docs/api/openapi.yaml from the FastAPI app
	$(PY) scripts/gen_openapi.py

tf-fmt: ## Format Terraform
	docker run --rm -v $(CURDIR)/infra/terraform:/infra -w /infra $(TF_IMAGE) fmt -recursive

tf-validate: ## terraform validate for every environment (no credentials needed)
	@for e in $(TF_ENVS); do echo "== $$e"; \
	  docker run --rm --entrypoint sh -e TF_PLUGIN_CACHE_DIR=/plugin-cache -v sc-tfplugins:/plugin-cache -v $(CURDIR)/infra/terraform:/infra -w /infra/envs/$$e $(TF_IMAGE) \
	    -c "terraform init -backend=false -input=false -no-color >/dev/null && terraform validate -no-color" || exit 1; done

clean: ## Remove build output and caches
	rm -rf apps/console/.next apps/console/node_modules/.cache .pytest_cache .ruff_cache .mypy_cache
