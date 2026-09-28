# Feed Sources Reference

Places to find RSS feeds worth subscribing to, organised by category.

## Feed Discovery Tools

- **[OPML.org](https://opml.org)** — curated OPML bundles you can import directly via Feeds > Import OPML
- **[Feedsearch](https://feedsearch.dev)** — paste any site URL and it finds the feed
- **[Awesome RSS Feeds](https://github.com/plenaryapp/awesome-rss-feeds)** — big categorised list on GitHub
- **[Blogroll.org](https://blogroll.org)** — curated blogroll with OPML export

FeedWire also auto-discovers feeds — just paste a page URL when adding a feed and it'll try to find the RSS/Atom link.

## Tech / Development

| Source | URL |
|--------|-----|
| Hacker News | `https://news.ycombinator.com/rss` |
| Lobste.rs | `https://lobste.rs/rss` |
| The Register | `https://www.theregister.com/headlines.atom` |
| Ars Technica | `https://feeds.arstechnica.com/arstechnica/index` |
| TechCrunch | `https://techcrunch.com/feed/` |
| The Verge | `https://www.theverge.com/rss/index.xml` |
| Wired | `https://www.wired.com/feed/rss` |

## News

| Source | URL |
|--------|-----|
| BBC News | `https://feeds.bbci.co.uk/news/rss.xml` |
| BBC Technology | `https://feeds.bbci.co.uk/news/technology/rss.xml` |
| Reuters | `https://www.reutersagency.com/feed/` |
| The Guardian World | `https://www.theguardian.com/world/rss` |
| AP News | `https://apnews.com/apf-topnews` |

## Reddit

Add `.rss` to a subreddit URL. These feeds are optional and go in the full/private installation; the public showcase deliberately excludes them.

```
https://www.reddit.com/r/selfhosted/.rss
https://www.reddit.com/r/homelab/.rss
https://www.reddit.com/r/programming/.rss
```

No cookie is normally needed for a public subreddit feed. If you want to try Reddit's optional `user`/`feed` RSS parameters, configure `REDDIT_RSS_USER` and `REDDIT_RSS_FEED` in the private `.env` as described in the [deployment guide](deployment.md#reddit-rss). They are sensitive query credentials, not cookies; do not publish them or put them in a showcase feed URL. Reddit can change RSS access and throttling at any time, and these parameters may not avoid rate limits.

## GitHub

Add `.atom` to any releases, commits, or tags page:

```
https://github.com/sveltejs/svelte/releases.atom
https://github.com/anthropics/claude-code/releases.atom
https://github.com/your-org/your-repo/commits/main.atom
```

## X / Twitter (via RSSHub)

Optional. Requires the bundled RSSHub and may require a valid X `auth_token` cookie in the full installation's private `.env`. Cookie-based access is sensitive and may stop working when X or RSSHub changes. Follow the [deployment guide](deployment.md#x-via-rsshub) to configure it. The public showcase never includes this cookie or RSSHub routes.

```
http://rsshub:1200/twitter/user/USERNAME
http://rsshub:1200/twitter/keyword/SEARCH_TERM
http://rsshub:1200/twitter/list/LIST_ID
```

## YouTube (via RSSHub)

```
http://rsshub:1200/youtube/channel/CHANNEL_ID
http://rsshub:1200/youtube/user/USERNAME
http://rsshub:1200/youtube/playlist/PLAYLIST_ID
```

To find a channel ID, go to the channel page and view source, search for `"channelId":"UCxxxxx"`.

## Instagram (via RSSHub)

```
http://rsshub:1200/instagram/user/USERNAME
```

## Other RSSHub Routes

Browse the full list at `http://localhost:8088/rsshub/` — RSSHub supports hundreds of sources including:

- **GitHub Trending**: `http://rsshub:1200/github/trending/daily`
- **Mastodon user**: `http://rsshub:1200/mastodon/user/@handle@instance.social`
- **Bluesky user**: `http://rsshub:1200/bsky/user/handle.bsky.social`
- **Product Hunt**: `http://rsshub:1200/producthunt/today`
- **Stack Overflow**: `http://rsshub:1200/stackoverflow/questions/newest`
- **Medium tag**: `http://rsshub:1200/medium/tag/programming`

## Synthetic Feeds

For sites without RSS at all, use FeedWire's synthetic feed creation:

1. Go to **Feeds** page
2. Click **Create from Webpage**
3. Paste the URL
4. FeedWire scrapes links from the page and creates an RSS-like feed

Good for news sites, blogs, and documentation pages that don't publish feeds.
