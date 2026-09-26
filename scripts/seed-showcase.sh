#!/usr/bin/env bash
set -euo pipefail

repo_dir="$(cd "$(dirname "$0")/.." && pwd)"
cd "$repo_dir"

private_compose=(docker compose -f docker-compose.yml)
public_compose=(docker compose -p feedwire-showcase --env-file .env.showcase -f docker-compose.showcase.yml)

empty_tables="$("${public_compose[@]}" exec -T db psql -U feedwire -d feedwire -At -c "SELECT (SELECT count(*) FROM categories) + (SELECT count(*) FROM feeds)")"
if [[ "$empty_tables" != "0" ]]; then
  echo "Showcase categories and feeds are not empty; refusing to merge another seed." >&2
  exit 1
fi

# Only copy the category tree and anonymous, non-social feed definitions.
# No items, reading state, notes, tags, rules, settings, or secrets are copied.
"${private_compose[@]}" exec -T db psql -U feedwire -d feedwire -c \
  "COPY (SELECT id,name,sort_order,now(),group_name FROM categories ORDER BY id) TO STDOUT" \
  | "${public_compose[@]}" exec -T db psql -v ON_ERROR_STOP=1 -U feedwire -d feedwire -c \
  "COPY categories(id,name,sort_order,created_at,group_name) FROM STDIN"

"${private_compose[@]}" exec -T db psql -U feedwire -d feedwire -c \
  "COPY (SELECT id,url,title,description,site_url,favicon_url,category_id,FALSE,fetch_interval_minutes,NULL,NULL,0,date_trunc('day', now() AT TIME ZONE 'America/Los_Angeles') AT TIME ZONE 'America/Los_Angeles',FALSE FROM feeds WHERE NOT is_private AND lower(url) !~ '(reddit[.]com|twitter[.]com|x[.]com|rsshub:1200/(twitter|reddit)/)' AND url !~* '^https?://[^/]*:[^/@]+@' AND url !~* '[?&](auth|token|key|secret|cookie|user|password|passwd|api_key|access_token)=' ORDER BY id) TO STDOUT" \
  | "${public_compose[@]}" exec -T db psql -v ON_ERROR_STOP=1 -U feedwire -d feedwire -c \
  "COPY feeds(id,url,title,description,site_url,favicon_url,category_id,is_private,fetch_interval_minutes,last_fetched_at,last_error,error_count,created_at,title_custom) FROM STDIN"

"${public_compose[@]}" exec -T db psql -v ON_ERROR_STOP=1 -U feedwire -d feedwire -c \
  "SELECT setval(pg_get_serial_sequence('categories','id'), GREATEST(coalesce(max(id),1),1), max(id) IS NOT NULL) FROM categories; SELECT setval(pg_get_serial_sequence('feeds','id'), GREATEST(coalesce(max(id),1),1), max(id) IS NOT NULL) FROM feeds;"

echo "Seeded public categories and safe feed definitions. The separate public worker will fetch a fresh first batch."
