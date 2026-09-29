<script lang="ts">
  import { onMount, untrack } from 'svelte';
  import { page } from '$app/stores';
  import { env } from '$env/dynamic/public';
  import { getItems, getItem, getReadable, updateItem, bulkUpdateItems, getFeeds, getCategories, getTags, addTagToItem, removeTagFromItem } from './api';
  import { articleUrl, buildLibrary, feedLabel } from './library';
  import type { Item, Feed, Category, Tag } from './types';
  import dayjs from 'dayjs';
  import relativeTime from 'dayjs/plugin/relativeTime.js';
  dayjs.extend(relativeTime);

  let { savedOnly = false }: { savedOnly?: boolean } = $props();
  const showcaseMode = env.PUBLIC_SHOWCASE === 'true';
  let items: Item[] = $state([]);
  let feeds: Feed[] = $state([]);
  let failedFavicons: Set<number> = $state(new Set());
  let categories: Category[] = $state([]);
  let tags: Tag[] = $state([]);
  let selected: Item | null = $state(null);
  let readerContent = $state('');
  let readerLoading = $state(false);
  let readerError = $state('');
  let focus = $state(false);
  let loading = $state(true);
  let ready = $state(false);
  let error = $state('');
  let filter = $state<'all' | 'unread'>('all');
  let search = $state('');
  let query = $state('');
  let timeWindow = $state('7d');
  let sort = $state('time');
  let offset = $state(0);
  let hasMore = $state(false);
  let requestId = 0;
  let readerRequest = 0;
  let searchTimer: ReturnType<typeof setTimeout>;
  let readerPane = $state<HTMLElement>();
  let titleElement = $state<HTMLHeadingElement>();
  let sectionName = $derived($page.url.searchParams.get('section') || '');
  let feedId = $derived($page.url.searchParams.get('feed_id') || '');
  let categoryId = $derived($page.url.searchParams.get('category_id') || '');
  let categoryIds = $derived($page.url.searchParams.get('category_ids') || '');
  let library = $derived(buildLibrary(categories));
  let activeSection = $derived(library.find(s => s.name === sectionName));
  let title = $derived(savedOnly ? 'Saved for later' : feedId ? sourceName(Number(feedId)) : sectionName || library.flatMap(s => s.topics).find(t => t.ids.join(',') === categoryIds)?.name || categories.find(c => String(c.id) === categoryId)?.name || 'All stories');
  let original = $derived.by(() => articleUrl(selected?.link));
  let content = $derived.by(() => readerHtml(readerContent, selected?.link || ''));

  function sourceName(id: number, fallback = 'Source') { const f = feeds.find(f => f.id === id); return f ? feedLabel(f) : fallback; }
  function sourceFavicon(item: Item) {
    const feed = feeds.find(f => f.id === item.feed_id);
    const candidate = item.feed_favicon || feed?.favicon_url;
    if (!candidate) return '';
    try {
      const icon = new URL(candidate);
      const site = feed?.site_url ? new URL(feed.site_url) : null;
      // Only load HTTPS favicons from the publisher's own origin. This avoids
      // mixed content and prevents feed metadata from pointing at arbitrary hosts.
      if (icon.protocol !== 'https:' || !site || icon.origin !== site.origin) return '';
      return icon.href;
    } catch { return ''; }
  }
  function sourceHue(item: Item) {
    const feed = feeds.find(f => f.id === item.feed_id);
    const key = feed?.site_url || item.feed_favicon || String(item.feed_id);
    let hash = 0;
    for (let i = 0; i < key.length; i++) hash = (hash * 31 + key.charCodeAt(i)) | 0;
    return Math.abs(hash) % 360;
  }
  function markFaviconFailed(feedId: number) { failedFavicons = new Set(failedFavicons).add(feedId); }
  function stripHtml(value: string | null | undefined) { return (value || '').replace(/<[^>]*>/g, ' ').replace(/&[^;]+;/g, ' ').replace(/\s+/g, ' ').trim(); }
  function age(item: Item) { return dayjs(item.published_at || item.created_at).fromNow(); }
  function readingTime(item: Item) { return Math.max(1, Math.ceil(stripHtml(item.content).split(/\s+/).length / 220)); }
  function notifyChange() { window.dispatchEvent(new Event('feedwire-items-changed')); }
  function readerHtml(html: string, base: string) {
    if (!html || typeof DOMParser === 'undefined') return '';
    const doc = new DOMParser().parseFromString(html, 'text/html');
    doc.querySelectorAll('script,style,iframe,object,embed,form,input,button,link,meta,base').forEach(e => e.remove());
    for (const el of Array.from(doc.body.querySelectorAll('*'))) {
      for (const attr of Array.from(el.attributes)) {
        if (/^on/i.test(attr.name) || ['srcdoc', 'style'].includes(attr.name)) el.removeAttribute(attr.name);
      }
      for (const attr of ['href', 'src', 'xlink:href', 'action', 'srcset']) {
        if (!el.hasAttribute(attr)) continue;
        if (attr === 'srcset' || attr === 'xlink:href' || attr === 'action') { el.removeAttribute(attr); continue; }
        try { const url = new URL(el.getAttribute(attr) || '', base); if (['http:', 'https:'].includes(url.protocol)) el.setAttribute(attr, url.href); else el.removeAttribute(attr); }
        catch { el.removeAttribute(attr); }
      }
    }
    for (const a of Array.from(doc.querySelectorAll('a'))) {
      if (a.textContent?.trim() === '[link]') { a.remove(); continue; }
      a.target = '_blank'; a.rel = 'noopener noreferrer';
    }
    return doc.body.innerHTML;
  }
  function savePreferences() { localStorage.setItem('feedwire-reader-filters', JSON.stringify({ timeWindow, sort, filter })); }
  async function loadItems(more = false, quiet = false) {
    const token = ++requestId;
    if (!quiet) loading = true;
    error = '';
    const start = more ? offset : 0;
    const params: Record<string,string> = { time_window: savedOnly ? 'all' : timeWindow, sort_by: sort, limit: '100', offset: String(start), deduplicate: 'true' };
    if (savedOnly) params.is_saved = 'true';
    if (filter === 'unread') params.unread_only = 'true';
    if (query) params.search = query;
    if (!savedOnly) {
      if (feedId) params.feed_id = feedId;
      if (categoryId) params.category_id = categoryId;
      if (categoryIds) params.category_ids = categoryIds;
      if (activeSection) params.category_ids = activeSection.ids.join(',');
    }
    try {
      const result: Item[] = await getItems(params);
      if (token !== requestId) return;
      if (more) { const seen = new Set(items.map(i => i.id)); items = [...items, ...result.filter(i => !seen.has(i.id))]; }
      else items = result;
      offset = start + 100;
      // Dedup may shrink a full raw page. Continue until an empty raw page.
      hasMore = result.length > 0;
    } catch (e) { if (token === requestId) error = e instanceof Error ? e.message : 'Could not load stories.'; }
    finally { if (token === requestId) loading = false; }
  }
  function handleSearch() { clearTimeout(searchTimer); searchTimer = setTimeout(() => query = search, 300); }
  async function openItem(item: Item) {
    const token = ++readerRequest;
    selected = item; readerContent = item.cleaned_content || item.content || ''; readerError = ''; readerLoading = false;
    requestAnimationFrame(() => { readerPane?.scrollTo(0, 0); titleElement?.focus({ preventScroll: true }); });
    if (!showcaseMode && !item.is_read) {
      updateItem(item.id, { is_read: true }).then(() => {
        item.is_read = true; items = items.map(i => i.id === item.id ? { ...i, is_read: true } : i);
        if (selected?.id === item.id) selected.is_read = true;
        notifyChange();
      }).catch(() => { if (selected?.id === item.id) readerError = 'Could not mark this article as read.'; });
    }
    if (stripHtml(readerContent).length < 200 && item.link) {
      readerLoading = true;
      try { const result = await getReadable(item.id); if (token === readerRequest && selected?.id === item.id) readerContent = result.content; }
      catch { if (token === readerRequest) readerError = 'Full text could not be loaded. Open the original article to continue reading.'; }
      finally { if (token === readerRequest) readerLoading = false; }
    }
  }
  function closeReader() { const id = selected?.id; ++readerRequest; selected = null; focus = false; requestAnimationFrame(() => document.querySelector<HTMLButtonElement>('[data-story="' + id + '"]')?.focus({ preventScroll: true })); }
  async function changeItem(patch: Record<string, unknown>) {
    const current = selected; if (!current) return;
    try { await updateItem(current.id, patch); Object.assign(current, patch); items = items.map(i => i.id === current.id ? { ...i, ...patch } : i); if (patch.is_hidden || (savedOnly && patch.is_saved === false)) { items = items.filter(i => i.id !== current.id); closeReader(); } notifyChange(); }
    catch (e) { readerError = e instanceof Error ? e.message : 'Could not save this change.'; }
  }
  async function markShownRead() {
    const shown = items.filter(i => !i.is_read).map(i => i.id); if (!shown.length) return;
    try { await bulkUpdateItems(shown, { is_read: true }); items = items.map(i => ({ ...i, is_read: true })); if (selected && shown.includes(selected.id)) selected.is_read = true; notifyChange(); }
    catch (e) { error = e instanceof Error ? e.message : 'Could not mark these stories as read.'; }
  }
  async function toggleTag(tag: Tag) {
    const current = selected; if (!current) return;
    try { const exists = current.tags.some(t => t.id === tag.id); if (exists) await removeTagFromItem(current.id, tag.id); else await addTagToItem(current.id, tag.id); current.tags = exists ? current.tags.filter(t => t.id !== tag.id) : [...current.tags, tag]; }
    catch { readerError = 'Could not update this tag.'; }
  }
  async function openAlternative(id: number) { try { await openItem(await getItem(id)); } catch { readerError = 'Could not load this version.'; } }
  function keydown(e: KeyboardEvent) {
    if (e.key === 'Escape') { closeReader(); return; }
    if ((e.target as HTMLElement)?.closest('input,textarea,select,button,a,summary,[contenteditable="true"]') || e.ctrlKey || e.metaKey || e.altKey) return;
    const index = items.findIndex(i => i.id === selected?.id);
    if ((e.key === 'j' || e.key === 'k') && items.length) { e.preventDefault(); const next = e.key === 'j' ? Math.min(index + 1, items.length - 1) : Math.max(0, index - 1); openItem(items[next]); }
    if (e.key === 'o' && original) window.open(original, '_blank', 'noopener,noreferrer');
    if (!showcaseMode && e.key === 's' && selected) changeItem({ is_saved: !selected.is_saved });
    if (!showcaseMode && e.key === 'h' && selected) changeItem({ is_hidden: true });
    if (e.key === 'r') loadItems();
  }
  onMount(() => {
    let disposed = false;
    try { const prefs = JSON.parse(localStorage.getItem('feedwire-reader-filters') || '{}'); if (['24h','7d','30d','all'].includes(prefs.timeWindow)) timeWindow = prefs.timeWindow; if (['time','relevance','source','title'].includes(prefs.sort)) sort = prefs.sort; if (prefs.filter === 'unread') filter = 'unread'; } catch {}
    Promise.all([getFeeds(), getCategories(), getTags()]).then(([f,c,t]) => { if (!disposed) { feeds=f; categories=c; tags=t; ready=true; } }).catch(() => { if (!disposed) { error='Could not load the library. Refresh to try again.'; loading=false; } });
    const timer = setInterval(() => { if (!selected && ready) loadItems(false, true); }, 180000);
    return () => { disposed=true; ++requestId; ++readerRequest; clearInterval(timer); clearTimeout(searchTimer); };
  });
  $effect(() => {
    feedId; categoryId; categoryIds; sectionName; query; timeWindow; sort; filter; savedOnly;
    if (ready) untrack(() => { savePreferences(); selected=null; focus=false; ++readerRequest; loadItems(); });
  });
