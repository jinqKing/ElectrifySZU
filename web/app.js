// ── ElectrifySZU — Entry point (ES Module) ─────────────────────────
import { setLanguage, resolveInitialLocale, t, syncEmailInputState } from './modules/i18n.js';
import { setState, currentLocale, currentStatusData, customUsageLevels,
         buildingActiveIndex, allBuildings, buildingChoices, metricMode } from './modules/state.js';
import { escapeHtml, debounce, numberOrNull,
  loadUsageLevelSettings, saveUsageLevelSettings, readUsageLevelInputs } from './modules/utils.js';
import { canUseBackend, apiUrl, fetchJson } from './modules/api.js';
import {
  loadBuildings, renderBuildingOptions, renderBuildingOptionsForList,
  renderCampusOptions, chooseDefaultBuildingForCampus, syncSelectedBuilding,
  updateBuildingFeedback, closeBuildingOptions, updateActiveDescendant,
  mergeBuildingChoices, flattenBuildings, normalizeCampuses, fetchDemoStatus,
} from './modules/buildings.js';
import { initLike, handleLike } from './modules/likes.js';

// ── DOM references ────────────────────────────────────────────────
const form = document.querySelector("#queryForm");
const subscriptionForm = document.querySelector("#subscriptionForm");
const subscriptionTrigger = document.querySelector("#subscriptionTrigger");
const subscriptionInner = document.querySelector(".subscription-inner");
const subscriptionSummary = document.querySelector("#subscriptionSummary");
const starBadge = document.querySelector("#starBadge");
const demoButton = document.querySelector("#demoButton");
const message = document.querySelector("#message");
const heroStatus = document.querySelector("#heroStatus");
const languageButtons = document.querySelectorAll("[data-lang]");
const subscriptionDialog = document.querySelector("#subscriptionDialog");
const subscriptionDialogMessage = document.querySelector("#subscriptionDialogMessage");
const subscriptionDialogCancel = document.querySelector("#subscriptionDialogCancel");
const subscriptionDialogConfirm = document.querySelector("#subscriptionDialogConfirm");
const likeButton = document.querySelector("#likeButton");
const likeCount = document.querySelector("#likeCount");
const userCount = document.querySelector("#userCount");
const usageLevelForm = document.querySelector("#usageLevelForm");
const resetUsageLevelsButton = document.querySelector("#resetUsageLevels");

const fields = {
  campusGroup: document.querySelector("#campusGroup"),
  client: document.querySelector("#client"),
  campusName: document.querySelector("#campusName"),
  buildingSearch: document.querySelector("#buildingSearch"),
  buildingFeedback: document.querySelector("#buildingFeedback"),
  buildingId: document.querySelector("#buildingId"),
  buildingName: document.querySelector("#buildingName"),
  roomName: document.querySelector("#roomName"),
  days: document.querySelector("#days"),
  subscriberEmail: document.querySelector("#subscriberEmail"),
  subscribeAlert: document.querySelector("#subscribeAlert"),
  subscribeDailyReport: document.querySelector("#subscribeDailyReport"),
  mediumUseThreshold: document.querySelector("#mediumUseThreshold"),
  highUseThreshold: document.querySelector("#highUseThreshold"),
};

const view = {
  remaining: document.querySelector("#remaining"),
  remainingUnit: document.querySelector("#remainingUnit"),
  remainingAlt: document.querySelector("#remainingAlt"),
  dailyAvg: document.querySelector("#dailyAvg"),
  dailyAvgUnit: document.querySelector("#dailyAvgUnit"),
  dailyAvgAlt: document.querySelector("#dailyAvgAlt"),
  daysLeft: document.querySelector("#daysLeft"),
  daysLeftUnit: document.querySelector("#daysLeftUnit"),
  daysLeftDate: document.querySelector("#daysLeftDate"),
  totalUsed: document.querySelector("#totalUsed"),
  totalUsedUnit: document.querySelector("#totalUsedUnit"),
  totalUsedAlt: document.querySelector("#totalUsedAlt"),
  roomLabel: document.querySelector("#roomLabel"),
  lastRecord: document.querySelector("#lastRecord"),
  period: document.querySelector("#period"),
  records: document.querySelector("#records"),
  statusBadge: document.querySelector("#statusBadge"),
  meterFill: document.querySelector("#meterFill"),
  rechargeList: document.querySelector("#rechargeList"),
  rechargeCount: document.querySelector("#rechargeCount"),
  trendChart: document.querySelector("#trendChart"),
  chartRange: document.querySelector("#chartRange"),
};

// ── State ─────────────────────────────────────────────────────────
const pageQuery = new URLSearchParams(location.search);
let lastMessage = { key: "message.initial", values: {}, isError: false, raw: null };
let lastHeroStatus = { key: "status.waiting", values: {}, status: "unknown", raw: null };

