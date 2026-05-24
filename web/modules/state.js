// ── Shared mutable state ───────────────────────────────────────────

export const LIKE_ID_KEY = "electrifyszu.likeId";
export const USAGE_LEVEL_STORAGE_KEY = "electrifyszu.usageLevels";
export const BUILDINGS_CACHE_KEY = "electrifyszu.buildings";
export const BUILDINGS_CACHE_TTL = 3600 * 1000; // 1 hour

export let campuses = [];
export let allBuildings = [];
export let buildingChoices = [];
export let buildingActiveIndex = -1;
export let currentStatusData = null;
export let currentLocale = "zh-CN";
export let subscriptionWasPending = false;
export let lastFocusedElement = null;

export const metricMode = {
  remaining: "kwh",
  dailyAvg: "kwh",
  daysLeft: "days",
  totalUsed: "kwh",
};

export let customUsageLevels = { medium: null, high: null };

export function setState(key, value) {
  const setters = {
    campuses(v) { campuses = v; },
    allBuildings(v) { allBuildings = v; },
    buildingChoices(v) { buildingChoices = v; },
    buildingActiveIndex(v) { buildingActiveIndex = v; },
    currentStatusData(v) { currentStatusData = v; },
    currentLocale(v) { currentLocale = v; },
    subscriptionWasPending(v) { subscriptionWasPending = v; },
    lastFocusedElement(v) { lastFocusedElement = v; },
    customUsageLevels(v) { customUsageLevels = v; },
  };
  if (key in setters) setters[key](value);
}
