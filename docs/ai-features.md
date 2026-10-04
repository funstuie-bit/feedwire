# Processing and AI features

Updated 2026-10-04 after the group editor, local story matching and usage tracking release.

## Summarisation is off

Stu requested that the summariser be removed. The reader has no summary button, keyboard shortcut or summary panel. Existing summary text is retained in the database, but is not displayed in the reader or used in the daily digest.

- `POST /api/ai/process` with `action: summarize` returns HTTP 410 before reading the article or selecting a provider.
- `POST /api/ai/summarize-batch` returns HTTP 410.
- `services.ai_service.summarize_item` raises before any content fetch or model request, protecting legacy callers.
- Historical rules with a `summarize` action skip that action and still perform their other actions.
- Scheduled and manual digests use publisher excerpts. A legacy `digest_summarize=true` value cannot enable generation; the production setting is also now false.

Before shutdown the configured summariser was Anthropic Claude Haiku 4.5 (`claude-haiku-4-5-20251001`). Stored historical summaries do not contain model provenance.

## Entity extraction remains separate

Existing entity-extraction rules and the `extract_entities` API action remain available. They can make model requests and incur provider charges. The new reading view does not expose an entity-extraction button. Provider configuration is retained under Settings → Entity extraction provider. No provider keys were removed or exposed during this change.

## Article grouping runs locally

`services/dedup.py` groups repeated canonical article URLs, removing fragments and common tracking parameters while retaining meaningful query parameters. Publisher homepages are not treated as article identities.

Related headlines across sources use title similarity, conservative containment or local MiniLM embeddings with cosine similarity of at least 0.85, within 48 hours. Different numbers, negation and common opposing outcomes veto headline matches. Semantic matching also requires at least three substantive words in each headline and a shared word. Matching is conservative: some paraphrases will still remain separate.

The concise headline anchors reader groups independently of display order; the highest-ranked original item remains its representative. Alternative coverage includes actual article links. Reader matching happens within each requested page; the digest applies the same matcher across categories and retains the highest-relevance accepted story. The Docker build includes the small `sentence-transformers/all-MiniLM-L6-v2` model through FastEmbed. Inference uses two CPU threads, loads local files only and caches up to 4,096 headline vectors per process. A missing model falls back to URL/headline matching. No headlines are sent to providers and no API charge is incurred for grouping.

No subscriptions, articles, saved states or category IDs are deleted. Navigation combines overlapping categories at display/query time.

## AI usage and cost

Settings → AI usage & cost shows rolling 7/30/90-day requests, input/output tokens, failures and known USD cost per provider/model. Tracking starts with this release; past spend cannot be reconstructed. Only entity-extraction provider calls are metered because summarisation remains disabled.

`usage_logs` records provider/model, operation, status, token counts, cache-read/write counts, cost source and timestamp. It stores no article text, prompts, outputs, API keys or cookies. Each provider response is logged independently of the article transaction, including billed responses that later fail to parse as entities. Failed calls are recorded without inventing token counts or charges.

Provider-reported costs take precedence. Other costs are estimates using exact provider/model rates from the `ai_pricing` setting, editable under Model prices. Default Claude Haiku 4.5 and Sonnet 4.6 rates were verified against [Anthropic pricing](https://platform.claude.com/docs/en/about-claude/pricing) on 2026-10-04. Cached input and cache writes are priced separately. Unknown prices and missing usage remain explicit; local Ollama has zero provider cost. Saved rates apply to future requests; historical costs stay unchanged. Estimates do not replace provider invoices.

`GET /api/ai/usage?days=30` returns aggregates and prices; `PATCH /api/ai/pricing` validates and stores a model's rates. Both are blocked on the public showcase, as are all management APIs. A metering storage failure is logged without discarding a successful extraction result.

## Other deterministic features

Relevance scoring learns from reading, saved stories and up/down feedback. Keyword/regex rules, content cleaning and archive links remain available. These operations do not require a language model. The legacy clustering API remains available, although the refreshed reader uses a single story list.

## Verification

From `src/backend`: `python -m unittest discover -s tests -v`.

The 23 regression checks cover summary shutdown, canonical/category matching, digest grouping, contradictory headlines, auto-read/retention, provider metering fixtures, cached tokens, unknown costs and custom rates. Browser checks: `scripts/check-reader-ui.cjs` and `scripts/check-roadmap-ui.cjs`, with Playwright installed. They intercept all API requests and cover desktop/mobile group editing, navigation, usage periods/errors, model prices and reader behaviour.
