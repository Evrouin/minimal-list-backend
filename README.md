# Minimal List API

A production-ready REST API built with Django and Django REST Framework. Features JWT authentication, Google OAuth, email verification, note management with soft delete, an admin backoffice, and cursor-based pagination — deployed on Render with a Nuxt.js frontend on Vercel.

**Live API:** https://minimalist-todo-api-luzd.onrender.com  
**Swagger UI:** https://minimalist-todo-api-luzd.onrender.com/api/docs/  
**ReDoc:** https://minimalist-todo-api-luzd.onrender.com/api/redoc/

## Tech Stack

- Python 3.12 / Django 5 / Django REST Framework
- PostgreSQL
- JWT Authentication (SimpleJWT) with token blacklisting
- Google OAuth 2.0
- OpenAPI 3.0 documentation (drf-spectacular)
- Docker & Docker Compose
- Render (production) / Gunicorn

## Features

- **Authentication** — Register, login, JWT refresh, email verification, password reset with 24-hour expiry
- **Google OAuth** — Social login with Google
- **Custom User Model** — Email-based auth with profile fields
- **Note CRUD** — Create, read, update, soft delete, permanent delete, pin, bulk operations
- **Cursor Pagination** — Efficient infinite scroll support
- **Admin Backoffice** — Superuser-only endpoints for managing users and notes with search and pagination
- **Rate Limiting** — Per-endpoint IP-based throttling on auth routes
- **Soft Delete** — Two-stage delete (soft → permanent) with restore capability
- **Modular Settings** — Separate base, development, and production configurations
- **Security Hardened** — HTTPS enforcement, secure cookies, CORS whitelisting in production
- **Code Quality** — Black, Ruff, Flake8, MyPy
- **Unit Tests** — 33 tests covering auth and note endpoints

## API Endpoints

### Authentication
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/auth/register/` | Register new user |
| POST | `/api/auth/login/` | Login (returns JWT tokens) |
| POST | `/api/auth/login/google/` | Google OAuth login |
| POST | `/api/auth/token/refresh/` | Refresh access token |
| POST | `/api/auth/verify-email/<token>/` | Verify email address |
| POST | `/api/auth/password-reset/` | Request password reset |
| POST | `/api/auth/password-reset/confirm/` | Confirm password reset |

### User Profile
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/auth/profile/` | Get profile |
| PATCH | `/api/auth/profile/` | Update profile |
| PUT | `/api/auth/change-password/` | Change password |
| DELETE | `/api/auth/delete-account/` | Delete account |

### Notes
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/notes/` | List notes (cursor paginated) |
| POST | `/api/notes/` | Create note |
| GET | `/api/notes/:id/` | Get note |
| PUT/PATCH | `/api/notes/:id/` | Update note |
| DELETE | `/api/notes/:id/` | Soft delete / permanent delete |
| POST | `/api/notes/bulk-delete/` | Bulk delete |
| POST | `/api/notes/bulk-pin/` | Bulk pin/unpin |

### Admin Backoffice (Superuser)
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/admin/stats/` | Dashboard statistics |
| GET/POST | `/api/admin/users/` | List / create users |
| GET/PATCH/DELETE | `/api/admin/users/:id/` | User detail / update / delete |
| GET | `/api/admin/notes/` | List all notes (searchable) |
| GET/DELETE | `/api/admin/notes/:id/` | Note detail / permanent delete |

## Project Structure

```
├── apps/
│   ├── users/           # Auth, profile, admin backoffice
│   └── notes/           # Note CRUD, pagination, bulk ops
├── config/
│   └── settings/        # base / development / production
├── requirements/        # base / development / production
├── scripts/             # entrypoint, formatting, linting
├── render.yaml          # Render Blueprint (one-click deploy)
├── Dockerfile
└── docker-compose.yml
```

## Getting Started

```bash
cp .env.example .env
docker-compose up --build -d
docker-compose exec web python manage.py migrate
docker-compose exec web python manage.py createsuperuser
```

API available at `http://localhost:8000/api/docs/`

## Running Tests

```bash
docker-compose exec web pytest -v
```

## Deployment

Push to GitHub and connect to Render — the `render.yaml` blueprint provisions a PostgreSQL database and web service automatically. Set the required environment variables (`ALLOWED_HOSTS`, `CORS_ALLOWED_ORIGINS`, `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`) in the Render dashboard.

## License

MIT

## Author

Evrouin
