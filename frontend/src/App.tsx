import { useEffect, useState } from "react";
import OverviewPage from "./pages/OverviewPage";
import SourcesPage from "./pages/SourcesPage";
import ArticlesPage from "./pages/ArticlesPage";
import ArticlePage from "./pages/ArticlePage";

// Minimal hash router: #/, #/sources, #/articles?..., #/articles/<id>
function useHashRoute(): { path: string; query: URLSearchParams } {
  const read = () => {
    const raw = window.location.hash.replace(/^#/, "") || "/";
    const [path, qs = ""] = raw.split("?");
    return { path, query: new URLSearchParams(qs) };
  };
  const [route, setRoute] = useState(read);
  useEffect(() => {
    const onChange = () => setRoute(read());
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  }, []);
  return route;
}

const NAV = [
  { href: "#/", label: "Overview", match: (p: string) => p === "/" },
  { href: "#/sources", label: "Sources", match: (p: string) => p.startsWith("/sources") },
  { href: "#/articles", label: "Articles", match: (p: string) => p.startsWith("/articles") },
];

export default function App() {
  const { path, query } = useHashRoute();
  const articleId = path.match(/^\/articles\/(.+)$/)?.[1];

  let page;
  if (articleId) page = <ArticlePage id={decodeURIComponent(articleId)} />;
  else if (path.startsWith("/articles")) page = <ArticlesPage query={query} />;
  else if (path.startsWith("/sources")) page = <SourcesPage />;
  else page = <OverviewPage />;

  return (
    <div className="shell">
      <header className="topbar">
        <a className="brand" href="#/">
          BD News Monitor <span className="phase">Phase 1</span>
        </a>
        <nav>
          {NAV.map((n) => (
            <a key={n.href} href={n.href} className={n.match(path) ? "active" : ""}>
              {n.label}
            </a>
          ))}
        </nav>
      </header>
      <main>{page}</main>
      <footer className="footer">
        Articles belong to their publishers. Full text is kept for private analysis; always link to the original.
      </footer>
    </div>
  );
}
