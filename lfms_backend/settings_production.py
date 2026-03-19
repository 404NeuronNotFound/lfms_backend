"""
settings_production.py
──────────────────────
Production settings for Render deployment.
In your settings.py, add at the very bottom:

    import os
    if os.environ.get("DJANGO_ENV") == "production":
        from .settings_production import *

Or merge these values directly into your settings.py.
"""

import os
import dj_database_url
from pathlib import Path

# ── Security ──────────────────────────────────────────────────────────────
SECRET_KEY = os.environ["DJANGO_SECRET_KEY"]
DEBUG = False
ALLOWED_HOSTS = [
    os.environ.get("RENDER_EXTERNAL_HOSTNAME", ""),
    "localhost",
    "127.0.0.1",
]

# ── Database — Render PostgreSQL ──────────────────────────────────────────
DATABASES = {
    "default": dj_database_url.config(
        default=os.environ["DATABASE_URL"],
        conn_max_age=600,
        conn_health_checks=True,
    )
}

# ── Static files — WhiteNoise ─────────────────────────────────────────────
MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",   # ← after SecurityMiddleware
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

BASE_DIR = Path(__file__).resolve().parent
STATIC_URL  = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

# ── Media files — served from Render disk or S3 ───────────────────────────
MEDIA_URL  = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

# ── CORS — allow your Vercel frontend ─────────────────────────────────────
CORS_ALLOWED_ORIGINS = [
    os.environ.get("FRONTEND_URL", "https://your-app.vercel.app"),
]
CORS_ALLOW_CREDENTIALS = True
CORS_ALLOW_HEADERS = [
    "authorization",
    "content-type",
    "accept",
    "origin",
    "x-requested-with",
]

# ── Security headers ──────────────────────────────────────────────────────
SECURE_PROXY_SSL_HEADER     = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT         = True
SESSION_COOKIE_SECURE       = True
CSRF_COOKIE_SECURE          = True
SECURE_HSTS_SECONDS         = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True