# Data Ingestion Backend (Django + DRF)

Backend service for ingestion, storage, metadata management, and role-based access control for technical documents.

Scope included:
- Document upload and storage metadata
- Role-based access control (System Administrator, Data Steward, Field Technician)
- JWT authentication
- Document status lifecycle endpoints

Scope excluded:
- OCR, parsing, extraction, AI processing

## 1. Prerequisites

- Python 3.12+
- PostgreSQL (or Supabase PostgreSQL)

## 2. Setup

1. Create and activate a virtual environment.
2. Install dependencies:

```bash
pip install django djangorestframework djangorestframework-simplejwt dj-database-url psycopg2-binary django-cors-headers django-storages boto3
```

3. Create environment file from template:

```bash
copy .env.example .env
```

4. Update `backend/.env` with your values. Example:

```powershell
DJANGO_SECRET_KEY=your-secret-key
DJANGO_DEBUG=True
DJANGO_ALLOWED_HOSTS=127.0.0.1,localhost
SUPABASE_DB_URL=postgresql://postgres:password@db.project-ref.supabase.co:5432/postgres
PIPELINE_STATUS_TOKEN=your-strong-token
CORS_ALLOWED_ORIGINS=http://localhost:5173,http://127.0.0.1:5173

# Optional: allow Data Steward self-signup (default: enabled when DJANGO_DEBUG=True)
DATA_STEWARD_PUBLIC_SIGNUP_ENABLED=True

# Optional: Supabase Storage (public bucket) for uploaded files
SUPABASE_STORAGE_ENABLED=True
SUPABASE_PROJECT_REF=your-project-ref
SUPABASE_STORAGE_BUCKET=technical-documents
SUPABASE_STORAGE_REGION=us-east-1
SUPABASE_STORAGE_ACCESS_KEY_ID=your-storage-access-key-id
SUPABASE_STORAGE_SECRET_ACCESS_KEY=your-storage-secret-access-key
SUPABASE_STORAGE_PUBLIC=True
```

The Django settings load `backend/.env` automatically when management commands start.

## 3. Database

Run migrations:

```bash
python manage.py makemigrations
python manage.py migrate
```

## 4. Create an Admin User

```bash
python manage.py createsuperuser
```

After creating the user, assign role SYSTEM_ADMINISTRATOR in Django admin or shell.

## 5. Run the API

```bash
python manage.py runserver
```

Base URL: http://127.0.0.1:8000

## 6. Authentication (JWT)

- Obtain tokens: POST /api/auth/token/
- Refresh token: POST /api/auth/token/refresh/

Example token request body:

```json
{
  "username": "admin",
  "password": "your-password"
}
```

## 7. Main Endpoints

- Users (System Administrator only):
  - GET/POST /api/users/
  - GET/PATCH/DELETE /api/users/{id}/

- Documents:
  - POST /api/documents/ (System Administrator, Data Steward)
  - GET /api/documents/
    - System Administrator: all documents
    - Data Steward: only their uploaded documents
    - Field Technician: READY documents only
  - GET /api/documents/{id}/
  - PATCH /api/documents/{id}/status/
    - Allowed for System Administrator JWT users
    - Or external pipeline via X-PIPELINE-TOKEN header

- Lookups:
  - /api/vendors/
  - /api/equipment-categories/

## 8. Notes

- Upload endpoint accepts multipart/form-data.
- Status defaults to UPLOADED on document creation.
- External processing trigger is intentionally left as a TODO in the upload flow.
- If `SUPABASE_STORAGE_ENABLED=True`, uploaded files are stored in Supabase Storage (public bucket mode if `SUPABASE_STORAGE_PUBLIC=True`).

## 9. Deploy on Render

### Option A: Render Blueprint (recommended)

1. Push this repository to GitHub.
2. In Render, click **New** -> **Blueprint**.
3. Select your repository.
4. Render will detect `render.yaml` and create the web service.
5. In the service environment variables, set:
  - `SUPABASE_DB_URL` (or Render PostgreSQL URL)
  - `PIPELINE_STATUS_TOKEN`
  - `CSRF_TRUSTED_ORIGINS` (for example `https://your-service.onrender.com`)
  - `CORS_ALLOWED_ORIGINS` (frontend URLs, comma-separated)
6. Deploy.

### Option B: Manual Web Service Setup

1. In Render, click **New** -> **Web Service** and connect this repo.
2. Configure:
  - **Environment**: `Python`
  - **Build Command**: `pip install -r requirements.txt ; python manage.py migrate ; python manage.py collectstatic --noinput`
  - **Start Command**: `gunicorn config.wsgi:application`
3. Add env vars:
  - `DJANGO_SECRET_KEY=<strong-random-secret>`
  - `DJANGO_DEBUG=False`
  - `DJANGO_ALLOWED_HOSTS=.onrender.com`
  - `SUPABASE_DB_URL=<your-postgres-url>`
  - `PIPELINE_STATUS_TOKEN=<strong-random-token>`
  - `CSRF_TRUSTED_ORIGINS=https://your-service.onrender.com`
  - `CORS_ALLOWED_ORIGINS=https://your-frontend-domain.com`
4. Deploy and test:
  - `GET /api/` or one of your API endpoints
  - `POST /api/auth/token/`

### Important production notes

- Render filesystem is ephemeral. Keep `SUPABASE_STORAGE_ENABLED=True` for persistent uploaded files.
- Do not use SQLite in production. Use PostgreSQL via `SUPABASE_DB_URL` or `DATABASE_URL`.
