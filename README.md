# FeedWire

FeedWire is a self-hosted RSS/Atom reader with a compact inbox, article reader, grouped coverage, search and feed management.

**Live public showcase:** [live-feedwire.bomohome.work](https://live-feedwire.bomohome.work) — a read-only instance that starts with fresh, unauthenticated feeds. It has a separate database and does not contain the private installation's reading history, settings or social-media credentials.

This repository documents both that isolated public-showcase setup and the optional full/private installation. Reddit and X integrations are opt-in for the full installation; they are deliberately absent from the public showcase.

## What it does

- RSS/Atom subscriptions, feed discovery and OPML import/export
- A compact inbox, grouped navigation, article reader and focus mode
- Edit category groups on Sources, including custom sidebar groups
- Daily seven-day auto-read runs inside the app; saved/hidden items are untouched
- Dark/light themes, search, keyboard shortcuts and responsive layout
- Related-coverage grouping uses article URLs, headlines and local semantic matching, including across the daily digest
- Optional Reddit RSS and X/Twitter feeds in a full/private installation
- Optional entity extraction, rules, notes and relevance scoring in a full/private installation
- Settings shows AI request/token totals and known USD costs by provider/model; metering starts at installation
- A read-only showcase deployment with its own database and fresh feed history

AI summarisation is disabled. The showcase hides management features and rejects write requests on the server.

Semantic matching runs a small MiniLM model locally, with checks for differing dates, numbers and outcomes. The Docker build downloads the model; runtime does not send headlines to an AI provider. If it is unavailable, URL/headline matching still works. Grouping preserves stored stories and original coverage links.

Seven-day auto-read runs daily at 02:30 America/Los_Angeles through Celery beat and the control worker. It uses publication time, falling back to ingestion time, and skips saved/hidden items. Existing installations should remove any old `auto-read-7d.sh` host cron entry after deploying this version. The separate 90-day retention task preserves saved items, notes and learning records.

AI usage logs store metering only, without prompts, article text or credentials. Provider-reported costs take precedence; other costs use editable per-model rates in Settings. Unknown prices are labelled unpriced. Local Ollama has zero provider cost. Rates apply to future requests; historical costs are retained. Default Claude rates were checked against [Anthropic pricing](https://platform.claude.com/docs/en/about-claude/pricing) on 4 October 2026.

## Run the public showcase

The showcase is intentionally read-only. To give it a useful feed list, first run a normal FeedWire instance and add the feeds you want to publish. The seed script copies only safe category and feed definitions; it never copies stories or private reading data.

1. Start the full instance by following [Private/full installation](#privatefull-installation) and add your feeds. Keep this instance on a trusted network or behind authentication.
2. Create a separate showcase password and configure the isolated Compose project:

   ```bash
   cp .env.showcase.example .env.showcase
   # Edit .env.showcase: set a long random SHOWCASE_DB_PASSWORD and your public SHOWCASE_ORIGIN.
   docker compose -p feedwire-showcase --env-file .env.showcase -f docker-compose.showcase.yml up --build -d
   bash scripts/seed-showcase.sh
   ```

3. The showcase fetches a fresh batch from the copied feeds. Its default local HTTP port is `8089`. Put a dedicated hostname and HTTPS reverse proxy or Cloudflare Tunnel in front of that port. Do not expose the full/private instance as the public site.

See [Public showcase deployment](docs/showcase-deployment.md) for what is copied, safety boundaries, and routing details.

## Private/full installation

Requirements: Docker and Docker Compose.

```bash
git clone https://github.com/funstuie-bit/feedwire.git
cd feedwire
cp .env.example .env
# Edit .env and set a long random POSTGRES_PASSWORD.
docker compose up --build -d
```

Open `http://localhost:8088`. This is the management-capable installation, not the public showcase. It has no built-in user login; keep it on a trusted network or put an authentication layer in front of it before exposing it beyond your LAN. Optional social-feed setup is in [docs/deployment.md](docs/deployment.md#optional-social-feeds).

## Optional Reddit and X feeds

These options apply only to the full/private Compose installation. **Never put Reddit tokens or X cookies in `.env.showcase`, a public seed, a screenshot, or a committed file.** The showcase compose file clears social credentials and the seed script excludes Reddit/X/RSSHub feeds.

- **Reddit:** ordinary `https://www.reddit.com/r/<subreddit>/.rss` subscriptions need no cookie. If Reddit is throttling your installation, you can optionally set `REDDIT_RSS_USER` and `REDDIT_RSS_FEED` in the private `.env`; these are Reddit RSS query credentials, not cookies. Whether they help can vary, and Reddit may change or rate-limit RSS at any time.
- **X/Twitter:** RSSHub routes require an `auth_token` cookie in `TWITTER_AUTH_TOKEN`. This is a sensitive logged-in session credential. Use it only in the private `.env`; RSSHub may stop working when X or RSSHub changes.

See the step-by-step [optional social-feed setup](docs/deployment.md#optional-social-feeds) and [feed URL examples](docs/feed-sources.md).

## Configuration

The full installation reads environment variables from `.env`. AI provider keys are optional and are used for entity extraction only; they can also be configured in the app's Settings page. The showcase uses `.env.showcase` for its separate database password, local port and public origin. Both files are ignored by Git.

| Variable | Used by | Purpose |
|---|---|---|
| `POSTGRES_PASSWORD` | Full/private instance | Required PostgreSQL password |
| `REDDIT_RSS_USER`, `REDDIT_RSS_FEED` | Full/private instance, optional | Reddit RSS query credentials |
| `TWITTER_AUTH_TOKEN` | Full/private instance, optional | X/Twitter RSSHub session cookie |
| `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `OPENROUTER_API_KEY`, `GEMINI_API_KEY` | Full/private instance, optional | Entity extraction providers |
| `SHOWCASE_DB_PASSWORD` | Showcase only | Separate PostgreSQL password |
| `SHOWCASE_HTTP_PORT`, `SHOWCASE_ORIGIN` | Showcase only | Local port and externally visible origin |

## Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.12, FastAPI |
| Task queue | Celery, Redis |
| Database | PostgreSQL 16 |
| Frontend | SvelteKit 2, Svelte 5, Tailwind CSS 4 |
| Feed generation | RSSHub in the full/private installation only |
| Deployment | Docker Compose, nginx |

## Development

```bash
# Backend (from src/backend/)
pip install -r requirements.txt
uvicorn main:app --reload --port 8000

# Frontend (from src/frontend/)
npm install
npm run dev -- --port 3000
```

The frontend dev server proxies `/api` to `localhost:8000`.

## License

Personal project. Not licensed for redistribution.
