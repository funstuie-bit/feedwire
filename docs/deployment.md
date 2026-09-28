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
# Optional; leave blank unless you enable social feeds or entity extraction.
REDDIT_RSS_USER=
REDDIT_RSS_FEED=
TWITTER_AUTH_TOKEN=
ANTHROPIC_API_KEY=
```

Keep `.env` private. It contains database and potentially social-account credentials; never commit it or copy it to the public showcase environment.

## Starting

```bash
docker compose up --build -d
```

This starts the database, Redis, API, feed and control workers, scheduler, frontend, RSSHub and nginx. The full installation includes management features; it is not a public read-only site and has no built-in user login. Keep it on a trusted network or add authentication before exposing it.

## Updating

```bash
# Run from your FeedWire checkout.
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

For the intended public read-only site, use the separate Compose project in [showcase-deployment.md](showcase-deployment.md) and route a dedicated hostname to its nginx port. Do not expose this full installation directly. If you need remote access to the full installation, put an authentication layer such as Cloudflare Access in front of it.

## Database

PostgreSQL data is persisted in the `pgdata` Docker volume. To backup:

```bash
docker compose exec db pg_dump -U feedwire feedwire > backup.sql
```

To restore:

```bash
docker compose exec -T db psql -U feedwire feedwire < backup.sql
```

## Optional social feeds

Social integrations are optional and apply only to the full/private Compose project. The public showcase has no social credentials and the seed script excludes Reddit/X/RSSHub feeds. If a social feed URL contains account tokens or other private query parameters, do not publish it.

### Reddit RSS

Basic public subreddit feeds do not require a cookie. For example:

```text
https://www.reddit.com/r/selfhosted/.rss
```

If you want to try Reddit's optional authenticated RSS parameters, set `REDDIT_RSS_USER` and `REDDIT_RSS_FEED` in your private `.env`, using the values from your Reddit RSS feed settings at `https://www.reddit.com/prefs/feeds/`. FeedWire adds these as `user` and `feed` query parameters to Reddit feed requests. These are sensitive account tokens, not cookies. Reddit's RSS behavior and throttling change over time; this is optional and may not prevent rate limits. Restart the API and feed workers after changing the values:

```bash
docker compose up -d --no-deps backend worker control-worker
```

### X via RSSHub

RSSHub's X/Twitter routes may require the `auth_token` cookie from a browser logged into X:

1. Log in to X in your browser.
2. In the browser's cookie/storage settings for `https://x.com`, locate the `auth_token` cookie.
3. Put only its value in `TWITTER_AUTH_TOKEN` in the private `.env`. Treat it like a password: it can grant access to your logged-in session. Never paste it into a feed URL, issue, screenshot or public file.
4. Recreate RSSHub so it receives the new environment value:

   ```bash
   docker compose up -d --no-deps rsshub
   ```

5. Add a route such as `http://rsshub:1200/twitter/user/USERNAME` in the full installation.

Cookies expire and RSSHub/X may change or block routes. If a route stops working, remove the cookie from `.env` and rotate/revoke the session through X if you believe it was exposed. Never configure this cookie in `.env.showcase`.

## Ports

| Service | Internal | External | Notes |
|---------|----------|----------|-------|
| nginx | 80 | 8088 | Main entry point |
| backend | 8000 | — | API, internal to the Compose network |
| db | 5432 | — | PostgreSQL, internal to the Compose network |
| redis | 6379 | — | Task queue, internal to the Compose network |
| frontend | 3000 | — | Internal to the Compose network |
| rsshub | 1200 | — | Internal only, proxied via /rsshub/ |

## Troubleshooting

**Frontend won't start**: Check the frontend logs. It is internal to the Compose network (`expose` only), not published on a host port.

**Worker/beat crashing**: Check logs with `docker compose logs worker`. Common cause: database schema changes need a backend restart to run migrations.

**X/Twitter feeds fail**: RSSHub routes are third-party integrations and can break when X changes. Check the RSSHub logs, and refresh/revoke the cookie if needed.
