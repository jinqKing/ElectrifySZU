// ── GitHub — star counter ─────────────────────────────────────────
import { canUseBackend, apiUrl, fetchJson } from './api.js';

export async function loadGithubStars() {
  const badge = document.querySelector("#starBadge");
  if (!badge) return;
  const isStatic =
    location.protocol === "file:" ||
    location.hostname.endsWith(".github.io") ||
    location.hostname === "github.io";
  if (isStatic) return;
  try {
    const res = await fetchJson(apiUrl("/api/github-stars"));
    const num = Number(res.stars) || 0;
    badge.textContent = `★ ${num >= 1000 ? `${(num / 1000).toFixed(1)}k+` : String(num)}`;
  } catch { /* silent */ }
}
