import { useApi } from "../api";
import { ErrorBox, Loading, Stat } from "../components";
import { fmtTime, pct } from "../format";
import type { Overview } from "../types";

export default function OverviewPage() {
  const { data, error, loading } = useApi<Overview>("/analytics/overview");
  if (loading && !data) return <Loading />;
  if (error) return <ErrorBox message={error} />;
  if (!data) return null;

  const healthy = data.sources_by_status.filter((s) => s.key === "ok").reduce((n, s) => n + s.count, 0);
  const maxDay = Math.max(1, ...data.per_day.map((d) => d.count));

  return (
    <>
      <h1>Overview</h1>
      <p className="muted">Generated {fmtTime(data.generated_at)}</p>

      <div className="stats">
        <Stat label="Articles collected" value={data.articles_total.toLocaleString()} />
        <Stat label="Sources healthy" value={`${healthy} / ${data.sources_active}`}
              hint={data.sources_by_status.map((s) => `${s.count} ${s.key.replace("_", " ")}`).join(" · ")} />
        <Stat label="New in last 24 h" value={data.last_24h.new_articles}
              hint={`${data.last_24h.updated_articles} updated`} />
        <Stat label="Fetch runs, last 24 h" value={data.last_24h.runs}
              hint={`${data.last_24h.failed} failed · ${data.last_24h.not_modified} not modified`} />
        <Stat label="Linked duplicates" value={data.duplicates_linked} hint="same text in another record" />
      </div>

      <section className="card">
        <h2>Articles per day <span className="muted small">(by publication date, UTC, last 14 days)</span></h2>
        <div className="bars" role="img" aria-label="Articles per day">
          {data.per_day.map((d) => (
            <div className="bar-col" key={d.key} title={`${d.key}: ${d.count}`}>
              <div className="bar-value">{d.count || ""}</div>
              <div className="bar" style={{ height: `${(100 * d.count) / maxDay}%` }} />
              <div className="bar-label">{d.key.slice(5)}</div>
            </div>
          ))}
        </div>
        <p className="muted small">
          Counts only reflect what the feeds exposed while collection was running; they are not a measure of
          total output.
        </p>
      </section>

      <section className="card">
        <h2>Source coverage</h2>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Source</th><th>Lang</th><th className="num">Articles</th><th className="num">With body</th>
                <th className="num">With date</th><th className="num">With author</th><th>Latest article</th>
              </tr>
            </thead>
            <tbody>
              {data.coverage.map((c) => (
                <tr key={c.source_id}>
                  <td><a href={`#/articles?source=${c.source_id}`}>{c.name}</a></td>
                  <td>{c.language}</td>
                  <td className="num">{c.articles}</td>
                  <td className="num">{pct(c.with_body, c.articles)}</td>
                  <td className="num">{pct(c.with_published_at, c.articles)}</td>
                  <td className="num">{pct(c.with_author, c.articles)}</td>
                  <td>{fmtTime(c.latest_published_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </>
  );
}
