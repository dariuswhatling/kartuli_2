# Kartuli Tutor

A self-hosted Django app for studying Georgian (ქართული). Upload your lesson
PDFs, and an AI tutor parses + categorises them into a searchable knowledge
base, then chats with you, quizzes you, and **adapts to your strengths and
weaknesses** over time.

- **Bring any model** via [OpenRouter](https://openrouter.ai) — pick separate
  models for the chat tutor and for parsing PDFs.
- **Scoped testing** — “quiz me on verbs from lesson 3” only ever pulls from
  lesson 3’s verb content, never unrelated material.
- **Two memories**:
  - a **lesson knowledge base** (parsed chunks + metadata + embeddings), and
  - a **learner profile** (structured mastery scores + [Mem0](https://github.com/mem0ai/mem0)
    self-hosted memory) so the tutor remembers what you’re good/bad at.
- **Clean, minimal light UI.**

## Architecture

```
Upload PDF ─▶ extract text (pypdf) ─▶ chosen OpenRouter model tags & chunks it
          ─▶ OpenAI embeddings ─▶ stored in Postgres

Chat turn  ─▶ scope (lesson/topic) ─▶ retrieve only matching chunks
          ─▶ tutor model answers using ONLY that context
          ─▶ assess your answer ─▶ update mastery scores + Mem0
```

| Concern | Choice |
|---------|--------|
| Web | Django 5 + Gunicorn |
| DB | Postgres (pgvector image; Mem0 uses pgvector) |
| Lesson chat models | OpenRouter (any model) |
| Embeddings | OpenAI (`text-embedding-3-small`) |
| Memory | Mem0 OSS (self-hosted, optional) |
| DB GUI | Adminer |

## Environment variables

Copy `.env.example` to `.env` and fill in:

- `OPENROUTER_API_KEY` — required for chat + PDF parsing.
- `OPENAI_API_KEY` — required for semantic search + Mem0 memory.
- `DJANGO_SECRET_KEY`, `DJANGO_ALLOWED_HOSTS`, `DJANGO_CSRF_TRUSTED_ORIGINS`.
- `POSTGRES_*` / `DATABASE_URL` — set automatically in Docker.

## Run locally (SQLite, no Docker)

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env            # add OPENROUTER_API_KEY + OPENAI_API_KEY
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Without `DATABASE_URL`, the app uses SQLite and disables Mem0 (the rest works).

## Run with Docker (Postgres + Adminer + Mem0)

```bash
cp .env.example .env            # fill in keys + a strong DJANGO_SECRET_KEY
docker compose up --build
```

- App: http://localhost:8000
- Adminer (DB GUI): http://localhost:8080 — server `db`, user/password/db from `.env`.

## Deploying on Coolify

1. Create a new **Docker Compose** resource pointing at this repo.
2. Set the environment variables from `.env.example` in the Coolify UI.
3. Coolify builds `web`, `db` (pgvector), and `adminer`, and gives you domains.
4. Add your domain(s) to `DJANGO_ALLOWED_HOSTS` and `DJANGO_CSRF_TRUSTED_ORIGINS`.

## Using it

1. **Settings** → choose your chat model and parser model, then upload PDFs.
2. Wait for each lesson to reach **Ready** (parsing runs in the background).
3. **Chat**: “test me on lesson 2 vocabulary”, “go over verb tenses”, etc.
4. **Progress**: see your mastery per topic; the tutor focuses on weak spots.
```
