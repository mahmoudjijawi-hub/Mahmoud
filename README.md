# منصة المعاهد — Backend Django + DRF

منصة إدارة معاهد تعليمية (واجهة برمجية فقط حالياً) بالعربية. الـ API مطابقة لملف Postman Collection المرفق.

## التشغيل المحلي

1. ثبّت Python 3.12+ وأنشئ بيئة افتراضية:

```bash
python -m venv .venv
# Windows (مثبّت Python الرسمي)
.venv\Scripts\Activate.ps1
# Windows (هذه النسخة مبنية بـ MSYS وقد يكون المفسّر في .venv\bin\python.exe)
.venv\bin\python.exe manage.py runserver
# Linux / macOS
source .venv/bin/activate
```

2. ثبّت المتطلبات:

```bash
pip install -r requirements.txt
```

3. انسخ متغيرات البيئة:

```bash
cp .env.example .env
```

عدّل `.env` (خصوصاً `SECRET_KEY` وبيانات المدير و`ADMIN_URL`).

عند التطوير المحلي يُفضّل `CORS_ALLOW_ALL_ORIGINS=True` حتى يعمل الفرونت من أي عنوان/منفذ فوراً. في الإنتاج عطّله وحدد `CORS_ALLOWED_ORIGINS` بنطاق الفرونت فقط.

بيانات المدير الافتراضية المطابقة للـ Postman: `ammar` / `ammar12345ammar` (بعد `seed_manager`).

4. طبّق الهجرات وازرع المدير الأولي:

```bash
python manage.py migrate
python manage.py seed_manager
python manage.py createsuperuser
```

`createsuperuser` ينشئ حساب لوحة الإدارة وهو **منفصل** عن مدير المعهد الذي يدخل عبر `/api/token/`.

بعد `migrate` شغّل `seed_manager` حتى تُضبط كلمة مرور المدير الأولي (الهجرة تنشئ الحساب، والأمر يضبط كلمة المرور من `.env`).

مشغّل PostgreSQL هو `psycopg` (الإصدار 3). على x86_64 و macOS يُثبَّت `psycopg[binary]` كويل جاهز بلا بناء C، وعلى ARM/Termux تُثبَّت النسخة النقية `psycopg` التي تعتمد على `libpq` من النظام — يتم الاختيار تلقائياً حسب المعمارية داخل `requirements.txt`. إن تعذّر بناء `argon2-cffi` فالمنصة تعمل بـ PBKDF2 تلقائياً.

### التشغيل على Termux (أندرويد)

```bash
pkg install python postgresql libffi clang
pip install -r requirements.txt
```

`libpq` تأتي مع حزمة `postgresql`، وهي كل ما تحتاجه نسخة `psycopg` النقية — لا يوجد بناء لـ `psycopg2` إطلاقاً.

لقاعدة بيانات محلية على الهاتف بدل Neon، اترك `DATABASE_URL` فارغاً واملأ `DB_NAME` و`DB_USER` وبقية متغيرات `DB_*` في `.env`.

قاعدة المشروع **PostgreSQL دائماً**. إن لم يكن المشغّل مثبّتاً يتوقف التطبيق برسالة واضحة تشرح أمر التثبيت، ولا يتحول إلى SQLite صامتاً حتى لا تعمل المنصة على قاعدة فارغة بدل بيانات المعهد. للتجربة المؤقتة على SQLite فقط اضبط `ALLOW_SQLITE_FALLBACK=True`.

5. شغّل خادم التطوير:

```bash
python manage.py runserver
```

القاعدة الافتراضية محلياً هي SQLite. للإنتاج استخدم PostgreSQL عبر متغيرات `DB_*` في `.env`.

## المصادقة

- المدير (خطوتان):
  1. `POST /api/token/` بـ `{"special_number": "7788990"}` → `200` مع `requires_password: true` و`role: "manager"` (بدون توكن) — للانتقال لصفحة كلمة المرور.
  2. `POST /api/token/` بـ `{"username": "ammar", "password": "ammar12345ammar"}` → `200` مع `access`/`refresh`/`token`/`role`/`user`.
- الأستاذ/الطالب: `POST /api/token/` بالجسم `{"special_number": "..."}` فقط → توكن مباشرة.
- التحديث: `POST /api/token/refresh/` بالجسم `{"refresh": "..."}`.
- الرأس: `Authorization: Bearer <access>`.

مدة صلاحية توكن الوصول 15 دقيقة. توكن التحديث يُدار مع القائمة السوداء.

## ملاحظات أمنية مهمة

- لا تفعّل `IS_HTTPS=True` قبل تركيب شهادة SSL، وإلا لن تُحفظ كوكيز جلسة `/admin/` على HTTP وستظهر حلقة إعادة توجيه.
- مسار لوحة الإدارة يأتي من `ADMIN_URL` وليس `/admin/` الافتراضي.
- الملفات المرفوعة للسيرة تُخزَّن تحت `media/private/cvs/` وتُنزَّل عبر مسار محمي للمدير.

## الاختبارات

```bash
python manage.py test
```

## النشر

على Render:
- Build Command: `bash build.sh`
- Start Command: `bash start.sh`

هذان الأمران يشغّلان `migrate` و`createcachetable` تلقائياً. انظر أيضاً `DEPLOYMENT.md` و`deploy.sh`.
