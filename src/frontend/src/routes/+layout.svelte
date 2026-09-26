<script lang="ts">
  import '../app.css';
  import { onMount } from 'svelte';
  import { env } from '$env/dynamic/public';
  import { page } from '$app/stores';
  import { getFeeds, getCategories, getUnreadCounts } from '$lib/api';
  import { buildLibrary, feedLabel } from '$lib/library';
  import type { Feed, Category } from '$lib/types';

  let { children } = $props();
  let feeds: Feed[] = $state([]);
  let categories: Category[] = $state([]);
  let unreadTotal = $state(0);
  let dark = $state(true);
  let mobileOpen = $state(false);
  let expanded = $state<string[]>([]);
  let expandedTopics = $state<string[]>([]);
  let sidebarError = $state('');
  let sections = $derived(buildLibrary(categories));
  const showcaseMode = env.PUBLIC_SHOWCASE === 'true';
  let selectedSection = $derived($page.url.searchParams.get('section'));
  let selectedIds = $derived(($page.url.searchParams.get('category_ids') || $page.url.searchParams.get('category_id') || '').split(',').map(Number));
  let selectedFeed = $derived(Number($page.url.searchParams.get('feed_id')));
  let routeLabel = $derived(({ '/feeds': 'Sources', '/rules': 'Rules', '/feed-health': 'Feed health', '/settings': 'Settings', '/notes': 'Notes', '/reading-list': 'Saved for later' } as Record<string,string>)[$page.url.pathname] || 'Stories');

  function count(n: number) { return n < 1000 ? String(n) : (n / 1000).toFixed(n < 10000 ? 1 : 0).replace(/\.0$/, '') + 'K'; }
  function toggleSection(name: string) {
    expanded = expanded.includes(name) ? expanded.filter(x => x !== name) : [...expanded, name];
    localStorage.setItem('feedwire-expanded-sections', JSON.stringify(expanded));
  }
  function toggleTopic(name: string) { expandedTopics = expandedTopics.includes(name) ? expandedTopics.filter(x => x !== name) : [...expandedTopics, name]; }
  function toggleTheme() {
    dark = !dark;
    document.documentElement.classList.toggle('dark', dark);
    localStorage.setItem('feedwire-dark', String(dark));
  }
  async function loadSidebar() {
    try {
      const [f, c, counts] = await Promise.all([getFeeds(), getCategories(), getUnreadCounts()]);
      feeds = f; categories = c; unreadTotal = counts.total; sidebarError = '';
    } catch { sidebarError = 'Could not refresh sources.'; }
  }
  function closeNav() { mobileOpen = false; }
  onMount(() => {
    document.documentElement.dataset.theme = 'reader';
    dark = localStorage.getItem('feedwire-dark') !== 'false';
    document.documentElement.classList.toggle('dark', dark);
    try { const saved = JSON.parse(localStorage.getItem('feedwire-expanded-sections') || '[]'); if (Array.isArray(saved)) expanded = saved.filter(x => typeof x === 'string'); } catch {}
    loadSidebar();
    const interval = setInterval(loadSidebar, 60000);
    window.addEventListener('feedwire-items-changed', loadSidebar);
    return () => { clearInterval(interval); window.removeEventListener('feedwire-items-changed', loadSidebar); };
  });
</script>

<div class="fw-app" class:nav-open={mobileOpen}>
  {#if mobileOpen}<button class="fw-scrim" aria-label="Close navigation" onclick={closeNav}></button>{/if}
  <aside class="fw-sidebar" aria-label="Main navigation">
    <a class="fw-brand" href="/" onclick={closeNav}><span aria-hidden="true">◔</span>FeedWire</a>
    <a class="fw-nav" class:active={$page.url.pathname === '/' && !$page.url.search} href="/" onclick={closeNav}><span aria-hidden="true">▤</span>All stories<b>{count(unreadTotal)}</b></a>
    {#if !showcaseMode}<a class="fw-nav" class:active={$page.url.pathname === '/reading-list'} href="/reading-list" onclick={closeNav}><span aria-hidden="true">☆</span>Saved for later</a>{/if}
    <p class="fw-nav-label">Your sections</p>
    {#each sections as section}
      <div class="fw-section">
        <a class="fw-nav" class:active={selectedSection === section.name && $page.url.pathname === '/'} href={'/?section=' + encodeURIComponent(section.name)} onclick={closeNav}><span aria-hidden="true">{section.symbol}</span>{section.name}<small>{section.count ? count(section.count) : ''}</small></a>
        <button class="fw-disclosure" aria-label={'Expand ' + section.name} aria-expanded={expanded.includes(section.name)} onclick={() => toggleSection(section.name)}>›</button>
      </div>
      {#if expanded.includes(section.name)}
        <div class="fw-topics">
          {#each section.topics as topic}
            <div class="fw-topic-row">
              <a class:active={topic.ids.some(id => selectedIds.includes(id)) && $page.url.pathname === '/'} href={'/?category_ids=' + topic.ids.join(',')} onclick={closeNav}>{topic.name}<small>{topic.count ? count(topic.count) : ''}</small></a>
              <button aria-label={'Show sources in ' + topic.name} aria-expanded={expandedTopics.includes(topic.name)} onclick={() => toggleTopic(topic.name)}>›</button>
            </div>
            {#if expandedTopics.includes(topic.name)}
              <div class="fw-source-links">
                {#each feeds.filter(f => f.category_id !== null && topic.ids.includes(f.category_id)) as feed}
                  <a class:active={selectedFeed === feed.id} href={'/?feed_id=' + feed.id} title={feedLabel(feed)} onclick={closeNav}>{feedLabel(feed)}</a>
                {/each}
              </div>
            {/if}
          {/each}
        </div>
      {/if}
    {/each}
    {#if feeds.some(f => f.category_id === null)}
      <details class="fw-uncategorised"><summary>Uncategorised sources</summary>
        {#each feeds.filter(f => f.category_id === null) as feed}<a class="fw-nav" href={'/?feed_id=' + feed.id} onclick={closeNav}>{feedLabel(feed)}</a>{/each}
      </details>
    {/if}
    <div class="fw-side-bottom">
      {#if !showcaseMode}
        <a class="fw-nav" class:active={$page.url.pathname === '/feeds'} href="/feeds" onclick={closeNav}><span aria-hidden="true">◫</span>Browse sources</a>
        <details class="fw-manage"><summary>Manage</summary>
          <a href="/notes" onclick={closeNav}>Notes</a><a href="/rules" onclick={closeNav}>Rules</a><a href="/feed-health" onclick={closeNav}>Feed health</a>
        </details>
        <a class="fw-nav" class:active={$page.url.pathname === '/settings'} href="/settings" onclick={closeNav}><span aria-hidden="true">⚙</span>Settings</a>
      {/if}
      <p class="fw-side-note">{feeds.length} subscriptions<span>{showcaseMode ? 'Public feed showcase.' : sidebarError || 'Your sources, organised.'}</span></p>
    </div>
  </aside>
  <main class="fw-main">
    <header class="fw-topbar">
      <div class="fw-crumb"><button class="fw-button fw-mobile-menu" aria-label="Open navigation" onclick={() => mobileOpen = !mobileOpen}>☰</button><span>Library</span><span>/</span><strong>{routeLabel}</strong></div>
      <button class="fw-button" onclick={toggleTheme} aria-label={dark ? 'Switch to light theme' : 'Switch to dark theme'}>◐ {dark ? 'Light theme' : 'Dark theme'}</button>
    </header>
    <div class="fw-route">{@render children()}</div>
  </main>
</div>