export const loadingStatusController =
  window.ElectrifySZULoadingStatus?.createController(message, loadingStatusOptions()) || null;

setState("customUsageLevels", loadUsageLevelSettings());

// ── Event listeners ───────────────────────────────────────────────

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  syncSelectedBuilding(fields);
  if (!canUseBackend()) {
    setMessageKey("message.staticPage", {}, true);
    setHeroStatusKey("status.needBackend", {}, "critical");
    return;
  }
  await loadStatus(apiUrl("/api/status") + "?" + new URLSearchParams(new FormData(form)));
});

async function loadStatus(url) {
  setBusy(true);
  startLoadingMessage();
  try {
    const payload = await fetchJson(url);
    if (!payload.ok) throw new Error(payload.hint || payload.error || t("error.queryFailed"));
    const { renderStatus } = await import('./modules/chart.js');
    renderStatus(payload.data, view);
    setMessageKey("message.complete");
  } catch (error) {
    setMessageRaw(error.message, true);
    setHeroStatusKey("status.queryFailed", {}, "critical");
    updateBalanceCardStatus("unknown");
  } finally {
    setBusy(false);
  }
}

subscriptionForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  syncSelectedBuilding(fields);
  if (!canUseBackend()) {
    setMessageKey("subscribe.needsBackend", {}, true);
    setHeroStatusKey("status.needBackend", {}, "critical");
    return;
  }
  const { saveSubscription } = await import('./modules/subscription.js');
  await saveSubscription();
});

fields.campusGroup.addEventListener("change", () => {
  chooseDefaultBuildingForCampus(fields);
  renderBuildingOptions(fields);
  syncSelectedBuilding(fields);
});

const debouncedBuildingInput = debounce((value) => {
  setState("buildingActiveIndex", -1);
  renderBuildingOptions(fields, value);
  updateBuildingFeedback(fields);
}, 150);

fields.buildingSearch.addEventListener("change", () => syncSelectedBuilding(fields));
fields.buildingSearch.addEventListener("input", () => {
  debouncedBuildingInput(fields.buildingSearch.value);
});
fields.buildingSearch.addEventListener("focus", () => {
  fields.buildingSearch.select();
  const campusVal = fields.campusGroup.value;
  if (campusVal) {
    const campusBuildings = buildingChoices.filter((c) => c.campusGroup === campusVal);
    renderBuildingOptionsForList(fields, campusBuildings, "");
  } else {
    renderBuildingOptions(fields, "");
  }
});
fields.buildingSearch.addEventListener("blur", () => updateBuildingFeedback(fields));
fields.buildingSearch.addEventListener("keydown", (e) => {
  const list = document.querySelector("#buildingOptions");
  const options = list.querySelectorAll(".combo-option");
  if (!list.classList.contains("open") || options.length === 0) return;
  switch (e.key) {
    case "ArrowDown":
      e.preventDefault();
      setState("buildingActiveIndex", Math.min(buildingActiveIndex + 1, options.length - 1));
      updateActiveDescendant(fields, options);
      break;
    case "ArrowUp":
      e.preventDefault();
      setState("buildingActiveIndex", Math.max(buildingActiveIndex - 1, 0));
      updateActiveDescendant(fields, options);
      break;
    case "Enter":
      e.preventDefault();
      if (buildingActiveIndex >= 0 && buildingActiveIndex < options.length) options[buildingActiveIndex].click();
      break;
    case "Escape":
      e.preventDefault();
      closeBuildingOptions(fields);
      break;
  }
});

fields.roomName.addEventListener("focus", () => fields.roomName.select());
fields.subscriberEmail.addEventListener("input", syncEmailInputState);

document.querySelectorAll("[data-metric-card]").forEach((card) => {
  card.addEventListener("click", async () => {
    const { toggleMetricMode } = await import('./modules/chart.js');
    toggleMetricMode(card.dataset.metricKey, view);
  });
  card.addEventListener("keydown", async (event) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      const { toggleMetricMode } = await import('./modules/chart.js');
      toggleMetricMode(card.dataset.metricKey, view);
    }
  });
});

document.addEventListener("click", (event) => {
  if (!event.target.closest(".combo")) closeBuildingOptions(fields);
});

// ── 演示数据轮换 ─────────────────────────────────────────────
let _demoList = [];
let _demoIndex = 0;

demoButton.addEventListener("click", async () => {
  // 首次点击加载全部场景
  if (_demoList.length === 0) {
    const data = await fetchDemoStatus();
    if (!data || !Array.isArray(data) || data.length === 0) {
      setMessageKey("message.demoFailed", {}, true);
      return;
    }
    _demoList = data;
  }

  const scene = _demoList[_demoIndex % _demoList.length];
  _demoIndex++;

  const { renderStatus } = await import('./modules/chart.js');
  renderStatus(scene, view);
  // 显示当前场景序号，方便知道切换到第几个了
  setMessageKey("message.demoLoaded");
  const sceneLabel = `场景 ${(_demoIndex - 1) % _demoList.length + 1}/${_demoList.length}`;
  message.textContent += ` · ${sceneLabel}`;
});

