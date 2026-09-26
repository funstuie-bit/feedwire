// Run against the built frontend with Playwright installed. All API calls are
// intercepted: this check never writes to production or invokes an AI provider.
const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const origin = process.env.FEEDWIRE_TEST_ORIGIN || 'http://127.0.0.1:5188';

(async () => {
  const browser = await chromium.launch({ headless: true, args: ['--no-sandbox'] });
  try {
    const page = await browser.newPage({ viewport: { width: 1824, height: 1100 } });
    page.setDefaultTimeout(10000);
    const errors = []; const requests = []; const writes = [];
    page.on('pageerror', e => errors.push(e.message));
    const categories = [
      { id: 3, name: 'UK News', group_name: 'News', feed_count: 1, unread_count: 20 },
      { id: 11, name: 'UK News (Neutral to Left)', group_name: 'News', feed_count: 1, unread_count: 20 },
      { id: 9, name: 'Entertainment', group_name: 'Entertainment', feed_count: 1, unread_count: 10 },
      { id: 8, name: 'Sports', group_name: 'Sports', feed_count: 0, unread_count: 0 },
    ];
    const feeds = categories.filter(c => c.feed_count).map(c => ({ id: c.id, category_id: c.id, title: c.id === 9 ? 'TheWrap' : 'News source ' + c.id, url: 'https://example.org/feed/' + c.id, unread_count: 20 }));
    const items = Array.from({ length: 35 }, (_, i) => ({
      id: i + 1, feed_id: feeds[i % feeds.length].id, title: i ? 'Test article number ' + (i + 1) : 'SNL promotes Keri Powers and Rebecca Schwartz',
      link: 'https://example.org/articles/story-' + (i + 1) + '?edition=uk',
      content: '<p>' + 'Publisher article text. '.repeat(40) + '</p><a href="/related-story">Related article</a><img src=x onerror="window.badScript=true"><script>window.badScript=true</script>',
      created_at: new Date().toISOString(), published_at: null, author: 'Writer', is_read: false, is_saved: i === 2,
      is_hidden: false, feedback: 0, tags: [], similar_items: i ? [] : [{ id: 2, feed_id: 11, feed_title: 'Alternative publisher', link: 'https://other.example.org/news/snl-story' }],
      ai_summary: 'Old summary that must not be displayed', ai_entities: null,
    }));
    await page.route('**/api/**', async route => {
      const req = route.request(), url = new URL(req.url()), path = url.pathname;
      requests.push(path + url.search);
      const json = data => route.fulfill({ contentType: 'application/json', body: JSON.stringify(data) });
      if (req.method() !== 'GET') {
        writes.push({ path, data: req.postDataJSON() });
        const current = items.find(i => path === '/api/items/' + i.id);
        if (current) Object.assign(current, req.postDataJSON());
        return json(current || { ok: true });
      }
      if (path === '/api/feeds') return json(feeds);
      if (path === '/api/categories') return json(categories);
      if (path === '/api/items/unread-counts') return json({ total: 50, feeds: {} });
      if (path === '/api/tags') return json([]);
      if (path === '/api/items') {
        let result = items.filter(i => !i.is_hidden);
        if (url.searchParams.get('is_saved')) result = result.filter(i => i.is_saved);
        if (url.searchParams.get('unread_only')) result = result.filter(i => !i.is_read);
        if (url.searchParams.get('search')) result = result.filter(i => i.title.toLowerCase().includes(url.searchParams.get('search').toLowerCase()));
        if (url.searchParams.get('category_ids')) { const ids = url.searchParams.get('category_ids').split(',').map(Number); result = result.filter(i => ids.includes(i.feed_id)); }
        if (+url.searchParams.get('offset') > 0) result = [];
        return json(result);
      }
      const current = items.find(i => path === '/api/items/' + i.id);
      if (current) return json(current);
      throw new Error('Unexpected API route ' + path);
    });
    await page.goto(origin);
    await page.waitForSelector('.fw-story');
    // Both themes must cover navigation as well as the reader. Check actual
    // rendered colours, including white-on-brand management buttons.
    for (const mode of ['dark', 'light']) {
      if (mode === 'light') await page.getByRole('button', { name: 'Switch to light theme' }).click();
      const colours = await page.evaluate(() => {
        const style = getComputedStyle(document.documentElement);
        const css = name => style.getPropertyValue(name).trim();
        return {
          text: css('--color-text'), muted: css('--color-text-muted'), action: css('--color-action'),
          surface: css('--color-surface-alt'), sidebar: css('--fw-sidebar'), brand: css('--color-brand'),
          sidebarRendered: getComputedStyle(document.querySelector('.fw-sidebar')).backgroundColor,
          titleRendered: getComputedStyle(document.querySelector('.fw-story-title')).color,
        };
      });
      const channels = hex => hex.slice(1).match(/../g).map(x => parseInt(x, 16));
      const rgb = hex => `rgb(${channels(hex).join(', ')})`;
      const luminance = hex => channels(hex).map(x => x / 255).map(x => x <= .04045 ? x / 12.92 : ((x + .055) / 1.055) ** 2.4).reduce((sum, x, i) => sum + x * [.2126, .7152, .0722][i], 0);
      const contrast = (a, b) => { const x = luminance(a), y = luminance(b); return (Math.max(x, y) + .05) / (Math.min(x, y) + .05); };
      for (const foreground of ['text', 'muted', 'action']) {
        for (const background of ['surface', 'sidebar']) assert(contrast(colours[foreground], colours[background]) >= 4.5, `${mode}: ${foreground} on ${background}`);
      }
      assert(contrast('#ffffff', colours.brand) >= 4.5, `${mode}: filled button contrast`);
      assert.equal(colours.sidebarRendered, rgb(colours.sidebar));
      assert.equal(colours.titleRendered, rgb(colours.text));
    }
    await page.reload();
    await page.waitForSelector('.fw-story');
    assert.equal(await page.evaluate(() => document.documentElement.classList.contains('dark')), false);
    await page.getByRole('button', { name: 'Switch to dark theme' }).click();
    assert.equal(await page.locator('.fw-story').count(), 35);
    assert.equal(await page.locator('.fw-reader').count(), 0);
    assert.equal(await page.locator('.fw-topics').count(), 0);
    await page.locator('[data-story="1"]').click();
    assert.equal(await page.getByRole('link', { name: 'Open original' }).getAttribute('href'), items[0].link);
    assert.equal(await page.locator('.fw-article-text a').getAttribute('href'), 'https://example.org/related-story');
    assert.equal(await page.locator('.fw-reader').getByText('Old summary that must not be displayed').count(), 0);
    assert.equal(await page.locator('.fw-reader').getByText(/summari[sz]/i).count(), 0);
    assert.equal(await page.evaluate(() => window.badScript), undefined);
    await page.locator('.fw-also summary').click();
    assert.equal(await page.getByRole('link', { name: 'Open article' }).getAttribute('href'), 'https://other.example.org/news/snl-story');
    await page.getByRole('button', { name: 'Focus view' }).click();
    assert.equal(await page.locator('.fw-inbox').isVisible(), false);
    await page.getByRole('button', { name: 'Show story list' }).click();
    await page.getByRole('button', { name: '☆ Save', exact: true }).click();
    await page.waitForFunction(() => document.querySelector('.fw-reader-actions button[aria-pressed="true"]'));
    await page.keyboard.press('Escape');
    assert.equal(await page.locator('.fw-reader').count(), 0);
    await page.getByRole('button', { name: 'Expand News', exact: true }).click();
    assert.equal(await page.getByRole('link', { name: /^UK news/ }).count(), 1);
    await page.getByRole('link', { name: /^UK news/ }).click();
    await page.waitForFunction(() => document.querySelector('.fw-heading h1')?.textContent === 'UK news');
    await page.waitForTimeout(150);
    assert(requests.some(r => r.includes('category_ids=3%2C11')));
    assert.equal(await page.locator('.fw-story').count(), 24);
    await page.locator('.fw-nav').filter({ hasText: 'Saved for later' }).click();
    await page.waitForFunction(() => document.querySelectorAll('.fw-story').length === 2);
    assert(requests.some(r => r.includes('is_saved=true') && r.includes('time_window=all')));
    await page.locator('.fw-brand').click();
    await page.waitForFunction(() => document.querySelectorAll('.fw-story').length === 35);
    await page.setViewportSize({ width: 390, height: 844 });
    await page.locator('.fw-inbox').evaluate(el => el.scrollTop = 950);
    const before = await page.locator('.fw-inbox').evaluate(el => el.scrollTop);
    // Click a visible row without Playwright scrolling the list for us.
    await page.evaluate(() => { const rows = [...document.querySelectorAll('.fw-story')]; rows.find(el => { const r = el.getBoundingClientRect(); return r.top > 60 && r.bottom < 790; }).click(); });
    await page.waitForSelector('.fw-reader');
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
    await page.getByRole('button', { name: '← Inbox', exact: true }).click();
    assert.equal(await page.locator('.fw-inbox').evaluate(el => el.scrollTop), before);
    await page.getByRole('button', { name: 'Open navigation' }).click();
    assert.equal(await page.locator('.fw-sidebar').isVisible(), true);
    await page.getByRole('button', { name: 'Close navigation' }).click({ position: { x: 350, y: 200 } });
    assert(!requests.some(r => r.startsWith('/api/ai')));
    assert(!writes.some(w => w.path.includes('mark-all-read')));
    assert.deepEqual(errors, []);
    console.log('PASS: light/dark contrast and persistence, real article links, alternate coverage, disabled summary UI, safe content, focus, save, grouped category filtering, saved view, mobile scroll preservation and navigation.');
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exit(1); });
