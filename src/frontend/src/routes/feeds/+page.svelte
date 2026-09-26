<script lang="ts">
	import { onMount } from 'svelte';
	import { getFeeds, addFeed, addSyntheticFeed, deleteFeed, updateFeed, refreshFeed, getCategories, createCategory, importOPML, exportOPML, getFaviconUrl } from '$lib/api';
	import type { Feed, Category } from '$lib/types';
	import dayjs from 'dayjs';
	import relativeTime from 'dayjs/plugin/relativeTime.js';

	dayjs.extend(relativeTime);

	let feeds: Feed[] = $state([]);
	let categories: Category[] = $state([]);
	let newFeedUrl = $state('');
	let newFeedCategory = $state<number | undefined>(undefined);
	let newCategoryName = $state('');
	let loading = $state(true);
	let adding = $state(false);
	let error = $state('');
	let searchSubs = $state('');
	let showImport = $state(false);
	let opmlContent = $state('');
	let feedMode = $state<'rss' | 'synthetic'>('rss');

	async function loadData() {
		loading = true;
		try {
			[feeds, categories] = await Promise.all([getFeeds(), getCategories()]);
		} catch (e: any) {
			error = e.message;
		} finally {
			loading = false;
		}
	}

	async function handleAddFeed() {
		if (!newFeedUrl.trim()) return;
		adding = true;
		error = '';
		try {
			if (feedMode === 'synthetic') {
				await addSyntheticFeed(newFeedUrl.trim(), newFeedCategory);
			} else {
				await addFeed(newFeedUrl.trim(), newFeedCategory);
			}
			newFeedUrl = '';
			newFeedCategory = undefined;
			await loadData();
		} catch (e: any) {
			error = e.message;
		} finally {
			adding = false;
		}
	}

	async function handleDeleteFeed(id: number) {
		if (!confirm('Remove this feed and all its items?')) return;
		try {
			await deleteFeed(id);
			feeds = feeds.filter(f => f.id !== id);
		} catch (e: any) {
			error = e.message;
		}
	}

	async function handleCategoryChange(feed: Feed, newCategoryId: number | null) {
		try {
			await updateFeed(feed.id, { category_id: newCategoryId });
			feed.category_id = newCategoryId;
			// Refresh categories to update counts
			categories = await getCategories();
		} catch (e: any) {
			error = e.message;
		}
	}

	let editingTitleId = $state<number | null>(null);
	let titleDraft = $state('');

	function startEditTitle(feed: Feed) {
		editingTitleId = feed.id;
		titleDraft = feed.title || '';
	}

	async function saveTitle(feed: Feed) {
		const newTitle = titleDraft.trim();
		editingTitleId = null;
		if (!newTitle || newTitle === feed.title) return;
		try {
			await updateFeed(feed.id, { title: newTitle });
			feed.title = newTitle;
		} catch (e: any) {
			error = e.message;
		}
	}

	function cancelEditTitle() {
		editingTitleId = null;
		titleDraft = '';
	}

	async function handleRefreshFeed(feed: Feed) {
		try {
			const result = await refreshFeed(feed.id);
			alert(`Refreshed: ${result.new_items} new items`);
			await loadData();
		} catch (e: any) {
			error = e.message;
		}
	}

	async function handleAddCategory() {
		if (!newCategoryName.trim()) return;
		try {
			await createCategory(newCategoryName.trim());
			newCategoryName = '';
			categories = await getCategories();
		} catch (e: any) {
			error = e.message;
		}
	}

	let importing = $state(false);
	let importResult = $state<{ imported: number; errors: Array<{ url: string; error: string }> } | null>(null);

	async function handleImportOPML() {
		if (!opmlContent.trim()) return;
		importing = true;
		importResult = null;
		error = '';
		try {
			const result = await importOPML(opmlContent);
			importResult = result;
			opmlContent = '';
			await loadData();
		} catch (e: any) {
			error = `Import failed: ${e.message}`;
		} finally {
			importing = false;
		}
	}

	async function handleExportOPML() {
		const res = await exportOPML();
		const blob = await res.blob();
		const url = URL.createObjectURL(blob);
		const a = document.createElement('a');
		a.href = url;
		a.download = 'feedwire-export.opml';
		a.click();
		URL.revokeObjectURL(url);
	}

	function handleOPMLFile(e: Event) {
		const input = e.target as HTMLInputElement;
		const file = input.files?.[0];
		if (!file) return;
		const reader = new FileReader();
		reader.onload = () => { opmlContent = reader.result as string; };
		reader.readAsText(file);
	}

	let filteredFeeds = $derived(
		feeds.filter(f =>
			!searchSubs || (f.title?.toLowerCase().includes(searchSubs.toLowerCase()) ?? false)
		)
	);

	onMount(loadData);
