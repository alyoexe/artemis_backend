import os
from datetime import timedelta
from importlib.util import find_spec
from pathlib import Path

import dj_database_url

BASE_DIR = Path(__file__).resolve().parent.parent


def load_env_file(env_path: Path) -> None:
    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("\"'")
        os.environ.setdefault(key, value)


# Env file precedence (first found values win due to setdefault):
# 1) .env.local (developer local overrides)
# 2) .env
# 3) backend.env (legacy/local fallback)
for env_name in (".env.local", ".env", "backend.env"):
    load_env_file(BASE_DIR / env_name)


def env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value.strip())
    except ValueError:
        return default

SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "change-me")
DEBUG = os.getenv("DJANGO_DEBUG", "False").lower() in {"1", "true", "yes"}

ALLOWED_HOSTS = [host.strip() for host in os.getenv("DJANGO_ALLOWED_HOSTS", "*").split(",") if host.strip()]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "rest_framework_simplejwt",
    "ingestion",
]

if find_spec("corsheaders"):
    INSTALLED_APPS.insert(0, "corsheaders")

if find_spec("storages"):
    INSTALLED_APPS.append("storages")

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

if find_spec("corsheaders"):
    MIDDLEWARE.insert(2, "corsheaders.middleware.CorsMiddleware")

ROOT_URLCONF = "config.urls"

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

WSGI_APPLICATION = "config.wsgi.application"

database_url = os.getenv("SUPABASE_DB_URL", "sqlite:///db.sqlite3")

# Supabase "pooler" hostnames are PgBouncer endpoints. In that setup, long-lived
# Django connections can become stale, and server-side cursors can be problematic.
is_supabase_pooler = "pooler.supabase.com" in (database_url or "")

default_conn_max_age = 0 if is_supabase_pooler else 60
conn_max_age = env_int("DJANGO_DB_CONN_MAX_AGE", default_conn_max_age)
database_config = dj_database_url.parse(database_url, conn_max_age=conn_max_age)

# Supabase requires SSL for PostgreSQL connections.
if database_config.get("ENGINE") == "django.db.backends.postgresql":
    database_config.setdefault("OPTIONS", {})["sslmode"] = "require"
    database_config.setdefault("OPTIONS", {}).setdefault("connect_timeout", 10)
    # Avoid stale connections causing intermittent 500s.
    database_config.setdefault("CONN_HEALTH_CHECKS", True)
    if is_supabase_pooler:
        database_config.setdefault("DISABLE_SERVER_SIDE_CURSORS", True)

DATABASES = {"default": database_config}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

SUPABASE_STORAGE_ENABLED = env_bool("SUPABASE_STORAGE_ENABLED", False)
SUPABASE_PROJECT_REF = os.getenv("SUPABASE_PROJECT_REF", "").strip()
SUPABASE_STORAGE_BUCKET = os.getenv("SUPABASE_STORAGE_BUCKET", "technical-documents").strip()
SUPABASE_STORAGE_REGION = os.getenv("SUPABASE_STORAGE_REGION", "us-east-1").strip()
SUPABASE_STORAGE_ACCESS_KEY_ID = os.getenv("SUPABASE_STORAGE_ACCESS_KEY_ID", "").strip()
SUPABASE_STORAGE_SECRET_ACCESS_KEY = os.getenv("SUPABASE_STORAGE_SECRET_ACCESS_KEY", "").strip()
SUPABASE_STORAGE_PUBLIC = env_bool("SUPABASE_STORAGE_PUBLIC", True)
SUPABASE_STORAGE_ENDPOINT_URL = os.getenv("SUPABASE_STORAGE_ENDPOINT_URL", "").strip()
SUPABASE_STORAGE_PUBLIC_BASE_URL = os.getenv("SUPABASE_STORAGE_PUBLIC_BASE_URL", "").strip().rstrip("/")

if not SUPABASE_STORAGE_ENDPOINT_URL and SUPABASE_PROJECT_REF:
    SUPABASE_STORAGE_ENDPOINT_URL = f"https://{SUPABASE_PROJECT_REF}.supabase.co/storage/v1/s3"

if not SUPABASE_STORAGE_PUBLIC_BASE_URL and SUPABASE_PROJECT_REF and SUPABASE_STORAGE_BUCKET:
    SUPABASE_STORAGE_PUBLIC_BASE_URL = (
        f"https://{SUPABASE_PROJECT_REF}.supabase.co/storage/v1/object/public/{SUPABASE_STORAGE_BUCKET}"
    )

if (
    SUPABASE_STORAGE_ENABLED
    and find_spec("storages")
    and SUPABASE_STORAGE_ENDPOINT_URL
    and SUPABASE_STORAGE_BUCKET
    and SUPABASE_STORAGE_ACCESS_KEY_ID
    and SUPABASE_STORAGE_SECRET_ACCESS_KEY
):
    s3_options = {
        "access_key": SUPABASE_STORAGE_ACCESS_KEY_ID,
        "secret_key": SUPABASE_STORAGE_SECRET_ACCESS_KEY,
        "bucket_name": SUPABASE_STORAGE_BUCKET,
        "endpoint_url": SUPABASE_STORAGE_ENDPOINT_URL,
        "region_name": SUPABASE_STORAGE_REGION,
        "default_acl": None,
        "file_overwrite": False,
        "querystring_auth": not SUPABASE_STORAGE_PUBLIC,
    }

    if SUPABASE_STORAGE_PUBLIC and SUPABASE_STORAGE_PUBLIC_BASE_URL:
        s3_options["custom_domain"] = SUPABASE_STORAGE_PUBLIC_BASE_URL.replace("https://", "").replace("http://", "")
        s3_options["url_protocol"] = "https:"

    STORAGES = {
        "default": {
            "BACKEND": "storages.backends.s3.S3Storage",
            "OPTIONS": s3_options,
        },
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
        },
    }

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
AUTH_USER_MODEL = "ingestion.CustomUser"

# Public signup controls
# Field Technicians can always self-register.
# Data Steward self-registration is allowed only when enabled.
DATA_STEWARD_PUBLIC_SIGNUP_ENABLED = env_bool("DATA_STEWARD_PUBLIC_SIGNUP_ENABLED", DEBUG)

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": (
        "rest_framework.permissions.IsAuthenticated",
    ),
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=30),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=1),
    "AUTH_HEADER_TYPES": ("Bearer",),
}

PIPELINE_STATUS_TOKEN = os.getenv("PIPELINE_STATUS_TOKEN", "")

raw_cors_allowed_origins = os.getenv("CORS_ALLOWED_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173")
CORS_ALLOWED_ORIGINS = [origin.strip() for origin in raw_cors_allowed_origins.split(",") if origin.strip()]
