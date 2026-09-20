COMPOSE_FILE := docker-compose.yml
COMPOSE := docker compose -f $(COMPOSE_FILE)
FRONTEND_DIR := ../frontend
# nvm-managed node is not on make's restricted PATH; resolve npm dynamically
# from whatever shell invoked make (e.g. after `nvm use`). Override with
# `make frontend-dev NPM_BIN=/path/to/npm` if it can't be found this way.
NPM_BIN ?= $(shell command -v npm 2>/dev/null)
NPM := $(NPM_BIN) --prefix $(FRONTEND_DIR)

VENV := .venv
PY := $(VENV)/bin/python
UVICORN := $(VENV)/bin/uvicorn
DEV_COMPOSE := docker compose -f docker-compose.yml -f docker-compose.dev.yml

.PHONY: help check up up-build down clean logs ps health \
        logs-calfire logs-noaa logs-all logs-mcp logs-recommendation \
        stream-fire stream-weather stream-recommendations \
        context topics mcp-server ingest sms sms-replay test \
        check-npm frontend-install frontend-dev frontend-build frontend-start frontend-lint \
        check-venv dev-venv dev-infra dev-down dev-api dev-calfire dev-noaa dev-recommendation

help:
	@echo "Available targets:"
	@echo "  make check          Verify Docker and Docker Compose are installed"
	@echo "  make up             Start all containers"
	@echo "  make up-build       Build and start all containers"
	@echo "  make down           Stop all containers"
	@echo "  make clean          Stop, remove volumes (wipes SQLite) and orphans"
	@echo "  make ps             Show container status"
	@echo "  make health         Check the backend health endpoint"
	@echo ""
	@echo "  make logs           Follow backend logs"
	@echo "  make logs-calfire   Follow CAL FIRE producer logs"
	@echo "  make logs-noaa      Follow NOAA producer logs"
	@echo "  make logs-all       Follow all container logs"
	@echo ""
	@echo "  make stream-fire    Live Kafka stream: firelink.fire"
	@echo "  make stream-weather Live Kafka stream: firelink.weather"
	@echo "  make context        Fetch /context/latest (pretty-printed JSON)"
	@echo "  make topics         List all Kafka topics"
	@echo "  make logs-mcp            Follow MCP server logs"
	@echo "  make logs-recommendation Follow recommendation agent logs"
	@echo "  make stream-recommendations Live Kafka stream: firelink.recommendations"
	@echo "  make mcp-server          Run FastMCP context server locally (stdio transport)"
	@echo "  make ingest              One-shot ingest of docs/*.pdf into Pinecone"
	@echo "  make sms                 Interactive SMS simulator (talks to /sms/inbound)"
	@echo "  make sms-replay          Batch-replay sms_test_cases.json through the Help Agent"
	@echo "  make test                Smoke-test running stack (make + REST + Help Agent)"
	@echo ""
	@echo "  make frontend-install    Install Next.js dependencies (npm install)"
	@echo "  make frontend-dev        Run Next.js dev server (port 3000)"
	@echo "  make frontend-build      Production build of the Next.js app"
	@echo "  make frontend-start      Run the production Next.js server"
	@echo "  make frontend-lint       Run eslint on the frontend"
	@echo ""
	@echo "Local development (Docker infra + host venv):"
	@echo "  make dev-venv            Create backend/.venv and install requirements.txt"
	@echo "  make dev-infra           Start zookeeper + kafka only (host listener :29092)"
	@echo "  make dev-down            Stop Docker infra"
	@echo "  make dev-api             Run FastAPI locally with uvicorn --reload (:8000)"
	@echo "  make dev-calfire         Run CAL FIRE producer locally"
	@echo "  make dev-noaa            Run NOAA producer locally"
	@echo "  make dev-recommendation  Run recommendation agent locally"

check:
	@command -v docker >/dev/null 2>&1 || { echo "Docker is not installed or not on PATH."; exit 1; }
	@docker compose version >/dev/null 2>&1 || { echo "Docker Compose v2 is not available."; exit 1; }
	@echo "Docker and Docker Compose are available."

up:
	$(COMPOSE) up

up-build:
	$(COMPOSE) up --build

down:
	$(COMPOSE) down

clean:
	$(COMPOSE) down -v --remove-orphans

logs:
	$(COMPOSE) logs -f backend

ps:
	$(COMPOSE) ps

health:
	$(COMPOSE) exec backend python -c "import urllib.request; print(urllib.request.urlopen('http://localhost:8000/health').read().decode())"

logs-calfire:
	$(COMPOSE) logs -f calfire-producer

logs-noaa:
	$(COMPOSE) logs -f noaa-producer

logs-all:
	$(COMPOSE) logs -f

logs-mcp:
	$(COMPOSE) logs -f mcp-server

logs-recommendation:
	$(COMPOSE) logs -f recommendation-agent

stream-fire:
	docker exec firelink-kafka kafka-console-consumer \
		--bootstrap-server localhost:9092 \
		--topic firelink.fire \
		--from-beginning

stream-weather:
	docker exec firelink-kafka kafka-console-consumer \
		--bootstrap-server localhost:9092 \
		--topic firelink.weather \
		--from-beginning

stream-recommendations:
	docker exec firelink-kafka kafka-console-consumer \
		--bootstrap-server localhost:9092 \
		--topic firelink.recommendations \
		--from-beginning

context:
	@curl -s http://localhost:8000/context/latest | python3 -m json.tool

topics:
	docker exec firelink-kafka kafka-topics \
		--bootstrap-server localhost:9092 \
		--list

mcp-server: check-venv
	$(VENV)/bin/pip show fastmcp >/dev/null 2>&1 || $(VENV)/bin/pip install -r requirements-mcp.txt
	$(PY) -m app.mcp_server

ingest:
	$(COMPOSE) exec backend python -m app.services.knowledge.ingest

sms:
	@python3 test/sms_cli.py

sms-replay:
	@python3 test/sms_cli.py --batch

test:
	@python3 test/smoke_test.py

check-npm:
	@test -n "$(NPM_BIN)" || { echo "npm not found on PATH. Run 'nvm use' (or otherwise ensure npm is on PATH) before using frontend-* targets, or override: make frontend-dev NPM_BIN=/path/to/npm"; exit 1; }

frontend-install: check-npm
	$(NPM) install

frontend-dev: check-npm
	@test -d $(FRONTEND_DIR)/node_modules || $(NPM) install
	$(NPM) run dev

frontend-build: check-npm
	@test -d $(FRONTEND_DIR)/node_modules || $(NPM) install
	$(NPM) run build

frontend-start: check-npm
	$(NPM) run start

frontend-lint: check-npm
	$(NPM) run lint

check-venv:
	@test -x $(PY) || { echo "backend/.venv not found. Run 'make dev-venv' first."; exit 1; }

# Local development (Docker infra + host venv)
dev-venv:
	python3 -m venv $(VENV)
	$(VENV)/bin/pip install --upgrade pip
	$(VENV)/bin/pip install -r requirements.txt

dev-infra:
	$(DEV_COMPOSE) up -d --wait zookeeper kafka

dev-down:
	$(DEV_COMPOSE) down

dev-api: check-venv
	$(UVICORN) app.main:app --host 0.0.0.0 --port 8000 --reload

dev-calfire: check-venv
	$(PY) -m app.run_producer calfire

dev-noaa: check-venv
	$(PY) -m app.run_producer noaa

dev-recommendation: check-venv
	$(PY) -m app.run_agent recommendation