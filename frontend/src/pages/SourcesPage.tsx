import { useApi } from "../api";
import { ErrorBox, Loading, StatusBadge } from "../components";
import { fmtTime, timeAgo } from "../format";
import type { Source, SourceHealth } from "../types";

export default function SourcesPage() {
  const sources = useApi<Source[]>("/sources");
  const health = useApi<SourceHealth[]>("/sources/health");
  if ((sources.loading && !sources.data) || (health.loading && !health.data)) return <Loading />;
  const error = sources.error ?? health.error;
  if (error) return <ErrorBox message={error} />;

  const byId = new Map((health.data ?? []).map((h) => [h.source_id, h]));

  return (
    <>
      <h1>Sources</h1>
      <p className="muted">
        Configured in <code>config/sources.yaml</code>. Only sources verified to be fresh and to carry full text are
        enabled; see <code>research/SOURCES.md</code>.
      </p>
      <div className="source-grid">
        {(sources.data ?? []).map((s) => {
          const h = byId.get(s.id);
          return (
            <article className="card source-card" key={s.id}>
              <header className="source-head">
                <div>
                  <h2>{s.name}</h2>
                  <a className="muted small" href={s.homepage} target="_blank" rel="noreferrer">{s.homepage}</a>
                </div>
                {h && <StatusBadge status={h.status} />}
              </header>

              <dl className="kv">
                <dt>Language</dt><dd>{s.language === "bn" ? "Bengali" : "English"}</dd>
                <dt>Access</dt><dd>{s.connector.toUpperCase()} · every {s.poll_minutes} min</dd>
                <dt>Endpoint</dt>
                <dd><a href={s.endpoint} target="_blank" rel="noreferrer" className="break">{s.endpoint}</a></dd>
                <dt>Full text in feed</dt><dd>{s.full_text_in_feed ? "yes" : "no"}</dd>
                {h && (
                  <>
                    <dt>Last success</dt><dd title={fmtTime(h.last_success_at)}>{timeAgo(h.last_success_at)}</dd>
                    <dt>Last run</dt>
                    <dd>{h.last_run_status ?? "–"} · {timeAgo(h.last_run_at)}
                      {h.last_run_items_seen !== null && ` · ${h.last_run_items_seen} items in feed`}</dd>
                    <dt>Articles</dt>
                    <dd><a href={`#/articles?source=${s.id}`}>{h.articles_total}</a> · latest {fmtTime(h.latest_published_at)}</dd>
                    <dt>Runs</dt><dd>{h.runs_total} total · {h.runs_failed} failed</dd>
                  </>
                )}
              </dl>

              {s.notes && <p className="small muted">{s.notes}</p>}
              {h && h.warnings.length > 0 && (
                <ul className="warnings">{h.warnings.map((w) => <li key={w}>{w}</li>)}</ul>
              )}
              {h && h.recent_errors.length > 0 && (
                <details>
                  <summary>Recent errors ({h.recent_errors.length})</summary>
                  <ul className="errors">
                    {h.recent_errors.map((e, i) => (
                      <li key={i}><span className="muted">{fmtTime(e.at)}</span> {e.error}</li>
                    ))}
                  </ul>
                </details>
              )}
            </article>
          );
        })}
      </div>
    </>
  );
}
