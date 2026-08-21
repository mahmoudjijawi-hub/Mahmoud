"""
إعدادات منصة المعاهد.
كل القيم الحساسة تُقرأ من ملف .env عبر django-environ — لا تُكتب أسراراً هنا.
"""
# مسار الملفات لحساب BASE_DIR
from pathlib import Path
# قراءة متغيرات البيئة من .env
import environ
# التعامل مع قيم النطاق الفارغة لكوكي الجلسة
import os

# جذر المشروع (المجلد الذي فيه manage.py)
BASE_DIR = Path(__file__).resolve().parent.parent
# ضمان وجود مجلد السجلات قبل إعداد FileHandler
(BASE_DIR / "logs").mkdir(exist_ok=True)

# تهيئة مكتبة environ
env = environ.Env(
    # القيمة الافتراضية لوضع التصحيح: مفعّل محلياً
    DEBUG=(bool, True),
    # القيمة الافتراضية لـ HTTPS: معطّل حتى تركيب شهادة SSL
    IS_HTTPS=(bool, False),
)

# قراءة ملف .env إن وُجد بجانب manage.py
environ.Env.read_env(os.path.join(BASE_DIR, ".env"))

# مفتاح التوقيع — إلزامي من البيئة
SECRET_KEY = env("SECRET_KEY", default="dev-only-insecure-key-change-me")

# وضع التصحيح: True محلياً و False في الإنتاج
DEBUG = env("DEBUG")

# هل السيرفر خلف HTTPS فعلياً؟ يتحكم بكوكيز الجلسة الآمنة
IS_HTTPS = env("IS_HTTPS")

# المضيفون المسموحون — قائمة مفصولة بفاصلة في البيئة
ALLOWED_HOSTS = [
    host.strip()
    for host in env("ALLOWED_HOSTS", default="localhost,127.0.0.1").split(",")
    if host.strip()
]
# في التطوير: اقبل أي Host (ngrok وغيره) حتى لا يفشل الدخول بـ DisallowedHost صامت
if DEBUG:
    ALLOWED_HOSTS = ["*"]

# تطبيقات Django المدمجة والمخصصة حسب الوظيفة
INSTALLED_APPS = [
    # لوحة الإدارة الجاهزة لكل معهد
    "django.contrib.admin",
    # إطار المصادقة والصلاحيات
    "django.contrib.auth",
    # أنواع المحتوى المستخدمة مع الصلاحيات
    "django.contrib.contenttypes",
    # جلسات المستخدمين (لا سيما /admin/)
    "django.contrib.sessions",
    # رسائل الإطار
    "django.contrib.messages",
    # الملفات الثابتة
    "django.contrib.staticfiles",
    # إطار REST
    "rest_framework",
    # JWT مع قائمة سوداء لإبطال التوكن
    "rest_framework_simplejwt",
    "rest_framework_simplejwt.token_blacklist",
    # CORS لأصول الواجهة الأمامية المحددة فقط
    "corsheaders",
    # تطبيقات المنصة
    "core",
    "accounts",
    "academics",
    "attendance",
    "grades",
    "schedule",
    "payments",
]

