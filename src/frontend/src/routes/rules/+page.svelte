<script lang="ts">
	import { onMount } from 'svelte';
	import { getRules, createRule, deleteRule, getCategories } from '$lib/api';
	import type { Rule, Category } from '$lib/types';

	let rules: Rule[] = $state([]);
	let categories: Category[] = $state([]);
	let loading = $state(true);
	let error = $state('');

	// New rule form
	let matchExpression = $state('');
	let scope = $state('title');
	let wholeWord = $state(false);
	let selectedCategories = $state<number[]>([]);
	let actions = $state<string[]>([]);

	const availableActions = [
		{ value: 'extract_entities', label: 'AI extract entities' },
		{ value: 'save_to_notes', label: 'Save to Notes' },
		{ value: 'notify_discord', label: 'Notify Discord' },
	];

	async function loadData() {
		loading = true;
		try {
			[rules, categories] = await Promise.all([getRules(), getCategories()]);
		} catch (e: any) {
			error = e.message;
		} finally {
			loading = false;
		}
	}

	async function handleCreateRule() {
		if (!matchExpression.trim()) return;
		error = '';
		try {
			await createRule({
				name: matchExpression.trim(),
				match_expression: matchExpression.trim(),
				scope,
				match_whole_word: wholeWord,
				category_ids: selectedCategories,
				actions,
				is_active: true,
				background_enabled: false,
			});
			matchExpression = '';
			scope = 'title';
			wholeWord = false;
			selectedCategories = [];
			actions = [];
			await loadData();
		} catch (e: any) {
			error = e.message;
		}
	}

	async function handleDeleteRule(id: number) {
		try {
			await deleteRule(id);
			rules = rules.filter(r => r.id !== id);
		} catch (e: any) {
			error = e.message;
		}
	}

	function toggleAction(action: string) {
		if (actions.includes(action)) {
			actions = actions.filter(a => a !== action);
		} else {
			actions = [...actions, action];
		}
	}

	function toggleCategory(id: number) {
		if (selectedCategories.includes(id)) {
			selectedCategories = selectedCategories.filter(c => c !== id);
		} else {
			selectedCategories = [...selectedCategories, id];
		}
	}

	onMount(loadData);
</script>

