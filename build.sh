#!/usr/bin/env bash
# أمر البناء على Render: تثبيت المتطلبات + migrate + جدول الـ cache + الملفات الثابتة.
set -euo pipefail
cd "$(dirname "$0")"

python -m pip install -r requirements.txt
python manage.py migrate --noinput
python manage.py createcachetable
python manage.py collectstatic --noinput