// Block F5 / Ctrl+R reload (SPA behavior)
window.addEventListener("keydown", (event) => {
  const key = String(event.key || "").toLowerCase();
  if (event.key === "F5" || ((event.ctrlKey || event.metaKey) && key === "r")) {
    event.preventDefault();
    event.stopPropagation();
  }
});

window.addEventListener("beforeunload", (event) => {
  event.preventDefault();
  event.returnValue = "";
});

languageButtons.forEach((button) => {
  button.addEventListener("click", async () => {
    setLanguage(button.dataset.lang);
    document.title = t("meta.title");
    if (currentStatusData) {
      const { renderStatus } = await import('./modules/chart.js');
      renderStatus(currentStatusData, view);
    } else view.rechargeCount.textContent = t("format.records", { count: 0 });
    if (lastMessage.raw != null) setMessage(lastMessage.raw, lastMessage.isError);
    else setMessage(t(lastMessage.key, lastMessage.values), lastMessage.isError);
    if (lastHeroStatus.raw != null) setHeroStatus(lastHeroStatus.raw, lastHeroStatus.status);
    else setHeroStatus(t(lastHeroStatus.key, lastHeroStatus.values), lastHeroStatus.status);
    syncEmailInputState();
    const btn = document.querySelector("#chartUnitToggle");
    if (btn) btn.textContent = t("chart.unitToggle");
    if (userCount && userCount.dataset.count) {
      const n = Number(userCount.dataset.count);
      if (Number.isFinite(n)) userCount.textContent = t("stats.usersFormat", { count: n.toLocaleString() });
    }
  });
});

likeButton?.addEventListener("click", handleLike);

usageLevelForm.addEventListener("input", async () => {
  setState("customUsageLevels", readUsageLevelInputs());
  saveUsageLevelSettings(customUsageLevels);
  if (currentStatusData) {
    const { renderTrend } = await import('./modules/chart.js');
    renderTrend(currentStatusData.trend || [], view);
  }
});

resetUsageLevelsButton.addEventListener("click", async () => {
  setState("customUsageLevels", { medium: null, high: null });
  saveUsageLevelSettings(customUsageLevels);
  if (currentStatusData) {
    const { renderTrend } = await import('./modules/chart.js');
    renderTrend(currentStatusData.trend || [], view);
  }
});

const chartUnitToggle = document.querySelector("#chartUnitToggle");
if (chartUnitToggle) {
  chartUnitToggle.addEventListener("click", async () => {
    const { toggleChartUnit } = await import('./modules/chart.js');
    toggleChartUnit(view);
  });
}

// ── Initialization ────────────────────────────────────────────────
const initialLocale = resolveInitialLocale();
setLanguage(initialLocale, { persist: false });
document.title = t("meta.title");

loadBuildings(fields, { setMessageKey });

syncEmailInputState();
// Inline subscription toggle (was in subscription.js, kept here to avoid static import)
{
  const trigger = document.querySelector("#subscriptionTrigger");
  const inner = document.querySelector(".subscription-inner");
  const summary = document.querySelector("#subscriptionSummary");
  if (trigger && inner) {
    const toggle = () => {
      inner.classList.toggle("open");
      const ring = trigger.querySelector(".ring-icon");
      if (ring) { ring.classList.remove("clicked"); void ring.offsetWidth; ring.classList.add("clicked"); }
    };
    trigger.addEventListener("click", toggle);
    if (summary) summary.addEventListener("click", toggle);
  }
}
showPageNotice();
import('./modules/github.js').then(mod => mod.loadGithubStars());

// Lazy-loaded: likes (deferred with requestIdleCallback)
if ('requestIdleCallback' in window) {
  requestIdleCallback(() => { initLike(); }, { timeout: 2000 });
} else {
  setTimeout(() => { initLike(); }, 1000);
}

import('./modules/sponsor.js').then(mod => { mod.setupSponsor(); mod.setupSponsorKeyboard(); });

// ── Helper functions ──────────────────────────────────────────────

function setBusy(isBusy) {
  form.querySelectorAll("button, input, select").forEach((el) => { el.disabled = isBusy; });
}

function setMessageKey(key, values = {}, isError = false) {
  lastMessage = { key, values, isError, raw: null };
  setMessage(t(key, values), isError);
}

function setMessageRaw(text, isError = false) {
  lastMessage = { key: null, values: {}, isError, raw: text };
  setMessage(text, isError);
}

function setMessage(text, isError = false) {
  loadingStatusController?.stop();
  message.textContent = text;
  message.classList.toggle("error", isError);
}

