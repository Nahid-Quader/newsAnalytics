// Mirrors backend/app/api/schemas.py.

export interface Page<T> {
  items: T[];
  page: number;
  page_size: number;
  total: number;
}

export interface Source {
  id: string;
  name: string;
  homepage: string;
  language: string;
  connector: string;
  endpoint: string;
  poll_minutes: number;
  active: boolean;
  full_text_in_feed: boolean;
  notes: string | null;
  terms_notes: string | null;
}

export type HealthStatus = "ok" | "warning" | "stale" | "failing" | "never_run" | "inactive";

export interface SourceHealth {
  source_id: string;
  name: string;
  active: boolean;
  status: HealthStatus;
  warnings: string[];
  last_run_at: string | null;
  last_run_status: string | null;
  last_success_at: string | null;
  consecutive_failures: number;
  recent_errors: { at: string; error: string | null; http_status: number | null }[];
  runs_total: number;
  runs_failed: number;
  articles_total: number;
  latest_published_at: string | null;
  last_new_article_at: string | null;
  last_run_items_seen: number | null;
}

export interface ArticleSummary {
  id: string;
  source_id: string;
  source_name: string;
  url: string;
  title: string;
  summary: string | null;
  language: string;
  section: string | null;
  author: string | null;
  published_at: string | null;
  first_seen_at: string;
  has_body: boolean;
  duplicate_of_id: string | null;
}

export interface Article extends ArticleSummary {
  external_id: string | null;
  url_normalized: string;
  canonical_url: string | null;
  body: string | null;
  body_source: string | null;
  section_source: string | null;
  categories: string[];
  image_url: string | null;
  published_at_raw: string | null;
  published_at_note: string | null;
  updated_at_raw: string | null;
  last_seen_at: string;
  last_updated_at: string;
  version: number;
  content_hash: string;
  duplicate_method: string | null;
  collection_method: string;
  ingestion_status: string;
  provenance: Record<string, unknown>;
}

export interface CountBy {
  key: string;
  count: number;
}

export interface Overview {
  generated_at: string;
  articles_total: number;
  duplicates_linked: number;
  sources_total: number;
  sources_active: number;
  sources_by_status: CountBy[];
  by_language: CountBy[];
  per_day: CountBy[];
  coverage: {
    source_id: string;
    name: string;
    language: string;
    articles: number;
    with_body: number;
    with_published_at: number;
    with_author: number;
    latest_published_at: string | null;
  }[];
  last_24h: {
    runs: number;
    succeeded: number;
    not_modified: number;
    failed: number;
    new_articles: number;
    updated_articles: number;
  };
}
