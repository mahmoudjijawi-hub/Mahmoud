# نشر منصة المعاهد (نفس الكود — عدة سيرفرات)

كل معهد نشرة مستقلة: عملية Django خاصة، قاعدة PostgreSQL خاصة، وملف `.env` خاص. الكود واحد على GitHub؛ أي إصلاح أمني يُدفع مرة ثم يُعاد نشره على كل سيرفر. لا تفرّع المستودع لكل معهد.

**تنبيه:** نسيان تحديث أحد السيرفرات يتركه على نسخة قديمة وربما بها ثغرة غير مُصلحة.

**تنبيه كوكيز `/admin/`:** لا تضبط `IS_HTTPS=True` قبل التأكد من تركيب شهادة SSL على السيرفر، وإلا لن تتمكن من تسجيل الدخول للوحة الإدارة نهائياً لأن المتصفح لن يحفظ الكوكي. نسخ رابط اللوحة إلى نافذة تصفح خفي سيطلب دخولاً جديداً دائماً — هذا سلوك جلسة طبيعي وليس خللاً.

## خطوات نشرة معهد جديد (قابلة للتكرار)

1. `git clone` أو `git pull` للمستودع الواحد.
2. إنشاء بيئة افتراضية وتثبيت المتطلبات: `python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt`.
3. نسخ `.env.example` إلى `.env` وتعبئة قيم هذا المعهد: `SECRET_KEY`، بيانات PostgreSQL، `ALLOWED_HOSTS`، `ADMIN_URL` العشوائي، `ADMIN_SPECIAL_NUMBER`، `CORS_ALLOWED_ORIGINS`، و`SESSION_COOKIE_DOMAIN` إن لزم.
4. إنشاء قاعدة بيانات PostgreSQL فارغة خاصة بهذا المعهد.
5. `python manage.py migrate`
6. `python manage.py seed_manager`
7. `python manage.py createsuperuser` لحساب Django Admin الخاص بهذه النشرة (لا يُخزَّن في الكود).
8. `python manage.py collectstatic --noinput`
9. تشغيل التطبيق بـ gunicorn ثم nginx، مع تقييد مسار الإدارة بعنوان IP على مستوى nginx إن أمكن.

مثال تشغيل gunicorn:

```bash
gunicorn config.wsgi:application --bind 127.0.0.1:8000 --workers 3
```

بعد أي تحديث للكود المشترك: ادفع إلى GitHub ثم نفّذ `deploy.sh` يدوياً على **كل** سيرفر معهد.

تمديد أو إيقاف الاشتراك يتم فقط بتعديل `expiry_date` أو `is_active` من Django Admin لهذه النشرة — لا يوجد مسار تجديد داخل الـ API.
