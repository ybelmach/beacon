#!/bin/sh
set -eu

if [ "$#" -gt 0 ]; then
    exec "$@"
fi

set -- uvicorn beacon.main:app \
    --host 0.0.0.0 \
    --port "${BACKEND_INTERNAL_PORT:-8000}"

if [ "${UVICORN_RELOAD:-false}" = "true" ]; then
    set -- "$@" --reload
fi

exec "$@"