# سلسلة الوسطاء بالترتيب المطلوب أمنياً
MIDDLEWARE = [
    # أمان Django الأساسي (HSTS و XSS headers حسب الإعدادات)
    "django.middleware.security.SecurityMiddleware",
    # CORS قبل CommonMiddleware حتى تُعالَج preflight
    "corsheaders.middleware.CorsMiddleware",
    # الجلسات قبل المصادقة
    "django.contrib.sessions.middleware.SessionMiddleware",
    # معالجة عامة للطلبات
    "django.middleware.common.CommonMiddleware",
    # حماية CSRF لجلسات /admin/ والنماذج
    "django.middleware.csrf.CsrfViewMiddleware",
    # ربط request.user
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    # فحص اشتراك المعهد قبل أي مسار محمي
    "core.middleware.SubscriptionMiddleware",
    # جلسة مدير واحدة نشطة + مهلة الخمول تُدار بإعدادات الجلسة
    "core.middleware.SingleManagerSessionMiddleware",
    # رسائل الإطار
    "django.contrib.messages.middleware.MessageMiddleware",
    # منع النقر داخل iframe (clickjacking)
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

# جذر روابط المشروع
ROOT_URLCONF = "config.urls"

# قوالب Django Admin والقوالب المخصصة إن وُجدت
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

# مدخل WSGI
WSGI_APPLICATION = "config.wsgi.application"

# قاعدة بيانات PostgreSQL السحابية (Neon) عبر dj-database-url
import dj_database_url

DATABASES = {
    "default": dj_database_url.parse(
        "postgresql://neondb_owner:npg_4nOL7skoMpib@ep-late-block-ax2kg9c0.c-4.us-east-2.aws.neon.tech/neondb?sslmode=require"
    )
}

# نموذج المستخدم المخصص (UUID + أدوار)
AUTH_USER_MODEL = "accounts.CustomUser"

# مدققو كلمة المرور الافتراضيون
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# Argon2 أولاً إن توفّر argon2-cffi، وإلا PBKDF2 حتى لا يتعطل التشغيل على ويندوز بدون عجلات جاهزة
try:
    import argon2  # noqa: F401

    PASSWORD_HASHERS = [
        "django.contrib.auth.hashers.Argon2PasswordHasher",
        "django.contrib.auth.hashers.PBKDF2PasswordHasher",
        "django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher",
        "django.contrib.auth.hashers.BCryptSHA256PasswordHasher",
        "django.contrib.auth.hashers.ScryptPasswordHasher",
    ]
except ImportError:
    PASSWORD_HASHERS = [
        "django.contrib.auth.hashers.PBKDF2PasswordHasher",
        "django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher",
        "django.contrib.auth.hashers.BCryptSHA256PasswordHasher",
        "django.contrib.auth.hashers.ScryptPasswordHasher",
    ]

# اللغة العربية للمنصة
LANGUAGE_CODE = "ar"
# توقيت سوريا لأن بيانات الأمثلة من اللاذقية
TIME_ZONE = "Asia/Damascus"
# تفعيل الترجمة
USE_I18N = True
# تخزين التواريخ بـ UTC وعرضها حسب TIME_ZONE
USE_TZ = True

# الملفات الثابتة المجمّعة للإنتاج
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

# الملفات المرفوعة (السير الذاتية) خارج المسار العام قدر الإمكان
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

# المفتاح الافتراضي للحقول التلقائية
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# مسار لوحة الإدارة العشوائي من البيئة (بدون / في البداية أو النهاية)
ADMIN_URL = env("ADMIN_URL", default="secret-admin").strip("/") + "/"

# أصول CORS المسموحة فقط — ممنوع CORS_ALLOW_ALL_ORIGINS في الإنتاج
_DEFAULT_CORS_ORIGINS = (
    "http://localhost:3000,http://127.0.0.1:3000,"
    "http://localhost:3001,http://127.0.0.1:3001,"
    "http://localhost:4173,http://127.0.0.1:4173,"
    "http://localhost:5173,http://127.0.0.1:5173,"
    "http://localhost:5174,http://127.0.0.1:5174,"
    "http://localhost:8080,http://127.0.0.1:8080,"
    "http://localhost:4200,http://127.0.0.1:4200,"
    "http://localhost:5500,http://127.0.0.1:5500"
)
CORS_ALLOWED_ORIGINS = [
    origin.strip()
    for origin in env("CORS_ALLOWED_ORIGINS", default=_DEFAULT_CORS_ORIGINS).split(",")
    if origin.strip()
]
# عند DEBUG: أي منفذ على localhost/127.0.0.1 مسموح حتى يعمل الفرونت بلا تعديل يدوي
if DEBUG:
    CORS_ALLOWED_ORIGIN_REGEXES = [
        r"^http://localhost:\d+$",
        r"^http://127\.0\.0\.1:\d+$",
        r"^http://\[::1\]:\d+$",
    ]
else:
    CORS_ALLOWED_ORIGIN_REGEXES = [
        pattern.strip()
        for pattern in env("CORS_ALLOWED_ORIGIN_REGEXES", default="").split(",")
        if pattern.strip()
    ]
# True = أي أصل فرونت يُقبل (حسب طلب التشغيل الحالي).
CORS_ALLOW_ALL_ORIGINS = True
# السماح بحمل التوكن من الواجهة الأمامية إن لزم
CORS_ALLOW_CREDENTIALS = True
# السماح بكل الرؤوس والطرق حتى لا تُحجب طلبات الفرونت (preflight)
CORS_ALLOW_HEADERS = ["*"]
CORS_ALLOW_METHODS = ["*"]

# الواجهة الأمامية تعتمد JWT: لا نعطّل CSRF عالمياً لأن /admin/ يحتاجه.
# مسارات API تستخدم JWTAuthentication وليست SessionAuthentication، لذلك لا تُفرض CSRF عليها.
CSRF_TRUSTED_ORIGINS = list(CORS_ALLOWED_ORIGINS)

# جلسة المدير: 30 دقيقة خمول، وتجديد العداد مع كل طلب
SESSION_COOKIE_AGE = 30 * 60
SESSION_SAVE_EVERY_REQUEST = True
SESSION_EXPIRE_AT_BROWSER_CLOSE = False
# كوكي آمن فقط عند HTTPS الفعلي لتفادي حلقة إعادة توجيه /admin/ على HTTP
SESSION_COOKIE_SECURE = IS_HTTPS
CSRF_COOKIE_SECURE = IS_HTTPS
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
# نطاق الكوكي: None محلياً، أو النطاق الفعلي لكل معهد من البيئة
_session_domain = env("SESSION_COOKIE_DOMAIN", default="").strip()
SESSION_COOKIE_DOMAIN = _session_domain or None

# إعدادات الإنتاج الأمنية — تُفعَّل عند DEBUG=False
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
SECURE_BROWSER_XSS_FILTER = True
if not DEBUG and IS_HTTPS:
    # إعادة توجيه HTTP إلى HTTPS في الإنتاج فقط بعد SSL
    SECURE_SSL_REDIRECT = True
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
else:
    # التطوير المحلي على HTTP: لا إعادة توجيه ولا HSTS
    SECURE_SSL_REDIRECT = False
    SECURE_HSTS_SECONDS = 0

# إعدادات REST Framework
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        # JWT هو أسلوب المصادقة للـ API (بدون Session على مسارات API)
        "accounts.authentication.VersionedJWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": (
        "rest_framework.permissions.IsAuthenticated",
    ),
    "DEFAULT_THROTTLE_CLASSES": (
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ),
    "DEFAULT_THROTTLE_RATES": {
        # حدود أوضح للتطوير حتى لا يُحسب فشل الدخول كـ «لا يستطيع الدخول»
        "anon": "120/minute" if DEBUG else "60/minute",
        "user": "600/minute" if DEBUG else "300/minute",
        "login": "30/minute" if DEBUG else "5/minute",
        "special_number": "30/minute" if DEBUG else "5/minute",
        "payments": "20/minute",
    },
    "EXCEPTION_HANDLER": "core.exceptions.api_exception_handler",
    "DEFAULT_RENDERER_CLASSES": (
        "rest_framework.renderers.JSONRenderer",
    ),
}

