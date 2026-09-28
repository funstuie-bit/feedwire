# Public read-only showcase

The showcase is a separate FeedWire deployment intended to be visible to anyone. The live example is [live-feedwire.bomohome.work](https://live-feedwire.bomohome.work). Its UI and layout match FeedWire, but it has no feed-management or account controls and rejects writes on the server.

## Isolation and copied data

The showcase has its own PostgreSQL volume, Redis queue and Compose project. It does not share a database, Docker network or credentials with the full/private installation. It never starts RSSHub and its Reddit/X/API-key environment variables are explicitly blank.

The seed script copies only category labels and eligible feed definitions from the normal FeedWire database. It excludes private feeds, Reddit/X/RSSHub routes, URLs with embedded credentials, and URLs containing credential-like query parameters. The showcase starts each copied subscription from the current local day and fetches a fresh story history. It does **not** copy existing stories, settings, provider keys, cookies, notes, saved/read state, rules, tags or scores. It refuses to seed a non-empty showcase database.

The public reader serves feed-provided article content; it does not fetch arbitrary links on a visitor's behalf. The backend allows only the read APIs needed by the UI. Management pages redirect home, mutation APIs return 404, and `/rsshub` is blocked.

## Setup

1. Start the regular/private Compose project and add the feed sources you want the showcase to display. You can add them through the UI or import an OPML file. Keep that instance on a trusted network or behind authentication. Do not commit your `.env` or OPML files.
2. In the same checkout, create a separate showcase environment file and set a new, strong database password. Set the origin to the public HTTPS URL you plan to use:

   ```bash
   cp .env.showcase.example .env.showcase
   # Edit .env.showcase; for example:
   # SHOWCASE_DB_PASSWORD=<a-long-random-value>
   # SHOWCASE_ORIGIN=https://live-feedwire.bomohome.work
   ```

3. Start the isolated showcase and copy the safe categories/feed definitions:

   ```bash
   docker compose -p feedwire-showcase --env-file .env.showcase -f docker-compose.showcase.yml up --build -d
   bash scripts/seed-showcase.sh
   ```

4. The public worker fetches a fresh batch. The default local HTTP port is `8089`; change it with `SHOWCASE_HTTP_PORT` if needed.

`.env.showcase` is ignored by Git and must remain private. Do not add Reddit/X cookies or tokens to it. The seed operation is one-way and copies feed definitions only; later changes to the private feed list are not automatically mirrored. The script deliberately refuses to merge or overwrite a non-empty catalogue. For a clean re-seed, use a fresh showcase database/volume and rerun the setup; be aware that removing a database volume deletes its contents.

## Publish behind Cloudflare Tunnel

Add a **Published application** route to a Cloudflare Tunnel:

- Hostname: your public subdomain (for example, `live-feedwire.bomohome.work`)
- Service: `http://<host-running-compose>:8089`
- Access: leave this hostname public if the showcase is meant for anyone

Cloudflare creates the hostname's DNS record when the route is added. If the tunnel runs on the same host, `http://localhost:8089` may be used instead. Do not point the public hostname at the full/private app's port. Keep any Access login policy on the full/private hostname; do not remove its protection to publish the showcase.

## Verify and maintain

```bash
docker compose -p feedwire-showcase --env-file .env.showcase -f docker-compose.showcase.yml ps
curl -fsS http://localhost:8089/api/health
curl -fsS http://localhost:8089/api/feeds
```

The showcase's own feed polling continues independently. Its database means that cleanup or an outage there cannot delete data from the full/private instance.
