# Public FeedWire showcase

The showcase is a second FeedWire instance. It has its own PostgreSQL volume and Redis queue; the private instance keeps running independently.

## What is copied

Run `bash scripts/seed-showcase.sh` on a host where the normal private FeedWire Compose stack is running and `.env.showcase` has been configured. The script copies category names and feed definitions only. It excludes private feeds, Reddit/X/RSSHub social feeds, feed URLs with embedded credentials, and URLs with credential-like query parameters. New subscriptions are stamped with the current time so the public worker begins fetching fresh stories immediately.

It does not copy stories, settings, provider keys, cookies, notes, saved/read state, rules, tags or scores. It never starts RSSHub. The public app exposes only read requests needed for the story library; writes and management pages return 404. Its article reader uses feed-provided content and does not fetch arbitrary URLs on a visitor's behalf.

## Start

1. Create `.env.showcase` from `.env.showcase.example`. Replace the database password with a new random value (for example, `openssl rand -hex 32`). Keep this file private; it is ignored by Git.
2. Start the isolated services and seed the safe feeds:

   ```bash
   docker compose -p feedwire-showcase --env-file .env.showcase -f docker-compose.showcase.yml up --build -d
   bash scripts/seed-showcase.sh
   ```

3. Wait for the worker to fetch the first batch. The default local port is `8089`; `SHOWCASE_HTTP_PORT` can change it.
4. Route a dedicated public hostname through your HTTPS reverse proxy or tunnel to this port. Do not reuse the private hostname's Access policy: the showcase is intentionally public. The private site and its credentials are not connected to this Compose project.

The `PUBLIC_READ_ONLY` backend flag is a server-side API allowlist. The browser hiding admin buttons is only a convenience. Keep the database and Redis ports unpublished, and do not attach this project to the private app's Docker network.

## Verify / maintain

```bash
docker compose -p feedwire-showcase --env-file .env.showcase -f docker-compose.showcase.yml ps
curl -fsS http://localhost:8089/api/health
```

The showcase starts with empty reading state and populates articles from feed publication after deployment. The ordinary feed polling schedule continues in its own worker. Its own database means a cleanup or outage here cannot delete data from the private instance.
