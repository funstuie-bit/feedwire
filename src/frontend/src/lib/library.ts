import type { Category, Feed } from './types';

export interface Topic { name: string; ids: number[]; count: number }
export interface Section { name: string; symbol: string; topics: Topic[]; ids: number[]; count: number }

export const sectionNames = ['News', 'Technology', 'Sport', 'Culture', 'Business', 'Social', 'Other'];
const symbols = ['◷', '⌘', '◉', '◈', '▥', '＠', '⋯'];
const mergedNames: Record<string, string> = {
  'UK News': 'UK news', 'UK News (Neutral to Left)': 'UK news',
  'World News': 'World & Europe', 'Europe and World News': 'World & Europe',
  'Tech': 'Tech news', 'Tech News': 'Tech news',
};

// Presentation groups preserve category IDs, rule scopes and subscription history.
export function categoryGroup(cat: Category): string {
  const group = cat.group_name?.trim();
  return ({ Tech: 'Technology', Sports: 'Sport', Entertainment: 'Culture' } as Record<string, string>)[group || '']
    || group || (cat.name === 'Finance / Markets' ? 'Business' : 'Other');
}

export function buildLibrary(categories: Category[]): Section[] {
  const sections: Section[] = sectionNames.map((name, i) => ({ name, symbol: symbols[i], topics: [], ids: [], count: 0 }));
  for (const cat of categories.filter(c => c.feed_count > 0)) {
    const group = categoryGroup(cat);
    let section = sections.find(s => s.name === group);
    if (!section) {
      section = { name: group, symbol: '⋯', topics: [], ids: [], count: 0 };
      sections.push(section);
    }
    const name = mergedNames[cat.name] || cat.name;
    let topic = section.topics.find(t => t.name === name);
    if (!topic) { topic = { name, ids: [], count: 0 }; section.topics.push(topic); }
    topic.ids.push(cat.id); topic.count += cat.unread_count;
    section.ids.push(cat.id); section.count += cat.unread_count;
  }
  for (const s of sections) s.topics.sort((a, b) => a.name.localeCompare(b.name));
  return sections.filter(s => s.ids.length);
}

export function feedLabel(feed: Pick<Feed, 'title' | 'url'>): string {
  if (feed.title === 'BBC Sport') {
    return 'BBC · ' + (feed.url.includes('/formula1/') ? 'F1' : feed.url.includes('/rugby-union/') ? 'Rugby' : 'All sport');
  }
  if (feed.title === 'CBS Sports Headlines') {
    return 'CBS · ' + (feed.url.includes('/mlb/') ? 'MLB' : feed.url.includes('/nba/') ? 'NBA' : 'Sport');
  }
  return feed.title || feed.url;
}

export function articleUrl(link: string | null | undefined): string | null {
  if (!link) return null;
  try { const url = new URL(link); return ['http:', 'https:'].includes(url.protocol) ? url.href : null; }
  catch { return null; }
}
