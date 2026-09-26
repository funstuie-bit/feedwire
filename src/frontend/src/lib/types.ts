export interface Category {
	id: number;
	name: string;
	sort_order: number;
	group_name: string | null;
	feed_count: number;
	unread_count: number;
}

export interface Feed {
	id: number;
	url: string;
	title: string | null;
	description: string | null;
	site_url: string | null;
	favicon_url: string | null;
	category_id: number | null;
	is_private: boolean;
	fetch_interval_minutes: number;
	last_fetched_at: string | null;
	last_error: string | null;
	error_count: number;
	item_count: number;
	unread_count: number;
	created_at: string;
}

export interface SimilarItem {
	id: number;
	feed_title: string | null;
	feed_id: number;
	link?: string | null;
}

export interface Tag {
	id: number;
	name: string;
	color: string;
}

export interface Item {
	id: number;
	feed_id: number;
	guid: string | null;
	title: string | null;
	link: string | null;
	content: string | null;
	cleaned_content: string | null;
	author: string | null;
	published_at: string | null;
	ai_summary: string | null;
	ai_entities: Record<string, string[]> | null;
	is_read: boolean;
	is_saved: boolean;
	is_hidden: boolean;
	tags: Tag[];
	matched_rules: number[];
	cluster_id: string | null;
	relevance_score: number;
	feedback: number;
	similar_items: SimilarItem[];
	is_paywalled: boolean;
	archive_url: string | null;
	feed_title: string | null;
	feed_favicon: string | null;
	created_at: string;
}

export interface Rule {
	id: number;
	name: string | null;
	match_expression: string;
	scope: string;
	match_whole_word: boolean;
	category_ids: number[];
	actions: string[];
	is_active: boolean;
	background_enabled: boolean;
	created_at: string;
}

export interface Note {
	id: number;
	item_id: number | null;
	title: string | null;
	content: string;
	item_title: string | null;
	created_at: string;
}

export interface Cluster {
	cluster_id: string;
	label: string;
	size: number;
	item_ids: number[];
}
