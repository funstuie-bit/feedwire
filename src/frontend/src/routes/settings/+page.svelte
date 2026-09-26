<script lang="ts">
	import { onMount } from 'svelte';
	import { getSettings, updateSettings, healthCheck } from '$lib/api';

	interface Provider {
		id: string;
		name: string;
		default_model: string;
		needs_base_url: boolean;
		default_base_url?: string;
		model_examples: string[];
	}

	let settings: Record<string, string> = $state({});
	let providers: Provider[] = $state([]);
	let loading = $state(true);
	let saving = $state(false);
	let error = $state('');
	let success = $state('');
	let apiHealthy = $state(false);

	let aiProvider = $state('anthropic');
	let apiKeys = $state<Record<string, string>>({});
	let models = $state<Record<string, string>>({});
	let baseUrls = $state<Record<string, string>>({});
	let defaultTimeWindow = $state('24h');
	let defaultFetchInterval = $state('30');

	// Discord / digest settings
	let discordWebhookUrl = $state('');
	let discordDigestWebhookUrl = $state('');
	let digestHours = $state('24');
	let digestMaxItems = $state('5');
	let digestStatus = $state('');
	let testingWebhook = $state(false);
	let sendingDigest = $state(false);

	// Score alerts (push notifications for high-relevance items)
	let alertsEnabled = $state(false);
	let alertsWebhookUrl = $state('');
	let alertsScoreThreshold = $state('0.7');
	let alertsMaxPerHour = $state('5');

	let currentProvider = $derived(providers.find(p => p.id === aiProvider));

	async function loadProviders() {
		try {
			const res = await fetch('/api/ai/providers');
			const data = await res.json();
			providers = data.providers;
		} catch {}
	}

	async function loadSettings() {
		loading = true;
		try {
			const data = await getSettings();
			settings = data.settings;
			aiProvider = settings.ai_provider || 'anthropic';
			defaultTimeWindow = settings.default_time_window || '24h';
			defaultFetchInterval = settings.default_fetch_interval || '30';

			discordWebhookUrl = settings.discord_webhook_url || '';
			discordDigestWebhookUrl = settings.discord_digest_webhook_url || '';
			digestHours = settings.digest_hours || '24';
			digestMaxItems = settings.digest_max_items_per_category || '5';

			alertsEnabled = settings.alerts_enabled === 'true';
			alertsWebhookUrl = settings.alerts_webhook_url || '';
			alertsScoreThreshold = settings.alerts_score_threshold || '0.7';
			alertsMaxPerHour = settings.alerts_max_per_hour || '5';

			for (const provider of ['anthropic', 'openai', 'openrouter', 'gemini', 'ollama']) {
				apiKeys[provider] = settings[`${provider}_api_key`] || '';
				models[provider] = settings[`${provider}_model`] || '';
				baseUrls[provider] = settings[`${provider}_base_url`] || '';
			}
		} catch (e: any) {
			error = e.message;
		} finally {
			loading = false;
		}
	}

	async function checkHealth() {
		try {
			await healthCheck();
			apiHealthy = true;
		} catch {
			apiHealthy = false;
		}
	}

	async function testDiscordWebhook(url: string) {
		if (!url) { digestStatus = 'Enter a webhook URL first'; return; }
		testingWebhook = true;
		digestStatus = '';
		try {
			const res = await fetch('/api/digest/test-webhook', {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ webhook_url: url }),
			});
			if (res.ok) digestStatus = '✅ Test message sent';
			else {
				const err = await res.json();
				digestStatus = `❌ ${err.detail || 'Failed'}`;
			}
		} catch (e: any) {
			digestStatus = `❌ ${e.message}`;
		} finally {
			testingWebhook = false;
			setTimeout(() => digestStatus = '', 5000);
		}
	}

	async function sendDigestNow() {
		sendingDigest = true;
		digestStatus = '';
		try {
			// Use the URL from the form so it works before Save
			const webhookUrl = discordDigestWebhookUrl || discordWebhookUrl;
			const res = await fetch('/api/digest/send-now', {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ webhook_url: webhookUrl }),
			});
			if (res.ok) {
				const data = await res.json();
				digestStatus = `✅ Sent ${data.items} items across ${data.categories} categories`;
			} else {
				const err = await res.json();
				digestStatus = `❌ ${err.detail || 'Failed'}`;
			}
		} catch (e: any) {
			digestStatus = `❌ ${e.message}`;
		} finally {
			sendingDigest = false;
			setTimeout(() => digestStatus = '', 5000);
		}
	}

	async function handleSave() {
		saving = true;
		error = '';
		success = '';
		try {
			const updates = [
				{ key: 'ai_provider', value: aiProvider },
				{ key: 'default_time_window', value: defaultTimeWindow },
				{ key: 'default_fetch_interval', value: defaultFetchInterval },
				{ key: 'discord_webhook_url', value: discordWebhookUrl },
				{ key: 'discord_digest_webhook_url', value: discordDigestWebhookUrl },
				{ key: 'digest_hours', value: digestHours },
				{ key: 'digest_max_items_per_category', value: digestMaxItems },
				{ key: 'digest_summarize', value: 'false' },
				{ key: 'alerts_enabled', value: String(alertsEnabled) },
				{ key: 'alerts_webhook_url', value: alertsWebhookUrl },
				{ key: 'alerts_score_threshold', value: alertsScoreThreshold },
				{ key: 'alerts_max_per_hour', value: alertsMaxPerHour },
			];

			for (const provider of ['anthropic', 'openai', 'openrouter', 'gemini', 'ollama']) {
				updates.push({ key: `${provider}_api_key`, value: apiKeys[provider] || '' });
				updates.push({ key: `${provider}_model`, value: models[provider] || '' });
				updates.push({ key: `${provider}_base_url`, value: baseUrls[provider] || '' });
			}

			await updateSettings(updates);
			success = 'Settings saved';
			setTimeout(() => success = '', 3000);
		} catch (e: any) {
			error = e.message;
		} finally {
			saving = false;
		}
	}

	onMount(() => {
		loadProviders();
		loadSettings();
		checkHealth();
	});
