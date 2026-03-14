# Upwork Dashboard

A FastAPI app with user auth, Upwork OAuth2 login, and a job lookup dashboard powered by the Upwork GraphQL API.

## Quick Start

### 1. Install dependencies
```bash
pip install -r requirements.txt
```

### 2. Configure environment
```bash
cp .env.example .env
# Edit .env with your values
```

### 3. Run
```bash
uvicorn main:app --reload
```

Open http://localhost:8000

---

## Project Structure

```
upwork-dashboard/
├── main.py              # FastAPI entry point + static serving
├── database.py          # SQLAlchemy engine + session
├── models.py            # User ORM model
├── schemas.py           # Pydantic request/response schemas
├── auth.py              # JWT + password helpers + get_current_user
├── routers/
│   ├── auth.py          # /api/auth/* (register, login, upwork OAuth)
│   └── jobs.py          # /api/jobs/lookup
├── static/
│   └── index.html       # Full SPA frontend
├── requirements.txt
└── .env.example
```

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/auth/register` | Create account |
| POST | `/api/auth/login` | Get JWT token |
| GET  | `/api/auth/upwork/authorize` | Get Upwork OAuth URL |
| GET  | `/api/auth/upwork/callback` | Upwork OAuth2 callback |
| GET  | `/api/auth/me` | Current user info |
| POST | `/api/jobs/lookup` | Look up job by ID |

Interactive docs: http://localhost:8000/docs

---

## Upwork OAuth2 Setup

1. Go to https://developers.upwork.com/ and create an app
2. Set the callback URL to `http://localhost:8000/api/auth/upwork/callback`
3. Copy Client ID and Secret into your `.env`

### Using a bearer token directly (no OAuth app needed)
Set `UPWORK_BEARER_TOKEN` in `.env` with your token from Postman.
This token will be used as a fallback for users who haven't connected Upwork.

---

## Job Lookup

Post to `/api/jobs/lookup` with:
```json
{ "job_id": "2032480639478701974" }
```

Returns full job details: title, description, budget, skills, team, duration, etc.