</script>

<svelte:window onkeydown={keydown} />
<div class="fw-workspace" class:reading={selected !== null} class:focused={focus}>
  <section class="fw-inbox" aria-label="Stories">
    <div class="fw-heading"><div><p class="fw-eyebrow">Your reading</p><h1>{title}</h1><p class="fw-subhead">{savedOnly ? 'The stories you kept for later.' : 'One story, all its sources. A little less noise.'}</p></div><button class="fw-button fw-refresh" onclick={() => loadItems()} disabled={loading}>↻ Refresh</button></div>
    <div class="fw-filters"><div class="fw-tabs" aria-label="Filter stories"><button aria-pressed={filter === 'all'} onclick={() => filter='all'}>{savedOnly ? 'All saved' : 'Latest'}</button><button aria-pressed={filter === 'unread'} onclick={() => filter='unread'}>Unread</button>{#if !savedOnly && !showcaseMode}<a href="/reading-list">Saved</a>{/if}</div><label class="fw-search"><span aria-hidden="true">⌕</span><input type="search" placeholder="Find a story…" aria-label="Find a story" bind:value={search} oninput={handleSearch} /></label></div>
    <div class="fw-list-options">
      {#if !savedOnly}<select aria-label="Time window" bind:value={timeWindow}><option value="24h">Last 24 hours</option><option value="7d">Last 7 days</option><option value="30d">Last 30 days</option><option value="all">All time</option></select>{/if}
      <select aria-label="Sort stories" bind:value={sort}><option value="time">Newest first</option><option value="relevance">Most relevant</option><option value="source">By source</option><option value="title">By title</option></select>
      {#if !showcaseMode}<button onclick={markShownRead} disabled={!items.some(i => !i.is_read)}>Mark shown read</button>{/if}
    </div>
    {#if error}<p class="fw-error" role="alert">{error}</p>{/if}
    <div class="fw-list-head" aria-hidden="true"><span>Source</span><span>Story</span><span>Published</span></div>
    {#each items as item (item.id)}
      <button class="fw-story" class:selected={selected?.id === item.id} class:is-read={item.is_read} data-story={item.id} aria-label={'Read ' + (item.title || 'Untitled')} aria-pressed={selected?.id === item.id} onclick={() => openItem(item)}>
        <span class="fw-source"><span class="fw-favicon" style={`--source-hue:${sourceHue(item)}`} aria-hidden="true">{#if sourceFavicon(item) && !failedFavicons.has(item.feed_id)}<img src={sourceFavicon(item)} alt="" loading="lazy" decoding="async" referrerpolicy="no-referrer" onerror={() => markFaviconFailed(item.feed_id)} />{:else}<span>{sourceName(item.feed_id, item.feed_title || '?').slice(0,1)}</span>{/if}</span><span>{sourceName(item.feed_id, item.feed_title || 'Source')}</span></span>
        <span class="fw-story-copy"><span class="fw-story-title">{item.title || 'Untitled'}{#if item.is_saved}<span aria-label="Saved"> ☆</span>{/if}</span><span class="fw-story-deck">{stripHtml(item.content).slice(0,220)}</span></span>
        <span class="fw-story-meta"><span>{age(item)}</span><span class="fw-coverage">{item.similar_items.length ? (item.similar_items.length + 1) + ' sources ↗' : readingTime(item) + ' min read'}</span></span>
      </button>
    {/each}
    {#if loading}<p class="fw-empty" role="status">Loading stories…</p>{:else if !items.length && !error}<div class="fw-empty"><h2>{savedOnly ? 'Your reading list is clear' : 'Nothing here right now'}</h2><p>{query ? 'Try a different search.' : 'Try a wider time window or another section.'}</p></div>{/if}
    {#if hasMore}<button class="fw-button fw-load-more" onclick={() => loadItems(true)} disabled={loading}>Load more stories</button>{/if}
    <div class="fw-list-footer"><span>{items.length} stories shown</span><span><kbd>j</kbd> <kbd>k</kbd> move · <kbd>Esc</kbd> inbox</span></div>
  </section>
  {#if selected}
    <section class="fw-reader" aria-label="Article reader" bind:this={readerPane}>
      <div class="fw-reader-toolbar"><button class="fw-button" onclick={closeReader}>← Inbox</button><div class="fw-reader-actions"><button class="fw-button fw-focus" aria-pressed={focus} onclick={() => focus=!focus}>{focus ? 'Show story list' : 'Focus view'}</button>{#if !showcaseMode}<button class="fw-button" aria-pressed={selected.is_saved} onclick={() => changeItem({ is_saved: !selected!.is_saved })}>{selected.is_saved ? '★ Saved' : '☆ Save'}</button>{/if}{#if original}<a class="fw-button" href={original} target="_blank" rel="noopener noreferrer">Open original ↗</a>{/if}</div></div>
      <article class="fw-reader-inner">
        <p class="fw-section-label">{sourceName(selected.feed_id, selected.feed_title || 'Article')}</p>
        <h2 class="fw-article-title" tabindex="-1" bind:this={titleElement}>{selected.title || 'Untitled'}</h2>
        <div class="fw-byline">{#if selected.author}<span>{selected.author}</span><span>·</span>{/if}<span>{age(selected)}</span><span>·</span><span>{readingTime(selected)} min read</span></div>
        {#if !showcaseMode}<div class="fw-article-tools"><button class="fw-button" aria-label="More like this" aria-pressed={selected.feedback === 1} onclick={() => changeItem({ feedback: selected!.feedback === 1 ? 0 : 1 })}>↑ More like this</button><button class="fw-button" aria-label="Less like this" aria-pressed={selected.feedback === -1} onclick={() => changeItem({ feedback: selected!.feedback === -1 ? 0 : -1 })}>↓ Less</button><button class="fw-button" onclick={() => changeItem({ is_hidden: true })}>Hide</button>{#if selected.is_paywalled && articleUrl(selected.archive_url)}<a class="fw-button" href={articleUrl(selected.archive_url)!} target="_blank" rel="noopener noreferrer">Try archive ↗</a>{/if}</div>{/if}
        {#if readerError}<p class="fw-error" role="alert">{readerError}</p>{/if}
        {#if readerLoading}<p class="fw-empty" role="status">Loading article…</p>{/if}
        <div class="reader-content fw-article-text">{@html content || '<p>No article text is available in this feed. Use Open original to read it on the publisher’s site.</p>'}</div>
        {#if selected.similar_items.length}<details class="fw-also"><summary>Also covered by {selected.similar_items.length} other {selected.similar_items.length === 1 ? 'source' : 'sources'}</summary><div>
          {#each selected.similar_items as related}<div class="fw-alternative"><button onclick={() => openAlternative(related.id)}>{sourceName(related.feed_id, related.feed_title || 'Other coverage')}</button>{#if articleUrl(related.link)}<a href={articleUrl(related.link)!} target="_blank" rel="noopener noreferrer">Open article ↗</a>{/if}</div>{/each}
        </div></details>{/if}
        {#if tags.length}<details class="fw-also"><summary>Tags{selected.tags.length ? ' · ' + selected.tags.length : ''}</summary><div class="fw-tag-list">{#each tags as tag}<button class="fw-button" aria-pressed={selected.tags.some(t => t.id === tag.id)} onclick={() => toggleTag(tag)}>{tag.name}</button>{/each}</div></details>{/if}
      </article>
    </section>
  {/if}
</div>