<div class="max-w-screen-lg mx-auto px-4 sm:px-6 py-6">
	<h1 class="text-xl font-bold text-[var(--color-text)] mb-6">Rules</h1>

	{#if error}
		<div class="bg-red-50 border border-red-200 rounded-[8px] p-3 mb-4 text-sm text-red-700">{error}</div>
	{/if}

	<!-- Matching Rules -->
	<div class="bg-[var(--color-surface)] rounded-[8px] border border-[var(--color-border)] shadow-sm p-4 mb-6">
		<h2 class="text-sm font-semibold text-[var(--color-text)] mb-2">Matching Rules</h2>
		<p class="text-xs text-[var(--color-text-muted)] mb-4">
			When the feed polls for new items, any item matching a rule is automatically processed.
			Use AND / OR for compound expressions (e.g. <code class="bg-[var(--color-surface-alt)] px-1 rounded">rust AND python</code>).
		</p>

		{#if rules.length > 0}
			<div class="divide-y divide-[var(--color-border)] mb-4 border border-[var(--color-border)] rounded-[8px]">
				{#each rules as rule}
					<div class="px-4 py-3.5 sm:py-3 flex items-center gap-3">
						<div class="flex-1 min-w-0">
							<div class="flex flex-wrap items-center gap-2">
								<code class="text-sm font-medium text-[var(--color-text)] bg-[var(--color-surface-alt)] px-2 py-0.5 rounded">{rule.match_expression}</code>
								<span class="text-xs text-[var(--color-text-muted)]">in {rule.scope}</span>
								{#if rule.match_whole_word}
									<span class="px-1.5 py-0.5 text-[10px] bg-blue-100 text-blue-700 rounded">Whole word</span>
								{/if}
								{#if !rule.is_active}
									<span class="px-1.5 py-0.5 text-[10px] bg-gray-100 text-gray-500 rounded">Disabled</span>
								{/if}
							</div>
							<div class="flex gap-1 mt-1">
								{#each rule.actions as action}
									<span class="px-1.5 py-0.5 text-[10px] bg-purple-100 text-purple-700 rounded">{action}</span>
								{/each}
							</div>
						</div>
						<button
							onclick={() => handleDeleteRule(rule.id)}
							class="p-2.5 sm:p-1.5 rounded-[5px] hover:bg-red-50 text-[var(--color-text-muted)] hover:text-red-600 transition-colors flex-shrink-0"
						>
							<svg class="w-4 h-4" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
								<path d="M6 18L18 6M6 6l12 12"/>
							</svg>
						</button>
					</div>
				{/each}
			</div>
		{:else if !loading}
			<p class="text-sm text-[var(--color-text-muted)] mb-4">No matching rules yet.</p>
		{/if}

		<!-- Add rule form -->
		<div class="border border-[var(--color-border)] rounded-[8px] p-4 bg-[var(--color-surface-alt)]">
			<h3 class="text-sm font-medium text-[var(--color-text)] mb-3">Add rule</h3>
			<form onsubmit={(e) => { e.preventDefault(); handleCreateRule(); }}>
				<div class="flex flex-col sm:flex-row gap-2 mb-3">
					<input
						type="text"
						bind:value={matchExpression}
						placeholder="e.g. rust or python"
						class="flex-1 px-3 py-2.5 sm:py-1.5 border border-[var(--color-border)] rounded-[5px] text-sm focus:outline-none focus:ring-2 focus:ring-[var(--color-brand)] bg-[var(--color-surface)]"
					/>
					<div class="flex gap-2">
						<select bind:value={scope} class="flex-1 sm:flex-none border border-[var(--color-border)] rounded-[5px] px-2 py-2.5 sm:py-1.5 text-sm bg-[var(--color-surface)]">
							<option value="title">Title</option>
							<option value="content">Content</option>
							<option value="author">Author</option>
							<option value="all">All fields</option>
						</select>
						<label class="flex items-center gap-1.5 text-sm text-[var(--color-text-secondary)] whitespace-nowrap">
							<input type="checkbox" bind:checked={wholeWord} class="rounded w-4 h-4 sm:w-auto sm:h-auto" />
							Whole word
						</label>
					</div>
				</div>

				{#if categories.length > 0}
					<div class="flex flex-wrap items-center gap-3 sm:gap-2 mb-3">
						<span class="text-xs text-[var(--color-text-secondary)]">Categories:</span>
						{#each categories as cat}
							<label class="flex items-center gap-1.5 text-sm sm:text-xs py-1">
								<input
									type="checkbox"
									checked={selectedCategories.includes(cat.id)}
									onchange={() => toggleCategory(cat.id)}
									class="rounded w-4 h-4 sm:w-auto sm:h-auto"
								/>
								{cat.name}
							</label>
						{/each}
					</div>
				{/if}

				<div class="flex flex-wrap items-center gap-3 mb-3">
					{#each availableActions as act}
						<label class="flex items-center gap-1.5 text-sm sm:text-xs py-1">
							<input
								type="checkbox"
								checked={actions.includes(act.value)}
								onchange={() => toggleAction(act.value)}
								class="rounded w-4 h-4 sm:w-auto sm:h-auto"
							/>
							{act.label}
						</label>
					{/each}
				</div>

				<button
					type="submit"
					disabled={!matchExpression.trim()}
					class="px-4 py-2.5 sm:py-1.5 bg-[var(--color-brand)] text-white text-sm font-medium rounded-[5px] hover:bg-[var(--color-brand-dark)] disabled:opacity-50 transition-colors w-full sm:w-auto"
				>Add rule</button>
			</form>
		</div>
	</div>
</div>
