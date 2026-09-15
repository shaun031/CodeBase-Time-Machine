#!/usr/bin/env sh
set -eu
cd "$(dirname "$0")/../backend"
python -m ruff check .
python -m ruff format --check .
python -m mypy app
if [ "${1:-}" = "--integration" ]; then
  : "${TEST_DATABASE_URL:?Set TEST_DATABASE_URL to a migrated PostgreSQL database}"
  python -m pytest
else
  python -m pytest -m 'not integration'
fi
cd ../frontend
npm run lint
npm run format:check
npm run typecheck
npm test
