// ── Likes — like system ────────────────────────────────────────────
import { t } from './i18n.js';
import { LIKE_ID_KEY } from './state.js';
import { canUseBackend, apiUrl, fetchJson, postJson } from './api.js';

const $ = (s) => document.querySelector(s);

export async function initLike() {
  const likeBtn = $("#likeButton");
  const likeCt = $("#likeCount");
  const userCt = $("#userCount");
  if (!canUseBackend() || !likeBtn || !likeCt) return;

  try {
    const stats = await fetchJson(apiUrl("/api/stats"));
    updateCounts(stats.data.likes, stats.data.users);
  } catch { /* silent */ }

  const likeId = localStorage.getItem(LIKE_ID_KEY);
  if (!likeId) { likeBtn.disabled = false; return; }

  try {
    const res = await fetchJson(apiUrl(`/api/like/my?userId=${encodeURIComponent(likeId)}`));
    if (res.data.liked) { likeBtn.classList.add("liked"); likeBtn.disabled = true; }
    else likeBtn.disabled = false;
  } catch { likeBtn.disabled = false; }
}

export async function handleLike() {
  const likeBtn = $("#likeButton");
  const likeCt = $("#likeCount");
  const userCt = $("#userCount");
  if (!canUseBackend() || !likeBtn || !likeCt) return;

  likeBtn.disabled = true;
  try {
    let likeId = localStorage.getItem(LIKE_ID_KEY);
    if (!likeId) {
      const init = await postJson(apiUrl("/api/like/init"), {});
      likeId = init.id;
      localStorage.setItem(LIKE_ID_KEY, likeId);
    }
    const res = await postJson(apiUrl("/api/like"), { id: likeId });
    if (!res.already_liked) likeBtn.classList.add("liked");
    updateCounts(res.count, res.users);
    // Background sync
    try { const s = await fetchJson(apiUrl("/api/stats")); updateCounts(s.data.likes, s.data.users); } catch { /* */ }
    likeBtn.disabled = true;
  } catch {
    const msg = $("#message");
    if (msg) { msg.textContent = t("like.error"); msg.classList.add("error"); }
    likeBtn.disabled = false;
  }
}

function updateCounts(likes, users) {
  const likeCt = $("#likeCount");
  const userCt = $("#userCount");
  if (likeCt) {
    const n = Number(likes);
    if (Number.isFinite(n)) { likeCt.textContent = n.toLocaleString(); likeCt.dataset.count = String(n); }
  }
  if (userCt) {
    const n = Number(users);
    if (Number.isFinite(n)) { userCt.textContent = t("stats.usersFormat", { count: n.toLocaleString() }); userCt.dataset.count = String(n); }
  }
}
