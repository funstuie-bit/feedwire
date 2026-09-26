# Deployment Guide

## Prerequisites

- Docker and Docker Compose (OrbStack on macOS)
- Git access to the repository

## Initial Setup

```bash
git clone https://github.com/funstuie-bit/feedwire.git
cd feedwire
cp .env.example .env
```

Edit `.env` with your credentials:

```env
POSTGRES_PASSWORD=replace-with-a-long-random-password
ANTHROPIC_API_KEY=your-anthropic-api-key
TWITTER_AUTH_TOKEN=your_twitter_auth_token
```

## Starting

```bash
docker compose up --build -d
```

This starts all 8 services: db, redis, backend, worker, beat, frontend, rsshub, nginx.

## Updating

```bash
cd /tmp/feedwire
git pull
docker compose up --build -d
```

For backend-only changes (no frontend rebuild needed):

```bash
git pull
docker compose restart backend worker beat
```

For frontend changes:

```bash
git pull
docker compose up --build -d frontend
docker compose restart nginx
```

## Monitoring

```bash
# Check all containers
docker compose ps

# View logs
docker compose logs -f backend
docker compose logs -f worker

# Check API health
curl http://localhost:8088/api/health
```

## Cloudflare Tunnel

For a private installation, put an authentication layer such as Cloudflare Access in front of the public hostname. For a public showcase, use the separate Compose project in [showcase-deployment.md](showcase-deployment.md) and route a dedicated hostname to its nginx port.

## Database

PostgreSQL data is persisted in the `pgdata` Docker volume. To backup:

```bash
docker compose exec db pg_dump -U feedwire feedwire > backup.sql
```

To restore:

```bash
docker compose exec -T db psql -U feedwire feedwire < backup.sql
```

## Twitter/X Feed Setup

1. Log into Twitter/X in a browser
2. Open DevTools > Application > Cookies > `https://x.com`
3. Copy the `auth_token` cookie value
4. Add to `.env`: `TWITTER_AUTH_TOKEN=your_token_here`
5. Restart RSSHub: `docker compose restart rsshub`
6. Add feeds as: `http://rsshub:1200/twitter/user/USERNAME`

## Ports

| Service | Internal | External | Notes |
|---------|----------|----------|-------|
| nginx | 80 | 8088 | Main entry point |
| backend | 8000 | — | API, internal to the Compose network |
| db | 5432 | — | PostgreSQL, internal to the Compose network |
| redis | 6379 | — | Task queue, internal to the Compose network |
| frontend | 3000 | — | Internal only (Gitea uses 3000) |
| rsshub | 1200 | — | Internal only, proxied via /rsshub/ |

## Troubleshooting

**Frontend won't start**: Check if port 3000 is in use (Gitea). Frontend should be `expose` only, not `ports`.

**Worker/beat crashing**: Check logs with `docker compose logs worker`. Common cause: database schema changes need a backend restart to run migrations.

**Twitter feeds returning 503**: The auth token has expired. Get a fresh one from your browser cookies.

**AI summarization fails**: Check Settings page — API key must be saved there, or set as environment variable.
