// Browser fixtures only: never writes production state or calls an AI provider.
const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const origin = process.env.FEEDWIRE_TEST_ORIGIN || 'http://127.0.0.1:5188';

(async () => {
  const browser = await chromium.launch({ headless: true });
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
    page.setDefaultTimeout(10000);
    const errors = []; const writes = []; const requests = [];
    page.on('pageerror', error => errors.push(error.message));
    const categories = [{ id: 1, name: 'UK News', group_name: 'News', feed_count: 1, unread_count: 3 }];
    let failGroup = true;
    let failUsage = false;
    let usage = { requests: 3, known_cost_usd: .00015, unpriced: 1, tracking_since: null, pricing: {}, groups: [
      { provider: 'anthropic', model: 'claude-haiku-4-5-20251001', requests: 1, input_tokens: 100, output_tokens: 10, known_cost_usd: .00015, unpriced: 0, failed: 0, estimated: 1, missing_usage: 0 },
      { provider: 'openai', model: 'custom', requests: 2, input_tokens: 10, output_tokens: 5, known_cost_usd: 0, unpriced: 1, failed: 1, estimated: 0, missing_usage: 0 },
    ] };
    await page.route('**/api/**', async route => {
      const request = route.request(); const url = new URL(request.url()); const path = url.pathname;
      requests.push(path + url.search);
      const json = (data, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(data) });
      if (request.method() !== 'GET') {
        const data = request.postDataJSON(); writes.push({ path, data });
        if (path === '/api/categories/1') {
          if (failGroup) { failGroup = false; return json({ detail: 'Group could not be saved' }, 500); }
          Object.assign(categories[0], data); return json(categories[0]);
        }
        if (path === '/api/ai/pricing') { usage.pricing[data.provider + '/' + data.model] = data; return json({ ok: true }); }
        throw Error('Unexpected write ' + path);
      }
      if (path === '/api/categories') return json(categories);
      if (path === '/api/feeds') return json([]);
      if (path === '/api/items/unread-counts') return json({ total: 3, feeds: {} });
      if (path === '/api/items' || path === '/api/tags') return json([]);
      if (path === '/api/settings') return json({ settings: { ai_provider: 'anthropic' } });
      if (path === '/api/health') return json({ status: 'ok' });
      if (path === '/api/ai/providers') return json({ providers: [
        { id: 'anthropic', name: 'Anthropic', default_model: 'claude-haiku-4-5-20251001', needs_base_url: false, model_examples: [] },
        { id: 'openai', name: 'OpenAI', default_model: 'custom', needs_base_url: false, model_examples: [] },
      ] });
      if (path === '/api/ai/usage') return failUsage ? json({ detail: 'Usage unavailable' }, 500) : json(usage);
      throw Error('Unexpected read ' + path);
    });
    await page.goto(origin + '/feeds');
    const input = page.locator('#category-group-1');
    await input.fill('My reading');
    const save = page.locator('form').filter({ has: input }).getByRole('button', { name: 'Save', exact: true });
    await save.click();
    await page.getByText('Group could not be saved', { exact: true }).waitFor();
    assert.equal(await input.inputValue(), 'My reading');
    await save.click();
    await page.getByRole('link', { name: /My reading/ }).waitFor();
    assert.equal(writes.at(-1).data.group_name, 'My reading');
    await page.reload();
    assert.equal(await input.inputValue(), 'My reading');
    await page.getByRole('link', { name: /My reading/ }).click();
    await page.waitForFunction(() => document.querySelector('.fw-heading h1')?.textContent === 'My reading');
    assert(requests.some(request => request.includes('category_ids=1')));
    await page.goto(origin + '/settings');
    const panel = page.getByRole('region', { name: 'AI usage & cost' });
    await panel.getByText(/3 requests/).waitFor();
    assert(await panel.getByText(/unknown prices/).isVisible());
    assert(await panel.getByText('Includes estimates', { exact: true }).isVisible());
    await Promise.all([page.waitForResponse(response => response.url().includes('/ai/usage?days=7')), panel.getByLabel('Usage period').selectOption('7')]);
    await panel.getByText('Model prices', { exact: true }).click();
    await panel.getByLabel('Provider', { exact: true }).selectOption('openai');
    for (const [label, value] of [['Input', '1'], ['Output', '5'], ['Cached input', '.1'], ['Cache writes', '1']]) await panel.getByLabel(label, { exact: true }).fill(value);
    await panel.getByRole('button', { name: 'Save model prices' }).click();
    await panel.getByText('Prices saved for future requests').waitFor();
    assert.deepEqual(writes.at(-1).data, { provider: 'openai', model: 'custom', input: 1, output: 5, cache_read: .1, cache_write: 1 });
    failUsage = true;
    await panel.getByRole('button', { name: 'Refresh', exact: true }).click();
    await panel.getByRole('alert').waitFor();
    failUsage = false;
    usage = { ...usage, requests: 0, known_cost_usd: 0, unpriced: 0, groups: [] };
    await panel.getByRole('button', { name: 'Refresh', exact: true }).click();
    await panel.getByText('No AI requests recorded in this period.').waitFor();
    for (const route of ['/settings', '/feeds']) {
      await page.setViewportSize({ width: 390, height: 844 });
      await page.goto(origin + route);
      await page.waitForSelector(route === '/feeds' ? '#category-group-1' : '#ai-usage-heading');
      assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), route + ' overflows mobile');
      await page.screenshot({ path: '/tmp/feedwire-roadmap-' + route.slice(1) + '.png', fullPage: true });
    }
    assert.deepEqual(errors, []);
    console.log('Group editing, sidebar refresh/navigation, usage periods/errors/empty state, model pricing and mobile layout passed.');
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exit(1); });
