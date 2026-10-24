import { useEffect, useState } from "react";

const BASE = "/api";

export async function getJson<T>(path: string, params?: Record<string, string | number | undefined>): Promise<T> {
  const query = new URLSearchParams();
  for (const [k, v] of Object.entries(params ?? {})) {
    if (v !== undefined && v !== "") query.set(k, String(v));
  }
  const qs = query.toString();
  const res = await fetch(`${BASE}${path}${qs ? `?${qs}` : ""}`);
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`${res.status} ${res.statusText}: ${detail.slice(0, 200)}`);
  }
  return res.json() as Promise<T>;
}

export interface Loadable<T> {
  data: T | null;
  error: string | null;
  loading: boolean;
}

/** Fetch `path` whenever `key` changes. */
export function useApi<T>(path: string, params?: Record<string, string | number | undefined>): Loadable<T> {
  const key = path + JSON.stringify(params ?? {});
  const [state, setState] = useState<Loadable<T>>({ data: null, error: null, loading: true });
  useEffect(() => {
    let cancelled = false;
    setState((s) => ({ ...s, loading: true, error: null }));
    getJson<T>(path, params)
      .then((data) => !cancelled && setState({ data, error: null, loading: false }))
      .catch((e: Error) => !cancelled && setState({ data: null, error: e.message, loading: false }));
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);
  return state;
}
