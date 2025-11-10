#!/usr/bin/env bash

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_PATH="${PROJECT_ROOT}/.venv"
APP_EXEC="${VENV_PATH}/bin/midas"

if [[ ! -x "${APP_EXEC}" ]]; then
  echo "Error: ${APP_EXEC} not found."
  echo "Create the virtual environment and install dependencies first:"
  echo "  python3 -m venv .venv"
  echo "  .venv/bin/pip install -U pip"
  echo "  .venv/bin/pip install -e ."
  exit 1
fi

exec "${APP_EXEC}" "$@"

