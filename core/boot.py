"""تهيئة النشر: migrate + جدول الـ cache قبل استقبال الطلبات على Render."""
import logging
import os
import sys

logger = logging.getLogger("core.boot")

_PREPARED = False


def _should_skip():
    if os.environ.get("SKIP_RUNTIME_MIGRATE"):
        return True
    argv = " ".join(sys.argv).lower()
    skip_cmds = (
        "migrate",
        "makemigrations",
        "test",
        "collectstatic",
        "shell",
        "createsuperuser",
        "createcachetable",
    )
    return any(cmd in argv for cmd in skip_cmds)


def prepare_runtime():
    """
    يشغّل migrate و createcachetable مرة لكل عملية.
    آمن إن الجدول موجود مسبقاً، ويُستدعى من WSGI/entrypoint حتى لو نُسي أمر البناء.
    """
    global _PREPARED
    if _PREPARED or _should_skip():
        return
    _PREPARED = True
    try:
        from django.core.management import call_command

        call_command("migrate", interactive=False, verbosity=0)
    except Exception:
        logger.exception("migrate failed during boot")
    try:
        from core.admin_login_limit import ensure_cache_table

        ensure_cache_table()
    except Exception:
        logger.exception("createcachetable failed during boot")
        try:
            from django.core.management import call_command

            call_command("createcachetable", verbosity=0)
        except Exception:
            logger.exception("createcachetable retry failed")
