import { useEffect, useState, type FormEvent } from "react";
import { useApi } from "../api";
import { ErrorBox, Loading, Missing } from "../components";
import { fmtTime } from "../format";
import type { ArticleSummary, Page, Source } from "../types";

const FILTER_KEYS = ["q", "source", "language", "section", "date_from", "date_to"] as const;
type Filters = Record<(typeof FILTER_KEYS)[number], string>;
const PAGE_SIZE = 20;

function toHash(filters: Filters, page: number): string {
  const qs = new URLSearchParams();
  for (const k of FILTER_KEYS) if (filters[k]) qs.set(k, filters[k]);
  if (page > 1) qs.set("page", String(page));
  const s = qs.toString();
  return `#/articles${s ? `?${s}` : ""}`;
}

export default function ArticlesPage({ query }: { query: URLSearchParams }) {
  const applied = Object.fromEntries(FILTER_KEYS.map((k) => [k, query.get(k) ?? ""])) as Filters;
  const page = Math.max(1, Number(query.get("page") ?? 1));
  const [draft, setDraft] = useState<Filters>(applied);
  useEffect(() => setDraft(applied), [query.toString()]); // eslint-disable-line react-hooks/exhaustive-deps

  const sources = useApi<Source[]>("/sources");
  const result = useApi<Page<ArticleSummary>>("/articles", { ...applied, page, page_size: PAGE_SIZE });

  const submit = (e: FormEvent) => {
    e.preventDefault();
    window.location.hash = toHash(draft, 1);
  };
  const set = (k: keyof Filters) => (e: { target: { value: string } }) => setDraft({ ...draft, [k]: e.target.value });
  const pages = result.data ? Math.max(1, Math.ceil(result.data.total / PAGE_SIZE)) : 1;

  return (
    <>
      <h1>Articles</h1>
      <form className="filters card" onSubmit={submit}>
        <input className="grow" type="search" placeholder="Search title and text (Bengali or English)…"
               value={draft.q} onChange={set("q")} aria-label="Search" />
        <select value={draft.source} onChange={set("source")} aria-label="Source">
          <option value="">All sources</option>
          {(sources.data ?? []).map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
        </select>
        <select value={draft.language} onChange={set("language")} aria-label="Language">
          <option value="">All languages</option>
          <option value="bn">Bengali</option>
          <option value="en">English</option>
        </select>
        <input placeholder="Section (e.g. sport)" value={draft.section} onChange={set("section")} aria-label="Section" />
        <label className="date">From <input type="date" value={draft.date_from} onChange={set("date_from")} /></label>
        <label className="date">To <input type="date" value={draft.date_to} onChange={set("date_to")} /></label>
        <button type="submit">Apply</button>
        <a className="button-secondary" href="#/articles">Reset</a>
      </form>

      {result.error && <ErrorBox message={result.error} />}
      {result.loading && !result.data && <Loading />}
      {result.data && (
        <>
          <p className="muted">
            {result.data.total.toLocaleString()} article{result.data.total === 1 ? "" : "s"}
            {(applied.date_from || applied.date_to) && " · articles without a known publication time are hidden by the date filter"}
          </p>
          <ul className="article-list">
            {result.data.items.map((a) => (
              <li key={a.id} className="card article-row">
                <div className="article-meta">
                  <span className="pill">{a.source_name}</span>
                  {a.section && <span className="pill pill-light">{a.section}</span>}
                  <span className="muted small">{fmtTime(a.published_at)}</span>
                  {!a.has_body && <span className="pill pill-warn" title="Feed gave no article text">no body</span>}
                  {a.duplicate_of_id && <span className="pill pill-warn">duplicate</span>}
                </div>
                <a className="article-title" lang={a.language} href={`#/articles/${a.id}`}>{a.title}</a>
                <p className="excerpt" lang={a.language}>{a.summary ?? <Missing>no summary in feed</Missing>}</p>
              </li>
            ))}
          </ul>
          {result.data.total === 0 && <p className="muted">No articles match these filters.</p>}
          {pages > 1 && (
            <nav className="pager">
              <a className={page <= 1 ? "disabled" : ""} href={toHash(applied, page - 1)}>← Newer</a>
              <span>Page {page} of {pages}</span>
              <a className={page >= pages ? "disabled" : ""} href={toHash(applied, page + 1)}>Older →</a>
            </nav>
          )}
        </>
      )}
    </>
  );
}
