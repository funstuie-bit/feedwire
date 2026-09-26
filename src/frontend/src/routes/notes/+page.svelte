<script lang="ts">
	import { onMount } from 'svelte';
	import { getNotes, deleteNote } from '$lib/api';
	import type { Note } from '$lib/types';
	import dayjs from 'dayjs';
	import relativeTime from 'dayjs/plugin/relativeTime.js';

	dayjs.extend(relativeTime);

	let notes: Note[] = $state([]);
	let loading = $state(true);
	let error = $state('');

	async function loadNotes() {
		loading = true;
		try {
			notes = await getNotes();
		} catch (e: any) {
			error = e.message;
		} finally {
			loading = false;
		}
	}

	async function handleDelete(id: number) {
		try {
			await deleteNote(id);
			notes = notes.filter(n => n.id !== id);
		} catch (e: any) {
			error = e.message;
		}
	}

	onMount(loadNotes);
</script>

<div class="max-w-screen-lg mx-auto px-4 sm:px-6 py-6">
	<h1 class="text-xl font-bold text-[var(--color-text)] mb-6">Notes</h1>

	{#if error}
		<div class="bg-[var(--color-danger)]/10 border border-[var(--color-danger)]/20 rounded-[8px] p-3 mb-4 text-sm text-[var(--color-danger)]">{error}</div>
	{/if}

	{#if loading}
		<div class="flex justify-center py-10">
			<div class="animate-spin w-5 h-5 border-2 border-[var(--color-brand)] border-t-transparent rounded-full"></div>
		</div>
	{:else if notes.length === 0}
		<div class="bg-[var(--color-surface)] rounded-[8px] border border-[var(--color-border)] p-8 text-center">
			<p class="text-[var(--color-text-muted)]">No saved notes yet.</p>
			<p class="text-sm text-[var(--color-text-muted)] mt-1">Notes are created when you save items or when rules auto-save matches.</p>
		</div>
	{:else}
		<div class="bg-[var(--color-surface)] rounded-[8px] border border-[var(--color-border)] divide-y divide-[var(--color-border)]">
			{#each notes as note}
				<div class="px-4 py-3">
					<div class="flex items-start justify-between gap-3">
						<div class="flex-1">
							<h3 class="text-sm font-medium text-[var(--color-text)]">
								{note.title || note.item_title || 'Untitled note'}
							</h3>
							<p class="text-sm text-[var(--color-text-secondary)] mt-1 line-clamp-2">{note.content}</p>
							<span class="text-xs text-[var(--color-text-muted)] mt-1 block">{dayjs(note.created_at).fromNow()}</span>
						</div>
						<button
							onclick={() => handleDelete(note.id)}
							class="p-1.5 rounded-[5px] hover:bg-[var(--color-danger)]/10 text-[var(--color-text-muted)] hover:text-[var(--color-danger)] transition-colors flex-shrink-0"
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
