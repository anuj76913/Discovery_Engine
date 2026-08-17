// `toLocaleString()` with no explicit locale falls back to the runtime's
// default locale — which differs between the Node.js SSR process and the
// browser, producing a React hydration mismatch. A fixed locale keeps
// server and client output identical for both dates and grouped numbers.
export function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleString("en-US", {
    dateStyle: "medium",
    timeStyle: "short",
  });
}

export function formatNumber(value: number): string {
  return value.toLocaleString("en-US");
}
