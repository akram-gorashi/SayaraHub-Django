#!/bin/sh
set -e
python manage.py migrate --noinput
if [ "${SEED_DEMO_DATA:-false}" = "true" ]; then
  python manage.py seed_demo
fi
exec daphne -b 0.0.0.0 -p 8000 config.asgi:application