</script>

<div class="max-w-screen-lg mx-auto px-4 sm:px-6 py-6">
	<div class="flex flex-col sm:flex-row sm:items-center justify-between gap-2 mb-6">
		<h1 class="text-xl font-bold text-[var(--color-text)]">Manage Feeds</h1>
		<div class="flex gap-2">
			<button onclick={handleExportOPML} class="px-3 py-2 sm:py-1.5 text-sm sm:text-xs text-[var(--color-text-secondary)] hover:text-[var(--color-text)] transition-colors">Export OPML</button>
			<button onclick={() => showImport = !showImport} class="px-3 py-2 sm:py-1.5 text-sm sm:text-xs text-[var(--color-text-secondary)] hover:text-[var(--color-text)] transition-colors">Import OPML</button>
		</div>
	</div>

	{#if error}
		<div class="bg-[var(--color-danger)]/10 border border-[var(--color-danger)]/20 rounded-[8px] p-3 mb-4 text-sm text-[var(--color-danger)]">{error}</div>
	{/if}

	<!-- Add Feed hero -->
	<div class="rounded-[12px] border border-[var(--color-border)] p-4 sm:p-5 mb-6" style="background: linear-gradient(135deg, color-mix(in srgb, var(--color-brand) 8%, transparent) 0%, color-mix(in srgb, var(--color-brand) 2%, transparent) 100%);">
		<div class="flex items-start gap-4 mb-4">
			<div class="w-12 h-12 rounded-[10px] bg-[var(--color-surface)] grid place-items-center flex-shrink-0 border border-[var(--color-border)]">
				<svg class="w-6 h-6 text-[var(--color-brand)]" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
					<line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>
				</svg>
			</div>
			<div class="flex-1 min-w-0">
				<h2 class="text-base sm:text-lg font-bold text-[var(--color-text)] mb-0.5">Add a feed</h2>
				<p class="text-[13px] text-[var(--color-text-muted)]">
					{#if feedMode === 'synthetic'}
						Paste any webpage URL and we'll create a synthetic feed from its links.
					{:else}
						Paste an RSS/Atom feed URL, or a page URL and we'll try to discover the feed.
					{/if}
				</p>
			</div>
		</div>

		<div class="flex gap-2 mb-3">
			<button
				onclick={() => feedMode = 'rss'}
				class="px-3 py-2 sm:py-1 rounded-[5px] text-sm sm:text-xs font-medium transition-colors {feedMode === 'rss' ? 'bg-[var(--color-brand)] text-white' : 'bg-[var(--color-surface)] border border-[var(--color-border)] text-[var(--color-text-secondary)]'}"
			>RSS/Atom Feed</button>
			<button
				onclick={() => feedMode = 'synthetic'}
				class="px-3 py-2 sm:py-1 rounded-[5px] text-sm sm:text-xs font-medium transition-colors {feedMode === 'synthetic' ? 'bg-[var(--color-brand)] text-white' : 'bg-[var(--color-surface)] border border-[var(--color-border)] text-[var(--color-text-secondary)]'}"
			>Create from Webpage</button>
		</div>

		<form onsubmit={(e) => { e.preventDefault(); handleAddFeed(); }} class="flex flex-col sm:flex-row gap-3">
			<input
				type="url"
				bind:value={newFeedUrl}
				placeholder={feedMode === 'rss' ? 'https://example.com/feed.xml' : 'https://example.com/news'}
				required
				class="flex-1 px-3 py-2.5 sm:py-2 border border-[var(--color-border)] rounded-[5px] text-sm bg-[var(--color-surface)] text-[var(--color-text)] focus:outline-none focus:ring-2 focus:ring-[var(--color-brand)]"
			/>
			<div class="flex gap-2 sm:gap-3">
				{#if categories.length > 0}
					<select bind:value={newFeedCategory} class="flex-1 sm:flex-none border border-[var(--color-border)] rounded-[5px] px-2 py-2.5 sm:py-2 text-sm bg-[var(--color-surface)] text-[var(--color-text)]">
						<option value={undefined}>No category</option>
						{#each categories as cat}
							<option value={cat.id}>{cat.name}</option>
						{/each}
					</select>
				{/if}
				<button
					type="submit"
					disabled={adding}
					class="px-5 py-2.5 sm:py-2 bg-[var(--color-brand)] text-white text-sm font-medium rounded-[5px] hover:bg-[var(--color-brand-dark)] disabled:opacity-50 transition-colors whitespace-nowrap"
				>
					{adding ? 'Adding...' : feedMode === 'synthetic' ? 'Create Feed' : 'Add Feed'}
				</button>
			</div>
		</form>
	</div>

	<!-- Import OPML -->
	{#if showImport}
		<div class="bg-[var(--color-surface)] rounded-[8px] border border-[var(--color-border)] p-4 mb-6">
			<h2 class="text-sm font-semibold text-[var(--color-text)] mb-3">Import OPML</h2>

			<label for="opml-file" class="block mb-3">
				<span class="inline-flex items-center gap-2 px-3 py-2 bg-[var(--color-surface-alt)] text-[var(--color-text)] text-sm font-medium rounded-[5px] hover:bg-[var(--color-border)] transition-colors cursor-pointer border border-[var(--color-border)]">
					<svg class="w-4 h-4" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
						<path d="M9 13h6m-3-3v6m5 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/>
					</svg>
					Choose OPML file
				</span>
				<input id="opml-file" type="file" accept=".opml,.xml" onchange={handleOPMLFile} class="hidden" />
			</label>

			<textarea
				bind:value={opmlContent}
				placeholder="Or paste OPML XML content here..."
				rows="6"
				class="w-full px-3 py-2 border border-[var(--color-border)] rounded-[5px] text-sm font-mono bg-[var(--color-surface)] text-[var(--color-text)] focus:outline-none focus:ring-2 focus:ring-[var(--color-brand)] mb-3"
			></textarea>

			<div class="flex items-center gap-3 mb-3">
				<button
					onclick={handleImportOPML}
					disabled={!opmlContent.trim() || importing}
					class="px-5 py-2 bg-[var(--color-brand)] text-white text-sm font-medium rounded-[5px] hover:bg-[var(--color-brand-dark)] disabled:opacity-50 transition-colors flex items-center gap-2"
				>
					{#if importing}
						<div class="animate-spin w-4 h-4 border-2 border-white border-t-transparent rounded-full"></div>
						Importing...
					{:else}
						Import
					{/if}
				</button>
				{#if importing}
					<span class="text-xs text-[var(--color-text-muted)]">This can take a minute for many feeds — don't close the page.</span>
				{/if}
			</div>

			{#if importResult}
				<div class="mt-4 p-3 rounded-[5px] border {importResult.errors.length === 0 ? 'bg-[var(--color-success)]/10 border-[var(--color-success)]/20' : 'bg-[var(--color-warning-bg)] border-[var(--color-warning)]/20'}">
					<p class="text-sm font-medium text-[var(--color-text)] mb-2">
						Imported {importResult.imported} feeds
						{#if importResult.errors.length > 0}
							&middot; {importResult.errors.length} errors
						{/if}
					</p>
					{#if importResult.errors.length > 0}
						<details class="text-xs">
							<summary class="cursor-pointer text-[var(--color-text-secondary)] hover:text-[var(--color-text)] mb-1">Show errors</summary>
							<div class="mt-2 space-y-1 max-h-60 overflow-y-auto">
								{#each importResult.errors as err}
									<div class="p-2 bg-[var(--color-surface)] rounded text-[11px] font-mono">
										<div class="text-[var(--color-danger)] break-all">{err.url}</div>
										<div class="text-[var(--color-text-muted)] mt-1">{err.error}</div>
									</div>
								{/each}
							</div>
						</details>
					{/if}
				</div>
			{/if}
		</div>
	{/if}

	<!-- Categories -->
	<div class="bg-[var(--color-surface)] rounded-[8px] border border-[var(--color-border)] p-4 mb-6">
		<h2 class="text-sm font-semibold text-[var(--color-text)] mb-3">Categories</h2>
		<div class="flex flex-wrap gap-2 mb-3">
			{#each categories as cat}
				<span class="inline-flex items-center gap-1.5 px-3 py-1 bg-[var(--color-surface-alt)] rounded-full text-sm text-[var(--color-text)]">
					{cat.name}
					<span class="text-xs text-[var(--color-text-muted)]">({cat.feed_count})</span>
				</span>
			{/each}
			{#if categories.length === 0}
				<span class="text-sm text-[var(--color-text-muted)]">No categories yet</span>
			{/if}
		</div>
		<form onsubmit={(e) => { e.preventDefault(); handleAddCategory(); }} class="flex gap-2">
			<input
				type="text"
				bind:value={newCategoryName}
				placeholder="New category name"
				class="flex-1 sm:flex-none px-3 py-2 sm:py-1.5 border border-[var(--color-border)] rounded-[5px] text-sm bg-[var(--color-surface)] text-[var(--color-text)] focus:outline-none focus:ring-2 focus:ring-[var(--color-brand)]"
			/>
			<button type="submit" class="px-3 py-2 sm:py-1.5 bg-[var(--color-surface-alt)] text-sm font-medium rounded-[5px] text-[var(--color-text)] hover:bg-[var(--color-border)] transition-colors">Add</button>
		</form>
	</div>

	<!-- Subscriptions -->
	<div class="bg-[var(--color-surface)] rounded-[8px] border border-[var(--color-border)]">
		<div class="p-4 border-b border-[var(--color-border)]">
			<div class="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
				<h2 class="text-sm font-semibold text-[var(--color-text)]">Subscriptions ({feeds.length})</h2>
				<input
					type="text"
					bind:value={searchSubs}
					placeholder="Search..."
					class="w-full sm:w-auto px-3 py-2 sm:py-1.5 border border-[var(--color-border)] rounded-[5px] text-sm bg-[var(--color-surface)] text-[var(--color-text)] focus:outline-none focus:ring-2 focus:ring-[var(--color-brand)]"
				/>
			</div>
		</div>

		{#if loading}
			<div class="flex justify-center py-10">
				<div class="animate-spin w-5 h-5 border-2 border-[var(--color-brand)] border-t-transparent rounded-full"></div>
			</div>
		{:else if filteredFeeds.length === 0}
			<p class="p-4 text-sm text-[var(--color-text-muted)]">No subscriptions yet.</p>
		{:else}
			<div class="divide-y divide-[var(--color-border)]">
				{#each filteredFeeds as feed}
					<div class="px-4 py-3.5 sm:py-3 flex items-center gap-3 hover:bg-[var(--color-surface-hover)] transition-colors">
						<img
							src={getFaviconUrl(feed.site_url || feed.url)}
							alt=""
							class="w-5 h-5 flex-shrink-0 rounded-sm"
							onerror={(e) => (e.target as HTMLImageElement).style.display='none'}
						/>
						<div class="flex-1 min-w-0">
							<div class="flex items-center gap-2">
								{#if editingTitleId === feed.id}
									<input
										type="text"
										bind:value={titleDraft}
										onblur={() => saveTitle(feed)}
										onkeydown={(e) => {
											if (e.key === 'Enter') saveTitle(feed);
											if (e.key === 'Escape') cancelEditTitle();
										}}
										class="flex-1 min-w-0 text-sm font-medium text-[var(--color-text)] bg-[var(--color-surface-alt)] border border-[var(--color-brand)] rounded-[3px] px-1.5 py-0.5 focus:outline-none focus:ring-1 focus:ring-[var(--color-brand)]"
										autofocus
									/>
								{:else}
									<button
										onclick={() => startEditTitle(feed)}
										class="text-sm font-medium truncate text-[var(--color-text)] hover:text-[var(--color-brand)] text-left cursor-pointer"
										title="Click to rename"
									>{feed.title || feed.url}</button>
								{/if}
								{#if feed.unread_count > 0}
									<span class="px-1.5 py-0.5 text-[10px] font-bold bg-[var(--color-brand)]/10 text-[var(--color-brand)] rounded-full">{feed.unread_count}</span>
								{/if}
								{#if feed.last_error}
									<span class="px-1.5 py-0.5 text-[10px] bg-red-100 dark:bg-red-900/30 text-[var(--color-danger)] rounded">Error</span>
								{/if}
							</div>
							<div class="text-xs text-[var(--color-text-muted)] truncate">
								{feed.url}
								{#if feed.last_fetched_at}
									&middot; {dayjs(feed.last_fetched_at).fromNow()}
								{/if}
								&middot; {feed.item_count} items
							</div>
						</div>
						<div class="flex items-center gap-2">
							<select
								value={feed.category_id ?? ''}
								onchange={(e) => {
									const val = (e.target as HTMLSelectElement).value;
									handleCategoryChange(feed, val === '' ? null : parseInt(val));
								}}
								class="border border-[var(--color-border)] rounded-[5px] px-2 py-1 text-xs bg-[var(--color-surface)] text-[var(--color-text-secondary)] focus:outline-none focus:ring-1 focus:ring-[var(--color-brand)]"
								title="Category"
							>
								<option value="">No category</option>
								{#each categories as cat}
									<option value={cat.id}>{cat.name}</option>
								{/each}
							</select>
							<button
								onclick={() => handleRefreshFeed(feed)}
								class="p-2.5 sm:p-1.5 rounded-[5px] hover:bg-[var(--color-surface-alt)] text-[var(--color-text-muted)] hover:text-[var(--color-text)] transition-colors"
								title="Refresh"
							>
								<svg class="w-5 h-5 sm:w-4 sm:h-4" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
									<path d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"/>
								</svg>
							</button>
							<button
								onclick={() => handleDeleteFeed(feed.id)}
								class="p-2.5 sm:p-1.5 rounded-[5px] hover:bg-[var(--color-danger)]/10 text-[var(--color-text-muted)] hover:text-[var(--color-danger)] transition-colors"
								title="Remove"
							>
								<svg class="w-4 h-4" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
									<path d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"/>
								</svg>
							</button>
						</div>
					</div>
				{/each}
			</div>
		{/if}
	</div>
</div>
