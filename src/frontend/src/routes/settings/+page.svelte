<script lang="ts">
	import { onMount } from 'svelte';
	import { getSettings, updateSettings, healthCheck, getAIUsage, updateAIPricing } from '$lib/api';
	import type { AIUsage } from '$lib/types';

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
	let usage = $state<AIUsage | null>(null);
	let usageDays = $state(30);
	let usageLoading = $state(false);
	let usageError = $state('');
	let pricingStatus = $state('');
	let savingPrice = $state(false);
	let priceProvider = $state('anthropic');
	let priceModel = $state('');
	let rates = $state<Record<string, number | undefined>>({ input: undefined, output: undefined, cache_read: undefined, cache_write: undefined });
	const rateFields = [{ key: 'input', label: 'Input' }, { key: 'output', label: 'Output' }, { key: 'cache_read', label: 'Cached input' }, { key: 'cache_write', label: 'Cache writes' }];
	const money = (value: number) => new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 6 }).format(value);
	let usageRequest = 0;

	async function loadUsage() {
		const request = ++usageRequest;
		usageLoading = true; usageError = '';
		try { const result = await getAIUsage(usageDays); if (request === usageRequest) usage = result; }
		catch (e: any) { if (request === usageRequest) usageError = e.message; }
		finally { if (request === usageRequest) usageLoading = false; }
	}
	function loadRate() {
		const rate = usage?.pricing[`${priceProvider}/${priceModel.trim()}`];
		rates = Object.fromEntries(rateFields.map(field => [field.key, rate ? Number(rate[field.key as keyof typeof rate]) : undefined]));
	}
	async function saveRate() {
		if (!priceModel.trim() || rateFields.some(field => rates[field.key] === undefined)) return;
		savingPrice = true; usageError = ''; pricingStatus = '';
		try {
			await updateAIPricing(priceProvider, priceModel.trim(), { input: rates.input!, output: rates.output!, cache_read: rates.cache_read!, cache_write: rates.cache_write! });
			await loadUsage(); pricingStatus = 'Prices saved for future requests';
		} catch (e: any) { usageError = e.message; }
		finally { savingPrice = false; }
	}

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
			priceProvider = aiProvider;
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
			await loadProviders();
			priceModel = models[priceProvider] || providers.find(p => p.id === priceProvider)?.default_model || '';
			await loadUsage(); loadRate();
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

		<section aria-labelledby="ai-usage-heading" class="bg-[var(--color-surface)] rounded-[8px] border border-[var(--color-border)] p-4 mb-4">
			<div class="flex flex-wrap items-center justify-between gap-3 mb-3">
				<h2 id="ai-usage-heading" class="text-sm font-semibold text-[var(--color-text)]">AI usage & cost</h2>
				<div class="flex items-center gap-2">
					<select aria-label="Usage period" bind:value={usageDays} onchange={loadUsage} class="px-2 py-2 border border-[var(--color-border)] rounded-[5px] text-sm bg-[var(--color-surface)] text-[var(--color-text)]"><option value={7}>Last 7 days</option><option value={30}>Last 30 days</option><option value={90}>Last 90 days</option></select>
					<button type="button" onclick={loadUsage} disabled={usageLoading} class="px-3 py-2 text-sm text-[var(--color-action)] disabled:opacity-50">Refresh</button>
				</div>
			</div>
			{#if usageError}<p role="alert" class="text-sm text-[var(--color-danger)] mb-3">{usageError}</p>{/if}
			{#if usage}
				<p class="text-sm text-[var(--color-text)] mb-2">{usage.requests.toLocaleString()} requests · Known cost {money(usage.known_cost_usd)}{usageLoading ? ' · Updating…' : ''}</p>
				<p class="text-xs text-[var(--color-text-muted)] mb-3">Costs include estimates where the provider does not report a price. {usage.unpriced ? `${usage.unpriced} requests have unknown prices and are excluded from the cost total.` : ''} Tracking starts with this release; earlier requests are not included.</p>
				{#if usage.groups.length}
					<div class="overflow-x-auto"><table class="w-full text-sm text-left">
						<thead class="text-xs text-[var(--color-text-muted)]"><tr><th class="py-2 pr-3">Provider / model</th><th class="py-2 pr-3">Requests</th><th class="py-2 pr-3">Input / output tokens</th><th class="py-2">Known cost</th></tr></thead>
						<tbody>{#each usage.groups as group}<tr class="border-t border-[var(--color-border)] text-[var(--color-text)]">
							<td class="py-3 pr-3 break-all">{group.provider}<span class="block text-xs text-[var(--color-text-muted)]">{group.model}</span></td>
							<td class="py-3 pr-3">{group.requests}{#if group.failed}<span class="block text-xs text-[var(--color-text-muted)]">{group.failed} failed</span>{/if}</td>
							<td class="py-3 pr-3">{group.input_tokens.toLocaleString()} / {group.output_tokens.toLocaleString()}{#if group.missing_usage}<span class="block text-xs text-[var(--color-text-muted)]">{group.missing_usage} missing token counts</span>{/if}</td>
							<td class="py-3">{group.unpriced === group.requests ? 'Unknown' : money(group.known_cost_usd)}<span class="block text-xs text-[var(--color-text-muted)]">{group.estimated ? 'Includes estimates' : ''}{group.unpriced ? ` · ${group.unpriced} unpriced` : ''}</span></td>
						</tr>{/each}</tbody>
					</table></div>
				{:else}<p class="text-sm text-[var(--color-text-muted)] mb-3">No AI requests recorded in this period.</p>{/if}
			{/if}
			<details class="mt-4 border-t border-[var(--color-border)] pt-3">
				<summary class="cursor-pointer text-sm text-[var(--color-action)]">Model prices</summary>
				<p class="text-xs text-[var(--color-text-muted)] my-3">USD per million tokens. Prices apply to future requests. Provider-reported costs take precedence. Ollama has no provider charge; unknown models stay unpriced.</p>
				<form onsubmit={(e) => { e.preventDefault(); saveRate(); }} class="space-y-3">
					<div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
						<div><label for="price-provider" class="block text-xs text-[var(--color-text-secondary)] mb-1">Provider</label><select id="price-provider" bind:value={priceProvider} onchange={() => { priceModel = models[priceProvider] || providers.find(p => p.id === priceProvider)?.default_model || ''; loadRate(); }} class="w-full px-3 py-2 bg-[var(--color-surface)] border border-[var(--color-border)] rounded-[5px] text-sm text-[var(--color-text)]">{#each providers as provider}<option value={provider.id}>{provider.name}</option>{/each}</select></div>
						<div><label for="price-model" class="block text-xs text-[var(--color-text-secondary)] mb-1">Exact model ID</label><input id="price-model" required maxlength="200" bind:value={priceModel} onchange={loadRate} class="w-full px-3 py-2 bg-[var(--color-surface)] border border-[var(--color-border)] rounded-[5px] text-sm text-[var(--color-text)]" /></div>
					</div>
					<div class="grid grid-cols-2 gap-3">{#each rateFields as field}<div><label for={'price-' + field.key} class="block text-xs text-[var(--color-text-secondary)] mb-1">{field.label}</label><input id={'price-' + field.key} type="number" min="0" max="10000" step="any" required bind:value={rates[field.key]} class="w-full min-w-0 px-3 py-2 bg-[var(--color-surface)] border border-[var(--color-border)] rounded-[5px] text-sm text-[var(--color-text)]" /></div>{/each}</div>
					<button type="submit" disabled={savingPrice} class="px-3 py-2 bg-[var(--color-brand)] text-white rounded-[5px] text-sm disabled:opacity-50">{savingPrice ? 'Saving…' : 'Save model prices'}</button>
					<p aria-live="polite" class="text-xs text-[var(--color-text-secondary)]">{pricingStatus}</p>
				</form>
			</details>
		</section>

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
