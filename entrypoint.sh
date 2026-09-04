#!/usr/bin/env bash
# نقطة تشغيل Render/gunicorn: يضمن migrate وجدول django_cache قبل فتح المنفذ.
set -euo pipefail
cd "$(dirname "$0")"

python manage.py migrate --noinput
python manage.py createcachetable
# مزامنة حساب المدير من البيئة إن توفرت الجداول
python manage.py seed_manager || true

PORT="${PORT:-8000}"
WORKERS="${WEB_WORKERS:-${WEB_CONCURRENCY:-3}}"
exec gunicorn config.wsgi:application --bind "0.0.0.0:${PORT}" --workers "${WORKERS}"
