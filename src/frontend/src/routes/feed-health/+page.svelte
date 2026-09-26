<script lang="ts">
	import { onMount } from 'svelte';
	import { getFeedHealth, deleteFeed, refreshFeed } from '$lib/api';

	let feeds: any[] = $state([]);
	let loading = $state(true);
	let filter = $state('all');

	const statusColors: Record<string, string> = {
		healthy: 'var(--color-success)',
		warning: 'var(--color-warning)',
		error: 'var(--color-danger)',
		stale: 'var(--color-text-muted)',
		inactive: 'var(--color-text-faint)',
	};

	let filtered = $derived(
		filter === 'all' ? feeds : feeds.filter(f => f.status === filter)
	);

	let statusCounts = $derived({
		all: feeds.length,
		healthy: feeds.filter(f => f.status === 'healthy').length,
		warning: feeds.filter(f => f.status === 'warning').length,
		error: feeds.filter(f => f.status === 'error').length,
		stale: feeds.filter(f => f.status === 'stale').length,
		inactive: feeds.filter(f => f.status === 'inactive').length,
	});

	async function load() {
		loading = true;
		try { feeds = await getFeedHealth(); } catch {} finally { loading = false; }
	}

	async function handleRefresh(id: number) {
		try { await refreshFeed(id); } catch {}
	}

	async function handleDelete(id: number, title: string) {
		if (!confirm(`Delete "${title}"?`)) return;
		await deleteFeed(id);
		feeds = feeds.filter(f => f.id !== id);
	}

	onMount(load);
</script>

<div class="h-full flex flex-col bg-[var(--color-surface)]">
	<div class="p-4 border-b border-[var(--color-border)]">
		<h1 class="text-lg font-semibold text-[var(--color-text)] mb-3">Feed Health</h1>
		<div class="flex gap-2 flex-wrap">
			{#each ['all', 'healthy', 'warning', 'error', 'stale', 'inactive'] as s}
				<button
					onclick={() => filter = s}
					class="px-3 py-1 rounded text-xs font-medium transition-colors {filter === s ? 'bg-[var(--color-brand)] text-white' : 'text-[var(--color-text-muted)] hover:text-[var(--color-text)] bg-[var(--color-surface-alt)]'}"
					>{s} ({statusCounts[s as keyof typeof statusCounts]})</button>
			{/each}
		</div>
	</div>

	<div class="flex-1 overflow-y-auto">
		{#if loading}
			<div class="flex items-center justify-center py-16">
				<div class="animate-spin w-5 h-5 border-2 border-[var(--color-brand)] border-t-transparent rounded-full"></div>
			</div>
		{:else}
			<table class="w-full text-xs">
				<thead class="sticky top-0 bg-[var(--color-surface-alt)]">
					<tr class="text-left text-[var(--color-text-muted)]">
						<th class="px-3 py-2 font-medium">Status</th>
						<th class="px-3 py-2 font-medium">Feed</th>
						<th class="px-3 py-2 font-medium">Category</th>
						<th class="px-3 py-2 font-medium text-right">24h</th>
						<th class="px-3 py-2 font-medium text-right">7d</th>
						<th class="px-3 py-2 font-medium text-right">Total</th>
						<th class="px-3 py-2 font-medium">Last Item</th>
						<th class="px-3 py-2 font-medium">Error</th>
						<th class="px-3 py-2 font-medium"></th>
					</tr>
				</thead>
				<tbody>
					{#each filtered as feed}
						<tr class="border-b border-[var(--color-border)] hover:bg-[var(--color-surface-hover)]">
							<td class="px-3 py-2">
								<span class="inline-block w-2 h-2 rounded-full" style="background-color: {statusColors[feed.status]}"></span>
								<span class="ml-1 text-[10px] text-[var(--color-text-muted)]">{feed.status}</span>
							</td>
							<td class="px-3 py-2 text-[var(--color-text)] max-w-[200px] truncate" title={feed.url}>{feed.title}</td>
							<td class="px-3 py-2 text-[var(--color-text-muted)]">{feed.category}</td>
							<td class="px-3 py-2 text-right text-[var(--color-text)]">{feed.items_24h}</td>
							<td class="px-3 py-2 text-right text-[var(--color-text)]">{feed.items_7d}</td>
							<td class="px-3 py-2 text-right text-[var(--color-text-muted)]">{feed.total_items}</td>
							<td class="px-3 py-2 text-[var(--color-text-muted)]">
								{#if feed.days_since_item !== null}
									{feed.days_since_item === 0 ? 'Today' : `${feed.days_since_item}d ago`}
								{:else}
									Never
								{/if}
							</td>
							<td class="px-3 py-2 max-w-[150px] truncate text-[var(--color-danger)]" title={feed.last_error || ''}>
								{#if feed.error_count > 0}
									{feed.error_count}× {feed.last_error || ''}
								{/if}
							</td>
							<td class="px-3 py-2">
								<div class="flex gap-1">
									<button onclick={() => handleRefresh(feed.id)} class="px-1.5 py-0.5 text-[10px] text-[var(--color-brand)] hover:bg-[var(--color-action)]/10 rounded" title="Refresh">↻</button>
									{#if feed.status === 'inactive' || feed.status === 'error'}
										<button onclick={() => handleDelete(feed.id, feed.title)} class="px-1.5 py-0.5 text-[10px] text-[var(--color-danger)] hover:bg-[var(--color-danger)]/10 rounded" title="Delete">×</button>
									{/if}
								</div>
							</td>
						</tr>
					{/each}
				</tbody>
			</table>
		{/if}
	</div>
</div>
