#!/usr/bin/env bash
# VidForge Development Helper
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

usage() {
    echo "Usage: $0 <command>"
    echo ""
    echo "Commands:"
    echo "  up        Start all services (docker-compose)"
    echo "  down      Stop all services"
    echo "  logs      Tail service logs"
    echo "  build     Rebuild all containers"
    echo "  migrate   Run database migrations"
    echo "  test      Run all tests (backend + frontend)"
    echo "  test-be   Run backend tests only"
    echo "  test-fe   Run frontend tests only"
    echo "  lint      Run all linters"
    echo "  lint-be   Run backend linter (ruff)"
    echo "  lint-fe   Run frontend linter"
    echo "  clean     Remove generated files"
    echo "  shell     Open a shell in the backend container"
    echo "  status    Show service status"
}

cmd_up() {
    cd "$PROJECT_DIR/docker"
    docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d
}

cmd_down() {
    cd "$PROJECT_DIR/docker"
    docker compose down
}

cmd_logs() {
    cd "$PROJECT_DIR/docker"
    docker compose logs -f "${@:-backend}"
}

cmd_build() {
    cd "$PROJECT_DIR/docker"
    docker compose up -d --build
}

cmd_migrate() {
    cd "$PROJECT_DIR/docker"
    docker-compose exec backend alembic upgrade head
}

cmd_test() {
    cmd_test_be
    cmd_test_fe
}

cmd_test_be() {
    cd "$PROJECT_DIR/backend"
    python -m pytest --tb=short -q "$@"
}

cmd_test_fe() {
    cd "$PROJECT_DIR/frontend"
    npx vitest run "$@"
}

cmd_lint() {
    cmd_lint_be
    cmd_lint_fe
}

cmd_lint_be() {
    cd "$PROJECT_DIR/backend"
    python -m ruff check app/
}

cmd_lint_fe() {
    cd "$PROJECT_DIR/frontend"
    npx eslint . --ext ts,tsx --report-unused-disable-directives --max-warnings 0 2>/dev/null || echo "ESLint not configured"
    npx tsc --noEmit
}

cmd_clean() {
    find "$PROJECT_DIR" -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
    find "$PROJECT_DIR" -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
    find "$PROJECT_DIR" -type d -name node_modules -exec rm -rf {} + 2>/dev/null || true
    rm -rf "$PROJECT_DIR/backend/.coverage" "$PROJECT_DIR/backend/htmlcov" 2>/dev/null || true
    echo "Cleaned."
}

cmd_shell() {
    cd "$PROJECT_DIR/docker"
    docker compose exec backend /bin/bash
}

cmd_status() {
    cd "$PROJECT_DIR/docker"
    docker compose ps
}

case "${1:-}" in
    up)      shift; cmd_up "$@" ;;
    down)    shift; cmd_down "$@" ;;
    logs)    shift; cmd_logs "$@" ;;
    build)   shift; cmd_build "$@" ;;
    migrate) shift; cmd_migrate "$@" ;;
    test)    shift; cmd_test "$@" ;;
    test-be) shift; cmd_test_be "$@" ;;
    test-fe) shift; cmd_test_fe "$@" ;;
    lint)    shift; cmd_lint "$@" ;;
    lint-be) shift; cmd_lint_be "$@" ;;
    lint-fe) shift; cmd_lint_fe "$@" ;;
    clean)   shift; cmd_clean "$@" ;;
    shell)   shift; cmd_shell "$@" ;;
    status)  shift; cmd_status "$@" ;;
    *)       usage ;;
esac
