// ── Subscription — email alerts ────────────────────────────────────
import { t } from './i18n.js';
import { escapeHtml } from './utils.js';
import { canUseBackend, apiUrl, postJson } from './api.js';

const $ = (sel) => document.querySelector(sel);
const messageEl = () => $("#message");
const setMsg = (text, isError) => { const m = messageEl(); if (m) { m.textContent = text; m.classList.toggle("error", isError); } };

export function setupSubscriptionToggle() {
  const trigger = $("#subscriptionTrigger");
  const inner = $(".subscription-inner");
  const summary = $("#subscriptionSummary");
  if (!trigger || !inner) return;
  const toggle = () => {
    inner.classList.toggle("open");
    const ring = trigger.querySelector(".ring-icon");
    if (ring) { ring.classList.remove("clicked"); void ring.offsetWidth; ring.classList.add("clicked"); }
  };
  trigger.addEventListener("click", toggle);
  if (summary) summary.addEventListener("click", toggle);
}

export function syncEmailInputState() {
  const group = $(".email-input-group");
  const input = $("#subscriberEmail");
  const hint = $("#subscriberEmailDomainHint");
  if (!group || !input) return;
  const value = input.value.trim();
  const hasCustomDomain = value.includes("@");
  group.classList.toggle("has-custom-domain", hasCustomDomain);
  input.placeholder = hasCustomDomain ? "you@example.com" : t("subscribe.emailPlaceholder");
  input.setCustomValidity("");
  if (hint) {
    if (value.length >= 4) {
      const inferred = inferEmailDomain(value);
      hint.textContent = inferred || "@email.szu.edu.cn";
    } else {
      hint.textContent = "@";
    }
  }
}

function inferEmailDomain(prefix) {
  const m = String(prefix).match(/^(\d{4})/);
  if (!m) return null;
  const year = parseInt(m[1]);
  return year >= 2024 ? "@mails.szu.edu.cn" : "@email.szu.edu.cn";
}

function normalizeEmail(value) {
  const t = String(value || "").trim();
  if (!t) return "";
  if (!t.includes("@")) {
    const d = inferEmailDomain(t) || "@email.szu.edu.cn";
    return `${t}${d}`.toLowerCase();
  }
  return /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(t) ? t.toLowerCase() : "";
}

function readFields() {
  return {
    email: $("#subscriberEmail"),
    client: $("#client"),
    campusName: $("#campusName"),
    buildingId: $("#buildingId"),
    buildingName: $("#buildingName"),
    roomName: $("#roomName"),
    alertEnabled: $("#subscribeAlert"),
    dailyReportEnabled: $("#subscribeDailyReport"),
  };
}

export async function saveSubscription() {
  const f = readFields();
  const email = normalizeEmail(f.email.value);
  if (!email) { setMsg(t("subscribe.invalidEmail"), true); f.email.focus(); return; }
  if (!f.alertEnabled.checked && !f.dailyReportEnabled.checked) {
    setMsg(t("subscribe.chooseOne"), true); f.alertEnabled.focus(); return;
  }

  const payload = {
    email, client: f.client.value, campusName: f.campusName.value,
    buildingId: f.buildingId.value, buildingName: f.buildingName.value,
    roomName: f.roomName.value,
    alertEnabled: f.alertEnabled.checked,
    dailyReportEnabled: f.dailyReportEnabled.checked,
  };

  const confirmed = await confirmDialog(payload);
  if (!confirmed) return;

  setBusy(true);
  setMsg(t("subscribe.saving"));
  try {
    const res = await postJson(apiUrl("/api/subscriptions"), payload);
    const msg = res.message || t("subscribe.saved");
    if (res.verification_required) {
      f.email.value = email;
      syncEmailInputState();
    }
    showResult(msg);
    setMsg(msg);
    if (res.verification_required) collapseTo("pending", email);
    else collapseTo("active", email);
  } catch (err) {
    setMsg(err.message, true);
  } finally {
    setBusy(false);
  }
}

function confirmDialog(payload) {
  const msg = t("subscribe.dialogConfirmMessage", {
    email: payload.email,
    dorm: `${payload.campusName} ${payload.buildingName} ${payload.roomName}`,
    types: [payload.alertEnabled && t("subscribe.alertOption"), payload.dailyReportEnabled && t("subscribe.dailyReportOption")].filter(Boolean).join("、"),
  });
  const dlg = $("#subscriptionDialog");
  const msgEl = $("#subscriptionDialogMessage");
  if (!dlg || !msgEl) return Promise.resolve(window.confirm(msg));
  const titleEl = $("#subscriptionDialogTitle");
  if (titleEl) titleEl.textContent = t("subscribe.dialogTitle");
  msgEl.textContent = msg;
  dlg.returnValue = "";
  $("#subscriptionDialogCancel").hidden = false;
  const confirmBtn = $("#subscriptionDialogConfirm");
  confirmBtn.value = "confirm";
  confirmBtn.textContent = t("subscribe.dialogConfirm");
  if (typeof dlg.showModal !== "function") return Promise.resolve(window.confirm(msg));
  return new Promise((r) => { dlg.addEventListener("close", () => r(dlg.returnValue === "confirm"), { once: true }); dlg.showModal(); });
}

function showResult(text) {
  const dlg = $("#subscriptionDialog");
  const msgEl = $("#subscriptionDialogMessage");
  if (!dlg || !msgEl) { window.alert(text); return; }
  const titleEl = $("#subscriptionDialogTitle");
  if (titleEl) titleEl.textContent = t("subscribe.dialogResultTitle");
  msgEl.textContent = text;
  dlg.returnValue = "";
  $("#subscriptionDialogCancel").hidden = true;
  const confirmBtn = $("#subscriptionDialogConfirm");
  confirmBtn.value = "done";
  confirmBtn.textContent = t("subscribe.dialogDone");
  if (typeof dlg.showModal === "function") dlg.showModal();
  else window.alert(text);
}

function collapseTo(type, email) {
  const summary = $("#subscriptionSummary");
  const inner = $(".subscription-inner");
  if (!summary || !inner) return;
  if (type === "pending") {
    summary.innerHTML = `⏳ ${escapeHtml(email)} · ${t("subscribe.summaryPending")}`;
    summary.classList.add("pending-verification");
  } else {
    summary.innerHTML = `✅ ${escapeHtml(email)} · ${t("subscribe.summaryActive")}`;
    summary.classList.remove("pending-verification");
  }
  summary.hidden = false;
  inner.classList.remove("open");
}

export function markAsVerified(email) {
  const summary = $("#subscriptionSummary");
  if (!summary || !summary.classList.contains("pending-verification")) return;
  summary.classList.remove("pending-verification");
  summary.innerHTML = `✅ ${escapeHtml(email)} · ${t("subscribe.summaryActive")}`;
}

function setBusy(busy) {
  $("#subscriptionForm").querySelectorAll("button, input").forEach((el) => { el.disabled = busy; });
}