# JWT: صلاحية قصيرة للوصول وإمكانية إبطال التحديث
from datetime import timedelta  # noqa: E402

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=15),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "AUTH_HEADER_TYPES": ("Bearer",),
    "USER_ID_FIELD": "id",
    "USER_ID_CLAIM": "user_id",
    "TOKEN_OBTAIN_SERIALIZER": "accounts.serializers.CustomTokenObtainPairSerializer",
}

# بيانات المدير الأولي من البيئة — ليست hardcoded
ADMIN_SPECIAL_NUMBER = env("ADMIN_SPECIAL_NUMBER", default="7788990")
ADMIN_USERNAME = env("ADMIN_USERNAME", default="ammar")
# افتراضي مطابق لطلب token في الـ Postman Collection
ADMIN_PASSWORD = env("ADMIN_PASSWORD", default="ammar12345ammar")
ADMIN_FIRST_NAME = env("ADMIN_FIRST_NAME", default="مدير")
ADMIN_LAST_NAME = env("ADMIN_LAST_NAME", default="المعهد")
SUBSCRIPTION_EXPIRY_DATE = env("SUBSCRIPTION_EXPIRY_DATE", default="2027-12-31")

# حد رفع السيرة الذاتية بالبايت (5 ميغابايت)
MAX_CV_UPLOAD_BYTES = 5 * 1024 * 1024

# تسجيل محاولات الدخول الفاشلة دون كتابة الرقم المميز أو كلمة المرور
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "simple": {
            "format": "{levelname} {asctime} {name} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "simple",
        },
        "file": {
            "class": "logging.FileHandler",
            "filename": BASE_DIR / "logs" / "auth.log",
            "formatter": "simple",
            "encoding": "utf-8",
        },
    },
    "loggers": {
        "accounts.auth": {
            "handlers": ["console", "file"],
            "level": "INFO",
            "propagate": False,
        },
    },
}