</script>

<div class="max-w-screen-md mx-auto px-4 sm:px-6 py-6">
	<h1 class="text-xl font-bold text-[var(--color-text)] mb-6">Settings</h1>

	{#if error}
		<div class="bg-[var(--color-danger)]/10 border border-[var(--color-danger)]/20 rounded-[8px] p-3 mb-4 text-sm text-[var(--color-danger)]">{error}</div>
	{/if}
	{#if success}
		<div class="bg-[var(--color-success)]/10 border border-[var(--color-success)]/20 rounded-[8px] p-3 mb-4 text-sm text-[var(--color-success)]">{success}</div>
	{/if}

	{#if loading}
		<div class="flex justify-center py-10">
			<div class="animate-spin w-5 h-5 border-2 border-[var(--color-brand)] border-t-transparent rounded-full"></div>
		</div>
	{:else}
		<div class="bg-[var(--color-surface)] rounded-[8px] border border-[var(--color-border)] p-4 mb-4">
			<h2 class="text-sm font-semibold text-[var(--color-text)] mb-3">Status</h2>
			<div class="flex items-center gap-2">
				<span class="w-2.5 h-2.5 rounded-full {apiHealthy ? 'bg-[var(--color-success)]' : 'bg-[var(--color-danger)]'}"></span>
				<span class="text-sm text-[var(--color-text-secondary)]">API: {apiHealthy ? 'Connected' : 'Disconnected'}</span>
			</div>
		</div>

		<div class="bg-[var(--color-surface)] rounded-[8px] border border-[var(--color-border)] p-4 mb-4">
			<h2 class="text-sm font-semibold text-[var(--color-text)] mb-1">Entity extraction provider</h2>
			<p class="text-xs text-[var(--color-text-muted)] mb-4">Article summarisation is off. These settings apply only to entity extraction in rules.</p>
			<p class="text-xs text-[var(--color-text-muted)] mb-4">Configure multiple providers and switch between them. Only the active provider is used for requests.</p>

			<div class="mb-4">
				<label for="ai-provider-select" class="block text-sm font-medium text-[var(--color-text-secondary)] mb-1">Active Provider</label>
				<select id="ai-provider-select" bind:value={aiProvider} class="w-full border border-[var(--color-border)] rounded-[5px] px-3 py-2 text-sm bg-[var(--color-surface)] text-[var(--color-text)] focus:outline-none focus:ring-2 focus:ring-[var(--color-brand)]">
					{#each providers as p}
						<option value={p.id}>{p.name}</option>
					{/each}
				</select>
			</div>

			{#if currentProvider}
				<div class="border-t border-[var(--color-border)] pt-4 space-y-4">
					<div class="flex items-center gap-2 mb-2">
						<span class="label-uppercase" style="font-size:11px;">Configure</span>
						<span class="text-sm font-medium text-[var(--color-text)]">{currentProvider.name}</span>
					</div>

					{#if currentProvider.id !== 'ollama'}
						<div>
							<label for="api-key-{currentProvider.id}" class="block text-sm font-medium text-[var(--color-text-secondary)] mb-1">API Key</label>
							<input
								id="api-key-{currentProvider.id}"
								type="password"
								bind:value={apiKeys[currentProvider.id]}
								placeholder={currentProvider.id === 'anthropic' ? 'sk-ant-...' : currentProvider.id === 'gemini' ? 'AIza...' : 'sk-...'}
								class="w-full px-3 py-2.5 sm:py-2 border border-[var(--color-border)] rounded-[5px] text-sm bg-[var(--color-surface)] text-[var(--color-text)] focus:outline-none focus:ring-2 focus:ring-[var(--color-brand)]"
							/>
							{#if currentProvider.id === 'openrouter'}
								<p class="mt-1 text-xs text-[var(--color-text-muted)]">Get a key at <a href="https://openrouter.ai/keys" target="_blank" rel="noopener" class="text-[var(--color-brand)] hover:underline">openrouter.ai/keys</a></p>
							{:else if currentProvider.id === 'gemini'}
								<p class="mt-1 text-xs text-[var(--color-text-muted)]">Get a key at <a href="https://aistudio.google.com/apikey" target="_blank" rel="noopener" class="text-[var(--color-brand)] hover:underline">aistudio.google.com/apikey</a></p>
							{/if}
						</div>
					{/if}

					<div>
						<label for="model-{currentProvider.id}" class="block text-sm font-medium text-[var(--color-text-secondary)] mb-1">Model</label>
						<input
							id="model-{currentProvider.id}"
							type="text"
							bind:value={models[currentProvider.id]}
							placeholder={currentProvider.default_model}
							list="model-examples-{currentProvider.id}"
							class="w-full px-3 py-2 border border-[var(--color-border)] rounded-[5px] text-sm bg-[var(--color-surface)] text-[var(--color-text)] focus:outline-none focus:ring-2 focus:ring-[var(--color-brand)] font-mono"
						/>
						<datalist id="model-examples-{currentProvider.id}">
							{#each currentProvider.model_examples as m}
								<option value={m}></option>
							{/each}
						</datalist>
						<p class="mt-1 text-xs text-[var(--color-text-muted)]">Default: <code class="bg-[var(--color-surface-alt)] px-1 rounded">{currentProvider.default_model}</code>. Leave blank to use default.</p>
					</div>

					{#if currentProvider.needs_base_url}
						<div>
							<label for="base-url-{currentProvider.id}" class="block text-sm font-medium text-[var(--color-text-secondary)] mb-1">Base URL</label>
							<input
								id="base-url-{currentProvider.id}"
								type="text"
								bind:value={baseUrls[currentProvider.id]}
								placeholder={currentProvider.default_base_url || ''}
								class="w-full px-3 py-2 border border-[var(--color-border)] rounded-[5px] text-sm bg-[var(--color-surface)] text-[var(--color-text)] focus:outline-none focus:ring-2 focus:ring-[var(--color-brand)] font-mono"
							/>
							{#if currentProvider.id === 'ollama'}
								<p class="mt-1 text-xs text-[var(--color-text-muted)]">Use <code class="bg-[var(--color-surface-alt)] px-1 rounded">host.docker.internal:11434/v1</code> to reach Ollama running on your Mac host.</p>
							{/if}
						</div>
					{/if}
				</div>
			{/if}
		</div>

		<div class="bg-[var(--color-surface)] rounded-[8px] border border-[var(--color-border)] p-4 mb-4">
			<h2 class="text-sm font-semibold text-[var(--color-text)] mb-3">Defaults</h2>
			<div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
				<div>
					<label for="time-window" class="block text-sm font-medium text-[var(--color-text-secondary)] mb-1">Time window</label>
					<select id="time-window" bind:value={defaultTimeWindow} class="w-full border border-[var(--color-border)] rounded-[5px] px-3 py-2 text-sm bg-[var(--color-surface)] text-[var(--color-text)]">
						<option value="1h">1 hour</option>
						<option value="6h">6 hours</option>
						<option value="12h">12 hours</option>
						<option value="24h">24 hours</option>
						<option value="48h">48 hours</option>
						<option value="7d">7 days</option>
						<option value="all">All</option>
					</select>
				</div>
				<div>
					<label for="fetch-interval" class="block text-sm font-medium text-[var(--color-text-secondary)] mb-1">Fetch interval (min)</label>
					<input id="fetch-interval" type="number" bind:value={defaultFetchInterval} min="5" max="1440" class="w-full px-3 py-2.5 sm:py-2 border border-[var(--color-border)] rounded-[5px] text-sm bg-[var(--color-surface)] text-[var(--color-text)] focus:outline-none focus:ring-2 focus:ring-[var(--color-brand)]" />
				</div>
			</div>
		</div>

		<!-- Discord / Digest -->
		<div class="bg-[var(--color-surface)] rounded-[8px] border border-[var(--color-border)] p-4 mb-4">
			<h2 class="text-sm font-semibold text-[var(--color-text)] mb-1">Discord Notifications & Digest</h2>
			<p class="text-xs text-[var(--color-text-muted)] mb-4">Configure Discord webhooks for rule-matched notifications and the daily digest. AI summarisation is off; digests use source excerpts.</p>

			<div class="space-y-4">
				<div>
					<label for="discord-rules-webhook" class="block text-sm font-medium text-[var(--color-text-secondary)] mb-1">Rule Notifications Webhook</label>
					<div class="flex gap-2">
						<input
							id="discord-rules-webhook"
							type="url"
							bind:value={discordWebhookUrl}
							placeholder="https://discord.com/api/webhooks/..."
							class="flex-1 px-3 py-2 border border-[var(--color-border)] rounded-[5px] text-sm bg-[var(--color-surface)] text-[var(--color-text)] focus:outline-none focus:ring-2 focus:ring-[var(--color-brand)] font-mono"
						/>
						<button
							onclick={() => testDiscordWebhook(discordWebhookUrl)}
							disabled={testingWebhook || !discordWebhookUrl}
							class="px-3 py-2 border border-[var(--color-border)] rounded-[5px] text-sm text-[var(--color-text-secondary)] hover:bg-[var(--color-surface-alt)] disabled:opacity-50 transition-colors whitespace-nowrap"
						>Test</button>
					</div>
					<p class="mt-1 text-xs text-[var(--color-text-muted)]">Used by rules with "Notify Discord" action.</p>
				</div>

				<div class="pt-4 border-t border-[var(--color-border)]">
					<label for="discord-digest-webhook" class="block text-sm font-medium text-[var(--color-text-secondary)] mb-1">Daily Digest Webhook</label>
					<div class="flex gap-2">
						<input
							id="discord-digest-webhook"
							type="url"
							bind:value={discordDigestWebhookUrl}
							placeholder="https://discord.com/api/webhooks/..."
							class="flex-1 px-3 py-2 border border-[var(--color-border)] rounded-[5px] text-sm bg-[var(--color-surface)] text-[var(--color-text)] focus:outline-none focus:ring-2 focus:ring-[var(--color-brand)] font-mono"
						/>
						<button
							onclick={() => testDiscordWebhook(discordDigestWebhookUrl)}
							disabled={testingWebhook || !discordDigestWebhookUrl}
							class="px-3 py-2 border border-[var(--color-border)] rounded-[5px] text-sm text-[var(--color-text-secondary)] hover:bg-[var(--color-surface-alt)] disabled:opacity-50 transition-colors whitespace-nowrap"
						>Test</button>
					</div>
					<p class="mt-1 text-xs text-[var(--color-text-muted)]">Sent daily at 07:00 UTC. Leave blank to use the rule notifications webhook above.</p>
				</div>

				<div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
					<div>
						<label for="digest-hours" class="block text-sm font-medium text-[var(--color-text-secondary)] mb-1">Digest time window</label>
						<select id="digest-hours" bind:value={digestHours} class="w-full border border-[var(--color-border)] rounded-[5px] px-3 py-2 text-sm bg-[var(--color-surface)] text-[var(--color-text)]">
							<option value="12">12 hours</option>
							<option value="24">24 hours</option>
							<option value="48">48 hours</option>
						</select>
					</div>
					<div>
						<label for="digest-max" class="block text-sm font-medium text-[var(--color-text-secondary)] mb-1">Max items per category</label>
						<input id="digest-max" type="number" bind:value={digestMaxItems} min="1" max="10" class="w-full px-3 py-2 border border-[var(--color-border)] rounded-[5px] text-sm bg-[var(--color-surface)] text-[var(--color-text)] focus:outline-none focus:ring-2 focus:ring-[var(--color-brand)]" />
					</div>
				</div>

				<p class="text-sm text-[var(--color-text-muted)]">AI summarisation is disabled for articles, rules and digests.</p>

				<div class="flex flex-col sm:flex-row gap-2 pt-2">
					<button
						onclick={sendDigestNow}
						disabled={sendingDigest || (!discordDigestWebhookUrl && !discordWebhookUrl)}
						class="px-4 py-2 bg-[var(--color-purple)] text-white text-sm font-medium rounded-[5px] hover:opacity-90 disabled:opacity-50 transition-opacity flex items-center gap-2 justify-center"
					>
						{#if sendingDigest}
							<div class="animate-spin w-4 h-4 border-2 border-white border-t-transparent rounded-full"></div>
							Sending digest...
						{:else}
							Send digest now
						{/if}
					</button>
					{#if digestStatus}
						<span class="text-sm text-[var(--color-text-secondary)] self-center">{digestStatus}</span>
					{/if}
				</div>
			</div>
		</div>

		<div class="bg-[var(--color-surface)] rounded-[8px] border border-[var(--color-border)] p-4 mb-4">
			<h2 class="text-sm font-semibold text-[var(--color-text)] mb-1">Score Alerts</h2>
			<p class="text-xs text-[var(--color-text-muted)] mb-4">Push high-relevance items to Discord as they arrive (separate from the daily digest). Throttled per hour. Relevance is learned from your reading + 👍/👎 feedback.</p>

			<div class="space-y-4">
				<label class="flex items-center gap-2 text-sm text-[var(--color-text-secondary)]">
					<input type="checkbox" bind:checked={alertsEnabled} class="rounded" />
					Enable score alerts
				</label>

				<div>
					<label for="alerts-webhook" class="block text-sm font-medium text-[var(--color-text-secondary)] mb-1">Alerts Webhook</label>
					<div class="flex gap-2">
						<input
							id="alerts-webhook"
							type="url"
							bind:value={alertsWebhookUrl}
							placeholder="https://discord.com/api/webhooks/..."
							class="flex-1 px-3 py-2 border border-[var(--color-border)] rounded-[5px] text-sm bg-[var(--color-surface)] text-[var(--color-text)] focus:outline-none focus:ring-2 focus:ring-[var(--color-brand)] font-mono"
						/>
						<button
							onclick={() => testDiscordWebhook(alertsWebhookUrl)}
							disabled={testingWebhook || !alertsWebhookUrl}
							class="px-3 py-2 border border-[var(--color-border)] rounded-[5px] text-sm text-[var(--color-text-secondary)] hover:bg-[var(--color-surface-alt)] disabled:opacity-50 transition-colors whitespace-nowrap"
						>Test</button>
					</div>
					<p class="mt-1 text-xs text-[var(--color-text-muted)]">Use a separate channel for these — they're noisier than the daily digest. Falls back to the rule notifications webhook if blank.</p>
				</div>

				<div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
					<div>
						<label for="alerts-threshold" class="block text-sm font-medium text-[var(--color-text-secondary)] mb-1">Score threshold (0.0–1.0)</label>
						<input id="alerts-threshold" type="number" step="0.05" min="0" max="1" bind:value={alertsScoreThreshold} class="w-full px-3 py-2 border border-[var(--color-border)] rounded-[5px] text-sm bg-[var(--color-surface)] text-[var(--color-text)] focus:outline-none focus:ring-2 focus:ring-[var(--color-brand)]" />
						<p class="mt-1 text-xs text-[var(--color-text-muted)]">Only items scoring at or above this trigger a push. 0.7 is a sensible start.</p>
					</div>
					<div>
						<label for="alerts-max" class="block text-sm font-medium text-[var(--color-text-secondary)] mb-1">Max pushes per hour</label>
						<input id="alerts-max" type="number" min="1" max="50" bind:value={alertsMaxPerHour} class="w-full px-3 py-2 border border-[var(--color-border)] rounded-[5px] text-sm bg-[var(--color-surface)] text-[var(--color-text)] focus:outline-none focus:ring-2 focus:ring-[var(--color-brand)]" />
					</div>
				</div>
			</div>
		</div>

		<button
			onclick={handleSave}
			disabled={saving}
			class="w-full sm:w-auto px-5 py-3 sm:py-2 bg-[var(--color-brand)] text-white text-sm font-medium rounded-[5px] hover:bg-[var(--color-brand-dark)] disabled:opacity-50 transition-colors"
		>{saving ? 'Saving...' : 'Save Settings'}</button>
	{/if}
</div>