function setHeroStatusKey(key, values = {}, status = "unknown") {
  lastHeroStatus = { key, values, status, raw: null };
  setHeroStatus(t(key, values), status);
}

function setHeroStatusRaw(text, status = "unknown") {
  lastHeroStatus = { key: null, values: {}, status, raw: text };
  setHeroStatus(text, status);
}

function setHeroStatus(text, status = "unknown") {
  heroStatus.querySelector("span:last-child").textContent = text;
  heroStatus.querySelector(".pulse").style.background = statusColor(status);
}

function statusColor(status) {
  return { ok: "#0f9f6e", low: "#d98616", critical: "#d73939", unknown: "#657386" }[status] || "#657386";
}

function updateBalanceCardStatus(status) {
  const card = document.querySelector(".metric.balance");
  if (!card) return;
  card.classList.remove("status-ok", "status-low", "status-critical");
  if (["ok", "low", "critical"].includes(status)) card.classList.add(`status-${status}`);
}

function startLoadingMessage() {
  lastMessage = { key: "message.loading", values: {}, isError: false, raw: null };
  if (!loadingStatusController) { setMessage(t("message.loading")); return; }
  message.classList.remove("error");
  loadingStatusController.start(loadingStatusOptions());
}

function loadingStatusOptions() {
  return { locale: currentLocale, mainText: t("message.loading") };
}

function showPageNotice() {
  const notice = pageQuery.get("notice");
  if (!notice) return;

  const values = {
    email: pageQuery.get("email") || "",
    campus: pageQuery.get("campus") || "",
    building: pageQuery.get("building") || "",
    room: pageQuery.get("room") || "",
  };
  const mapping = {
    verified: "notice.verified",
    already_verified: "notice.alreadyVerified",
    verify_expired: "notice.verifyExpired",
    verify_invalid: "notice.verifyInvalid",
    unsubscribed: "notice.unsubscribed",
    already_unsubscribed: "notice.alreadyUnsubscribed",
    unsubscribe_invalid: "notice.unsubscribeInvalid",
  };
  const key = mapping[notice];
  if (!key) return;

  const hasDetails = values.email || values.campus || values.building || values.room;
  if (!hasDetails && notice.includes("unsubscribed")) {
    setMessageKey("notice.unsubscribedGeneric", {}, notice.endsWith("invalid"));
  } else {
    setMessageKey(key, values, notice.endsWith("invalid"));
  }
  if (notice.includes("unsubscribed")) setHeroStatusKey("status.waiting", {}, "unknown");

  pageQuery.delete("notice");
  pageQuery.delete("email");
  pageQuery.delete("campus");
  pageQuery.delete("building");
  pageQuery.delete("room");
  const nextQuery = pageQuery.toString();
  const nextUrl = `${location.pathname}${nextQuery ? `?${nextQuery}` : ""}${location.hash}`;
  history.replaceState({}, "", nextUrl);

  if ((notice === "verified" || notice === "already_verified") && values.email) {
    import('./modules/subscription.js').then(mod => mod.markAsVerified(values.email));
  }

  if (["verified", "already_verified", "unsubscribed", "already_unsubscribed"].includes(notice)) {
    showVerificationNotice(notice, values);
  }
}

function showVerificationNotice(notice, values) {
  const titleMap = {
    verified: "notice.title.verified",
    already_verified: "notice.title.alreadyVerified",
    unsubscribed: "notice.title.unsubscribed",
    already_unsubscribed: "notice.title.alreadyUnsubscribed",
  };
  const msgMap = {
    verified: "notice.verified",
    already_verified: "notice.alreadyVerified",
    unsubscribed: "notice.unsubscribed",
    already_unsubscribed: "notice.alreadyUnsubscribed",
  };
  const titleKey = titleMap[notice];
  const msgKey = msgMap[notice];
  if (!titleKey || !msgKey) return;

  const hasDetails = values.email || values.campus || values.building || values.room;
  const safeValues = hasDetails ? values : {};
  const messageText = hasDetails
    ? t(msgKey, values)
    : (notice.includes("unsubscribed") ? t("notice.unsubscribedGeneric", {}) : t(msgKey, safeValues));

  const titleEl = document.querySelector("#subscriptionDialogTitle");
  if (titleEl) titleEl.textContent = t(titleKey);
  subscriptionDialogMessage.textContent = messageText;
  subscriptionDialog.returnValue = "";
  subscriptionDialogCancel.hidden = true;
  subscriptionDialogConfirm.value = "done";
  subscriptionDialogConfirm.textContent = t("subscribe.dialogDone");

  if (typeof subscriptionDialog.showModal === "function") {
    subscriptionDialog.showModal();
  } else {
    window.alert(`${t(titleKey)}\n${messageText}`);
  }
}
