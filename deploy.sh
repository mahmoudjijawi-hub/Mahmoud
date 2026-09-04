#!/usr/bin/env bash
# سكربت تحديث نشرة معهد واحدة — يُشغَّل على السيرفر بعد git push للكود المشترك.
set -euo pipefail

# غيّر أمر إعادة التشغيل حسب السيرفر (systemd / supervisor / إلخ)
RESTART_CMD="${RESTART_CMD:-sudo systemctl restart gunicorn}"
# مجلد المشروع على السيرفر
APP_DIR="$(cd "$(dirname "$0")" && pwd)"

cd "$APP_DIR"
# سحب آخر نسخة من المستودع الواحد
git pull
# تفعيل البيئة الافتراضية
# shellcheck disable=SC1091
source .venv/bin/activate
# تثبيت أي متطلبات جديدة
pip install -r requirements.txt
# تطبيق الهجرات على قاعدة هذا المعهد فقط
python manage.py migrate
# جدول قفل الدخول المشترك بين عمال gunicorn (DatabaseCache)
python manage.py createcachetable
# مزامنة كلمة مرور المدير من .env (ضروري حتى ينجح دخول الفرونت)
python manage.py seed_manager
# تجميع الملفات الثابتة
python manage.py collectstatic --noinput
# إعادة تشغيل خدمة التطبيق
eval "$RESTART_CMD"
