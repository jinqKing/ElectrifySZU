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
    if (res.data.liked) { likeBtn.classList.add("liked"); likeBtn.disabled = true; return; }
    // 服务端不认识该 ID（新部署/数据迁移 → 404），清除旧缓存
    if (res.ok && !res.data.liked) {
      // liked: false 有两种情况: 还没点过赞, 或 ID 不存在
      // 无额外字段区分，保守保留 ID（点过赞的用户不会再点第二次）
    }
  } catch { /* 查询失败不影响点赞能力 */ }
  likeBtn.disabled = false;
}

let _likePending = false;
let _retried = false;

async function _doHandleLike() {
  const likeBtn = $("#likeButton");
  const likeCt = $("#likeCount");
  const userCt = $("#userCount");
  if (!canUseBackend() || !likeBtn || !likeCt) return;

  likeBtn.disabled = true;
  const hadId = !!localStorage.getItem(LIKE_ID_KEY);
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
    const msg = $("#message");
    if (msg) { msg.classList.remove("error"); }
    try { const s = await fetchJson(apiUrl("/api/stats")); updateCounts(s.data.likes, s.data.users); } catch { /* */ }
    likeBtn.disabled = true;
  } catch (err) {
    if (err?.status === 400 && hadId && !_retried) {
      _retried = true;
      localStorage.removeItem(LIKE_ID_KEY);
      try { await _doHandleLike(); } catch { /* */ }
      _retried = false;
      return;
    }
    const msg = $("#message");
    if (msg) { msg.textContent = t("like.error"); msg.classList.add("error"); }
    likeBtn.disabled = false;
  }
}

export async function handleLike() {
  if (_likePending) return;
  _likePending = true;
  try {
    await _doHandleLike();
  } finally {
    _likePending = false;
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
