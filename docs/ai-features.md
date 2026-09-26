# Processing and AI features

Updated 2026-09-25 after the approved reader refresh.

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

## Article grouping does not use AI

`services/dedup.py` groups repeated canonical article URLs, removing fragments and common tracking parameters while retaining meaningful query parameters. Publisher homepages are not treated as article identities.

Related headlines across sources use title similarity or conservative containment of at least six substantive words, within 48 hours. The concise headline anchors a group independently of display order; the highest-ranked original item remains its representative. Alternative coverage includes the actual article links and can be opened in the reader. Matching happens within each requested page; this is a heuristic, not semantic understanding or a database cleanup.

No subscriptions, articles, saved states or category IDs are deleted. Navigation combines overlapping categories at display/query time.

## Other deterministic features

Relevance scoring learns from reading, saved stories and up/down feedback. Keyword/regex rules, content cleaning and archive links remain available. These operations do not require a language model. The legacy clustering API remains available, although the refreshed reader uses a single story list.

## Verification

From `src/backend`: `python -m unittest discover -s tests -v`.

The regression checks cover summary API/service shutdown, stale digest settings, historical rules, canonical URLs, category filtering and all six orderings of the three SNL headlines that prompted the cleanup.
