const BASE = '/api';
import type { AIUsage, AIRate } from './types';

async function request<T>(path: string, options?: RequestInit): Promise<T> {
	const res = await fetch(`${BASE}${path}`, {
		headers: { 'Content-Type': 'application/json', ...options?.headers },
		...options,
	});
	if (!res.ok) {
		const error = await res.json().catch(() => ({ detail: res.statusText }));
		throw new Error(error.detail || `Request failed: ${res.status}`);
	}
	return res.json();
}

// Feeds
export const getFeeds = () => request<any[]>('/feeds');
export const addFeed = (url: string, category_id?: number) =>
	request<any>('/feeds', {
		method: 'POST',
		body: JSON.stringify({ url, category_id }),
	});
export const addSyntheticFeed = (page_url: string, category_id?: number) =>
	request<any>('/feeds/synthetic', {
		method: 'POST',
		body: JSON.stringify({ page_url, category_id }),
	});
export const deleteFeed = (id: number) =>
	request<any>(`/feeds/${id}`, { method: 'DELETE' });
export const updateFeed = (id: number, data: Record<string, any>) =>
	request<any>(`/feeds/${id}`, { method: 'PATCH', body: JSON.stringify(data) });
export const refreshFeed = (id: number) =>
	request<any>(`/feeds/${id}/refresh`, { method: 'POST' });
export const importOPML = (content: string) =>
	request<any>('/feeds/import-opml', {
		method: 'POST',
		body: JSON.stringify({ content }),
	});
export const exportOPML = () => fetch(`${BASE}/feeds/export-opml`);

// Items
export const getItems = (params: Record<string, string>) => {
	const qs = new URLSearchParams(params).toString();
	return request<any[]>(`/items?${qs}`);
};
export const getItem = (id: number) => request<any>(`/items/${id}`);
export const getReadable = (id: number) =>
	request<{ content: string }>(`/items/${id}/readable`);
export const updateItem = (id: number, data: Record<string, any>) =>
	request<any>(`/items/${id}`, {
		method: 'PATCH',
		body: JSON.stringify(data),
	});
export const bulkUpdateItems = (item_ids: number[], data: Record<string, any>) =>
	request<any>('/items/bulk-update', {
		method: 'POST',
		body: JSON.stringify({ item_ids, ...data }),
	});
export const markAllRead = (params?: Record<string, any>) =>
	request<any>('/items/mark-all-read', {
		method: 'POST',
		body: JSON.stringify(params || {}),
	});
export const getUnreadCounts = () =>
	request<{ feeds: Record<string, number>; total: number }>('/items/unread-counts');
export const getClusters = (time_window: string = '24h') =>
	request<any[]>(`/items/clusters?time_window=${time_window}`);

// Categories
export const getCategories = () => request<any[]>('/categories');
export const createCategory = (name: string) =>
	request<any>('/categories', {
		method: 'POST',
		body: JSON.stringify({ name }),
	});
export const updateCategory = (id: number, data: { name?: string; sort_order?: number; group_name?: string | null }) =>
	request<any>(`/categories/${id}`, {
		method: 'PATCH',
		body: JSON.stringify(data),
	});

export const getAIUsage = (days: number = 30) => request<AIUsage>(`/ai/usage?days=${days}`);
export const updateAIPricing = (provider: string, model: string, rates: AIRate) =>
	request<{ ok: boolean }>('/ai/pricing', { method: 'PATCH', body: JSON.stringify({ provider, model, ...rates }) });
export const deleteCategory = (id: number) =>
	request<any>(`/categories/${id}`, { method: 'DELETE' });

// Rules
export const getRules = () => request<any[]>('/rules');
export const createRule = (data: Record<string, any>) =>
	request<any>('/rules', { method: 'POST', body: JSON.stringify(data) });
export const updateRule = (id: number, data: Record<string, any>) =>
	request<any>(`/rules/${id}`, { method: 'PATCH', body: JSON.stringify(data) });
export const deleteRule = (id: number) =>
	request<any>(`/rules/${id}`, { method: 'DELETE' });

// Notes
export const getNotes = () => request<any[]>('/notes');
export const createNote = (data: Record<string, any>) =>
	request<any>('/notes', { method: 'POST', body: JSON.stringify(data) });
export const deleteNote = (id: number) =>
	request<any>(`/notes/${id}`, { method: 'DELETE' });

// Tags
export const getTags = () => request<any[]>('/tags');
export const createTag = (name: string, color: string = '#6366f1') =>
	request<any>('/tags', { method: 'POST', body: JSON.stringify({ name, color }) });
export const deleteTag = (id: number) =>
	request<any>(`/tags/${id}`, { method: 'DELETE' });
export const addTagToItem = (itemId: number, tagId: number) =>
	request<any>(`/tags/items/${itemId}/${tagId}`, { method: 'POST' });
export const removeTagFromItem = (itemId: number, tagId: number) =>
	request<any>(`/tags/items/${itemId}/${tagId}`, { method: 'DELETE' });

// Feed health
export const getFeedHealth = () => request<any[]>('/feeds/health');

// AI
export const processAI = (item_id: number, action: string) =>
	request<any>('/ai/process', {
		method: 'POST',
		body: JSON.stringify({ item_id, action }),
	});

// Settings
export const getSettings = () => request<{ settings: Record<string, string> }>('/settings');
export const updateSettings = (updates: { key: string; value: string }[]) =>
	request<any>('/settings', {
		method: 'PATCH',
		body: JSON.stringify(updates),
	});

// Health
export const healthCheck = () => request<any>('/health');

// Favicon fallback
export function getFaviconUrl(url: string | null | undefined): string {
	if (!url) return '';
	try {
		const parsed = new URL(url);
		return `https://www.google.com/s2/favicons?domain=${parsed.hostname}&sz=32`;
	} catch {
		return url;
	}
}
