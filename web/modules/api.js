// ── API — fetch helpers ────────────────────────────────────────────
import { t } from './i18n.js';

const API_BASE = window.ELECTRIFYSZU_API_BASE || "";
const IS_STATIC_PAGE =
  location.protocol === "file:" ||
  location.hostname.endsWith(".github.io") ||
  location.hostname === "github.io";

const REQUEST_TIMEOUT_MS = 30000;

export function canUseBackend() {
  return Boolean(API_BASE) || !IS_STATIC_PAGE;
}

export function apiUrl(path) {
  if (!API_BASE) return path;
  return new URL(path, API_BASE).toString();
}

function fetchWithTimeout(url, options = {}) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
  return fetch(url, { ...options, signal: controller.signal }).finally(() => clearTimeout(timer));
}

export async function fetchJson(url) {
  const response = await fetchWithTimeout(url);
  const contentType = (response.headers.get("content-type") || "").toLowerCase();
  if (!contentType.includes("application/json")) {
    throw new Error(t("error.nonJson"));
  }
  const payload = await response.json();
  if (!response.ok) {
    const err = new Error(payload.hint || payload.error || t("error.requestFailed"));
    err.status = response.status;
    throw err;
  }
  return payload;
}

export async function postJson(url, data) {
  const response = await fetchWithTimeout(url, {
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
    const err = new Error(payload.hint || payload.error || t("error.requestFailed"));
    err.status = response.status;
    throw err;
  }
  return payload;
}
