# FeedWire

Self-hosted RSS/Atom reader with a compact inbox, article reader, grouped coverage, search and source management. The public showcase deployment starts with fresh, unauthenticated feeds and has a separate database.

Seven compact navigation sections, a full-width inbox, centred reader and focus mode. Neutral dark and light themes share a matching sidebar and readable accents. “Open original” and alternative-coverage links use actual article URLs.

## Features

- **Feed management** — subscribe to RSS/Atom feeds, auto-discover feeds from page URLs, OPML import/export
- **Synthetic feeds** — create RSS feeds from any webpage that doesn't have one
- **Twitter/X feeds** — via bundled RSSHub with cookie-based auth
- **AI summarisation off** — no summary controls or summary generation, including existing rules and scheduled/manual digests; old stored summaries remain in the database
- **Entity extraction** — pull out people, orgs, technologies, locations from articles
- **Article grouping** — matches canonical article URLs and similar headlines, with links to alternative coverage (no model calls)
- **Relevance scoring** — learns from your reading behavior, surfaces interesting items
- **Rules engine** — match items by keyword (AND/OR/regex), extract entities, save to notes or notify Discord; historical summarise actions are skipped
- **Reader mode** — fetches and cleans full article content for link-only feeds (HN, Lobsters)
- **Paywall detection** — identifies paywalled articles and provides archive.ph links
- **Notes** — save/bookmark items, auto-save via rules
- **Dark/light themes** — manual toggle with persisted preference (dark by default)
- **Keyboard shortcuts** — j/k navigate, o open original, s save, h hide, r refresh, Escape return to inbox
- **Mobile responsive** — 44px touch targets, responsive layouts

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.12, FastAPI |
| Task Queue | Celery + Redis |
| Database | PostgreSQL 16 |
| Frontend | SvelteKit 2, Svelte 5, Tailwind CSS 4 |
| Feed Generation | RSSHub (Twitter, YouTube, Reddit, etc.) |
| Deployment | Docker Compose, nginx reverse proxy |
| External Access | Cloudflare Tunnel + Zero Trust Access |

## Quick Start

```bash
git clone https://github.com/funstuie-bit/feedwire.git
cd feedwire
cp .env.example .env
# Edit .env — add ANTHROPIC_API_KEY for AI features, TWITTER_AUTH_TOKEN for Twitter feeds
docker compose up --build -d
```

Open `http://localhost:8088` in your browser.

## Configuration

### Environment Variables (.env)

| Variable | Description | Required |
|----------|-------------|----------|
| `POSTGRES_PASSWORD` | A strong database password set in `.env` | Yes |
| `ANTHROPIC_API_KEY` | For optional entity extraction via Claude | No |
| `OPENAI_API_KEY` | For optional entity extraction via GPT | No |
| `OPENROUTER_API_KEY` | Access to 300+ models via OpenRouter | No |
| `GEMINI_API_KEY` | Google Gemini (Pro accounts avoid rate limits) | No |
| `TWITTER_AUTH_TOKEN` | Twitter cookie auth_token for RSSHub | No |

API keys, model names, and base URLs can all be configured per-provider in the Settings page (stored in the database). The Settings page also supports Ollama for local model inference.

### Adding Feeds

See [docs/feed-sources.md](docs/feed-sources.md) for a comprehensive reference of feed URLs by category.

Quick starters:

```
# RSS/Atom
https://news.ycombinator.com/rss
https://feeds.bbci.co.uk/news/rss.xml
https://www.theregister.com/headlines.atom

# Reddit (add .rss to any subreddit)
https://www.reddit.com/r/selfhosted/.rss

# GitHub releases (add .atom)
https://github.com/sveltejs/svelte/releases.atom

# Twitter/X (via RSSHub)
http://rsshub:1200/twitter/user/USERNAME

# YouTube (via RSSHub)
http://rsshub:1200/youtube/channel/CHANNEL_ID
```

Browse all RSSHub routes at `http://localhost:8088/rsshub/`.

### Rules

Rules match incoming items and trigger actions automatically. Expressions support:
- Simple keywords: `python`
- AND: `rust AND wasm`
- OR: `rust OR go`
- Regex: `/\bAI\b/`

Available actions: AI extract entities, Save to Notes, Notify Discord. Historical summarise actions are disabled.

### Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `j` / `k` | Navigate items |
| `o` / `Enter` | Open article in new tab |
| `s` | Save/bookmark item |
| `Escape` | Return to the inbox |
| `r` | Refresh items |
| `Escape` | Close reader / exit selection |

## Architecture

```
nginx (:8088)
  ├── /api/*    → FastAPI backend (:8000)
  ├── /rsshub/* → RSSHub (:1200)
  └── /*        → SvelteKit frontend (:3000)

Celery Beat → schedules periodic tasks
Celery Worker → feed fetching, rule processing, relevance scoring
Redis → task queue + RSSHub cache
PostgreSQL → all application data
```

### Docker Services

| Service | Purpose |
|---------|---------|
| `backend` | FastAPI API server |
| `frontend` | SvelteKit SSR app |
| `worker` | Celery task worker |
| `beat` | Celery periodic scheduler |
| `db` | PostgreSQL database |
| `redis` | Task queue and cache |
| `rsshub` | RSS feed generator for social media |
| `nginx` | Reverse proxy |

### Background Tasks

| Task | Schedule | Description |
|------|----------|-------------|
| `fetch_all_feeds` | Every 5 min | Checks and fetches feeds respecting per-feed intervals |
| `update_relevance_scores` | Every 15 min | Recalculates item scores based on reading behavior |
| `cleanup_old_items` | Daily 3am | Removes unsaved items older than 90 days |

## External Access

For a public read-only installation, use the isolated [showcase deployment](docs/showcase-deployment.md). Keep the standard management UI behind authentication or on a trusted network.

## API

All endpoints are under `/api/`:

| Endpoint | Methods | Description |
|----------|---------|-------------|
| `/api/health` | GET | Health check |
| `/api/feeds` | GET, POST | List/add feeds |
| `/api/feeds/{id}` | DELETE | Remove feed |
| `/api/feeds/{id}/refresh` | POST | Manually refresh feed |
| `/api/feeds/synthetic` | POST | Create feed from webpage |
| `/api/feeds/import-opml` | POST | Import OPML |
| `/api/feeds/export-opml` | GET | Export OPML |
| `/api/items` | GET | List items (filterable) |
| `/api/items/{id}` | GET, PATCH | Get/update item |
| `/api/items/{id}/readable` | GET | Get cleaned article content |
| `/api/items/clusters` | GET | Get topic clusters |
| `/api/items/unread-counts` | GET | Unread counts per feed |
| `/api/items/mark-all-read` | POST | Mark items as read |
| `/api/items/bulk-update` | POST | Bulk update items |
| `/api/categories` | GET, POST | List/create categories |
| `/api/rules` | GET, POST | List/create rules |
| `/api/rules/{id}` | PATCH, DELETE | Update/delete rule |
| `/api/notes` | GET, POST | List/create notes |
| `/api/ai/process` | POST | Entity extraction; summarise requests return HTTP 410 |
| `/api/settings` | GET, PATCH | Get/update settings |

## Development

```bash
# Backend (from src/backend/)
pip install -r requirements.txt
uvicorn main:app --reload --port 8000

# Frontend (from src/frontend/)
npm install
npm run dev -- --port 3000

# Frontend proxies /api to localhost:8000 in dev mode
```

## License

Personal project. Not licensed for redistribution.
