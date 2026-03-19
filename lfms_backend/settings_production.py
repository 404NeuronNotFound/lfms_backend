"""
settings_production.py — imported at bottom of settings.py when DJANGO_ENV=production
"""
import os
import dj_database_url
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# ── Security ──────────────────────────────────────────────────────────────
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "changeme-set-in-render-env")
DEBUG = False

ALLOWED_HOSTS = [
    "lfms-backend.onrender.com",
    os.environ.get("RENDER_EXTERNAL_HOSTNAME", "lfms-backend.onrender.com"),
    "localhost",
    "127.0.0.1",
]

# ── Database — Render PostgreSQL via psycopg3 ─────────────────────────────
DATABASES = {
    "default": dj_database_url.config(
        default=os.environ.get("DATABASE_URL", ""),
        conn_max_age=600,
        conn_health_checks=True,
    )
}

# ── Static files — WhiteNoise ─────────────────────────────────────────────
STATIC_URL  = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

# ── CORS ──────────────────────────────────────────────────────────────────
# Hardcode your Vercel URL + filter out any empty env vars
CORS_ALLOW_ALL_ORIGINS = False
_extra = os.environ.get("FRONTEND_URL", "").strip()
CORS_ALLOWED_ORIGINS = list(filter(None, [
    "https://findify-keybeen.vercel.app",
    _extra if _extra.startswith("http") else "",
]))
CORS_ALLOW_CREDENTIALS = True
CORS_ALLOW_HEADERS = [
    "authorization",
    "content-type",
    "accept",
    "origin",
    "x-requested-with",
]

# ── Security headers ──────────────────────────────────────────────────────
SECURE_PROXY_SSL_HEADER        = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT            = True
SESSION_COOKIE_SECURE          = True
CSRF_COOKIE_SECURE             = True
SECURE_HSTS_SECONDS            = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True