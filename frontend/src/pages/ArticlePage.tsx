import { useApi } from "../api";
import { ErrorBox, Loading, Missing } from "../components";
import { fmtTime } from "../format";
import type { Article } from "../types";

export default function ArticlePage({ id }: { id: string }) {
  const { data: a, error, loading } = useApi<Article>(`/articles/${encodeURIComponent(id)}`);
  if (loading && !a) return <Loading />;
  if (error) return <ErrorBox message={error} />;
  if (!a) return null;

  const paragraphs = a.body?.split(/\n\n+/) ?? [];
  const show = (v: string | null | undefined) => v ?? <Missing />;

  return (
    <div className="article-layout">
      <article className="card article-body">
        <p><a href="#/articles">← Back to articles</a></p>
        <div className="article-meta">
          <span className="pill">{a.source_name}</span>
          {a.section && <span className="pill pill-light">{a.section}</span>}
        </div>
        <h1 lang={a.language}>{a.title}</h1>
        <p className="muted">
          {show(a.author)} · {fmtTime(a.published_at)}
        </p>
        <p>
          <a className="button" href={a.url} target="_blank" rel="noreferrer">Read on {a.source_name} ↗</a>
        </p>
        {a.summary && <p className="lead" lang={a.language}>{a.summary}</p>}
        {paragraphs.length > 0
          ? paragraphs.map((p, i) => <p key={i} lang={a.language}>{p}</p>)
          : <p><Missing>The feed did not include article text for this item.</Missing></p>}
        {a.categories.length > 0 && (
          <div className="tags">{a.categories.map((c) => <span key={c} className="pill pill-light">{c}</span>)}</div>
        )}
      </article>

      <aside className="card article-side">
        <h2>Metadata &amp; provenance</h2>
        <dl className="kv">
          <dt>Article ID</dt><dd className="mono">{a.id}</dd>
          <dt>Original URL</dt><dd><a className="break" href={a.url} target="_blank" rel="noreferrer">{a.url}</a></dd>
          <dt>Canonical URL</dt><dd>{a.canonical_url ?? <Missing>not determined</Missing>}</dd>
          <dt>Feed GUID</dt><dd className="mono break">{show(a.external_id)}</dd>
          <dt>Language</dt><dd>{a.language}</dd>
          <dt>Section</dt><dd>{show(a.section)}{a.section_source && <span className="muted"> (from {a.section_source.replace("_", " ")})</span>}</dd>
          <dt>Published (raw)</dt><dd className="mono">{show(a.published_at_raw)}</dd>
          <dt>Published (UTC)</dt><dd>{a.published_at ?? <Missing>{a.published_at_note ?? "unknown"}</Missing>}</dd>
          <dt>Updated (raw)</dt><dd className="mono">{show(a.updated_at_raw)}</dd>
          <dt>First seen</dt><dd>{fmtTime(a.first_seen_at)}</dd>
          <dt>Last seen in feed</dt><dd>{fmtTime(a.last_seen_at)}</dd>
          <dt>Content version</dt><dd>{a.version} (last change {fmtTime(a.last_updated_at)})</dd>
          <dt>Body source</dt><dd>{show(a.body_source)}</dd>
          <dt>Status</dt><dd>{a.ingestion_status}</dd>
          <dt>Collected via</dt><dd>{a.collection_method}</dd>
          <dt>Duplicate of</dt>
          <dd>{a.duplicate_of_id ? <a href={`#/articles/${a.duplicate_of_id}`}>{a.duplicate_of_id}</a> : "–"}</dd>
          <dt>Content hash</dt><dd className="mono break">{a.content_hash.slice(0, 16)}…</dd>
        </dl>
        <details>
          <summary>Raw provenance</summary>
          <pre>{JSON.stringify(a.provenance, null, 2)}</pre>
        </details>
      </aside>
    </div>
  );
}
