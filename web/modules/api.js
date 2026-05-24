// ── API — fetch helpers ────────────────────────────────────────────
import { t } from './i18n.js';

const API_BASE = window.ELECTRIFYSZU_API_BASE || "";
const IS_STATIC_PAGE =
  location.protocol === "file:" ||
  location.hostname.endsWith(".github.io") ||
  location.hostname === "github.io";

export function canUseBackend() {
  return Boolean(API_BASE) || !IS_STATIC_PAGE;
}

export function apiUrl(path) {
  if (!API_BASE) return path;
  return new URL(path, API_BASE).toString();
}

export async function fetchJson(url) {
  const response = await fetch(url);
  const contentType = (response.headers.get("content-type") || "").toLowerCase();
  if (!contentType.includes("application/json")) {
    throw new Error(t("error.nonJson"));
  }
  const payload = await response.json();
  if (!response.ok) {
    throw new Error(payload.hint || payload.error || t("error.requestFailed"));
  }
  return payload;
}

export async function postJson(url, data) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  const contentType = (response.headers.get("content-type") || "").toLowerCase();
  if (!contentType.includes("application/json")) {
    throw new Error(t("error.nonJson"));
  }
  const payload = await response.json();
  if (!response.ok) {
    throw new Error(payload.hint || payload.error || t("error.requestFailed"));
  }
  return payload;
}
