// ── Buildings — data loading, caching, search ──────────────────────
import { setState, campuses, allBuildings, buildingChoices, buildingActiveIndex,
         BUILDINGS_CACHE_KEY, BUILDINGS_CACHE_TTL } from './state.js';
import { t, bilingualCampusName, bilingualSourceCampusName, bilingualBuildingName,
         buildingEnglishName, campusLabels, sourceCampusLabels, buildingEnglishNames } from './i18n.js';
import { floorRange, baseBuildingName, roomFloor, escapeHtml, debounce } from './utils.js';
import { canUseBackend, apiUrl, fetchJson } from './api.js';

export { buildingActiveIndex };

const pageQuery = new URLSearchParams(location.search);

// ── Cache ─────────────────────────────────────────────────────────

function loadCachedBuildings() {
  try {
    const raw = localStorage.getItem(BUILDINGS_CACHE_KEY);
    if (!raw) return null;
    const cache = JSON.parse(raw);
    if (Date.now() - cache.timestamp > BUILDINGS_CACHE_TTL) return null;
    return cache.data;
  } catch { return null; }
}

function saveCachedBuildings(data) {
  try {
    localStorage.setItem(BUILDINGS_CACHE_KEY, JSON.stringify({ timestamp: Date.now(), data }));
  } catch { /* silent */ }
}

function hasBuildingsChanged(oldData, newData) {
  if (!oldData || !newData) return true;
  if (oldData.length !== newData.length) return true;
  const oldIds = new Set(oldData.flatMap(c => c.buildings.map(b => b.id)));
  const newIds = new Set(newData.flatMap(c => c.buildings.map(b => b.id)));
  if (oldIds.size !== newIds.size) return true;
  for (const id of oldIds) { if (!newIds.has(id)) return true; }
  return false;
}

// ── Data processing ────────────────────────────────────────────────

export function normalizeCampuses(data) {
  if (data[0]?.client && Array.isArray(data[0]?.buildings)) return data;
  return [{
    client: "192.168.84.87",
    name: "粤海",
    buildings: data.map((b) => ({ id: b.id, name: b.name })),
  }];
}

export function flattenBuildings(campusData) {
  return campusData.flatMap((campus) => {
    const uiCampus = campus.client === "172.21.101.11" ? "丽湖" : "粤海";
    const campusGroup = campus.client === "172.21.101.11" ? "lihu" : "yuehai";
    return (campus.buildings || []).map((building) => ({
      id: building.id,
      name: building.name,
      ...floorRange(building.name),
      client: campus.client,
      campusName: uiCampus,
      campusGroup,
      sourceCampusName: campus.name,
    }));
  });
}

export function mergeBuildingChoices(buildings) {
  const groups = new Map();
  for (const building of buildings) {
    const key = `${building.campusGroup}:${baseBuildingName(building.name)}`;
    const current = groups.get(key) || {
      displayName: baseBuildingName(building.name),
      displayLabel: bilingualBuildingName(baseBuildingName(building.name)),
      searchText: "",
      campusGroup: building.campusGroup,
      campusName: building.campusName,
      sourceCampusNames: new Set(),
      variants: [],
    };
    current.sourceCampusNames.add(building.sourceCampusName);
    current.variants.push(building);
    groups.set(key, current);
  }
  return [...groups.values()].map((group) => ({
    ...group,
    sourceCampusName: [...group.sourceCampusNames].join(" / "),
    sourceCampusLabel: [...group.sourceCampusNames].map(bilingualSourceCampusName).join(" / "),
    searchText: [
      group.displayName, group.displayLabel, buildingEnglishName(group.displayName),
      group.campusName, bilingualCampusName(group.campusName),
      ...group.sourceCampusNames,
      ...[...group.sourceCampusNames].map(bilingualSourceCampusName),
      ...group.variants.map((b) => b.name),
      ...group.variants.map((b) => bilingualBuildingName(b.name)),
    ].join(" ").toLowerCase(),
    variants: group.variants.sort((a, b) => (a.minFloor || 0) - (b.minFloor || 0)),
  }));
}

// ── Static fallback data ───────────────────────────────────────────

export function staticCampuses() {
  return [
    { client: "192.168.84.1", name: "北校区", buildings: [
      { id: "6363", name: "乔林11-12层" }, { id: "6364", name: "乔木11-12层" },
      { id: "6875", name: "乔森阁2-10层" }, { id: "6876", name: "乔森11-20层" },
      { id: "6877", name: "乔相阁2-10层" }, { id: "6878", name: "乔相11-20层" },
      { id: "6121", name: "乔林阁1-10层" }, { id: "6122", name: "乔木阁1-10层" },
      { id: "7724", name: "乔梧阁2-10层" }, { id: "7725", name: "乔梧阁11-20" },
      { id: "54", name: "山茶斋" }, { id: "55", name: "红榴斋" },
      { id: "56", name: "米兰斋" }, { id: "57", name: "海桐斋" },
      { id: "58", name: "桃李斋" }, { id: "59", name: "凌霄斋" },
      { id: "61", name: "银桦斋" }, { id: "63", name: "木犀轩" },
      { id: "64", name: "丹枫轩" }, { id: "65", name: "紫檀轩" },
      { id: "66", name: "石楠轩" }, { id: "67", name: "苏铁轩" },
      { id: "68", name: "芸香阁" }, { id: "69", name: "丁香阁" },
      { id: "70", name: "文杏阁" }, { id: "71", name: "海棠阁" },
      { id: "72", name: "疏影阁" }, { id: "73", name: "杜衡阁" },
      { id: "74", name: "辛夷阁" }, { id: "75", name: "韵竹阁" },
      { id: "76", name: "云杉轩" }, { id: "77", name: "紫藤轩" },
      { id: "8147", name: "留学生公寓" },
    ]},
    { client: "192.168.84.110", name: "南校区", buildings: [
      { id: "6875", name: "春笛3-8楼" }, { id: "6876", name: "夏筝3-17楼" },
      { id: "6877", name: "秋瑟3-8楼" }, { id: "6878", name: "冬筑3-6楼" },
      { id: "7119", name: "春笛9-17楼" }, { id: "7828", name: "秋瑟9-17楼" },
      { id: "8240", name: "冬筑7-10楼" }, { id: "8241", name: "冬筑11-14楼" },
      { id: "8242", name: "冬筑15-17楼" },
    ]},
    { client: "172.21.101.11", name: "丽湖校区", buildings: [
      { id: "10057", name: "A栋风信子" }, { id: "10934", name: "B栋山楂树" },
      { id: "10935", name: "C栋胡杨林" },
    ]},
    { client: "192.168.84.87", name: "深大新斋区", buildings: [
      { id: "7126", name: "风槐斋" }, { id: "7603", name: "雨鹃斋" },
      { id: "17887", name: "蓬莱客舍" }, { id: "18118", name: "聚翰斋" },
      { id: "18119", name: "紫薇斋" }, { id: "18120", name: "红豆斋" },
    ]},
  ];
}

// ── Render ─────────────────────────────────────────────────────────

export function renderCampusOptions(fields) {
  const preferredCampus = fields.campusGroup.value || "yuehai";
  const campusGroups = [
    { value: "yuehai", labelKey: "campus.yuehai" },
    { value: "lihu", labelKey: "campus.lihu" },
  ].filter((group) => allBuildings.some((b) => b.campusGroup === group.value));
  fields.campusGroup.innerHTML = "";
  for (const campus of campusGroups) {
    const option = document.createElement("option");
    option.value = campus.value;
    option.dataset.i18n = campus.labelKey;
    option.textContent = t(campus.labelKey);
    if (campus.value === preferredCampus) option.selected = true;
    fields.campusGroup.append(option);
  }
}

export function renderBuildingOptions(fields, filter = "") {
  const keyword = filter.trim().toLowerCase();
  const options = buildingChoices.filter((choice) => {
    if (!keyword) return true;
    return choice.searchText.includes(keyword);
  });
  renderBuildingOptionsForList(fields, options, filter.trim());
}

export function renderBuildingOptionsForList(fields, options, rawKeyword = "") {
  const list = document.querySelector("#buildingOptions");
  list.innerHTML = "";
  setState("buildingActiveIndex", -1);
  fields.buildingSearch.removeAttribute("aria-activedescendant");

  if (options.length === 0 && rawKeyword) {
    const empty = document.createElement("div");
    empty.className = "combo-empty";
    empty.textContent = t("form.buildingNoResults");
    list.append(empty);
    list.classList.add("open");
    return;
  }
  if (options.length === 0) { list.classList.remove("open"); return; }

  if (rawKeyword || document.activeElement === fields.buildingSearch) {
    list.classList.add("open");
  } else {
    list.classList.remove("open");
  }

  const keywordLower = rawKeyword.toLowerCase();
  for (let i = 0; i < options.length; i++) {
    const choice = options[i];
    const div = document.createElement("div");
    div.className = "combo-option";
    div.setAttribute("role", "option");
    div.id = `building-opt-${i}`;
    div.setAttribute("aria-selected", "false");
    const label = keywordLower
      ? highlightBuildingText(choice.displayLabel, rawKeyword)
      : choice.displayLabel;
    const campusInfo = `${bilingualCampusName(choice.campusName)} · ${choice.sourceCampusLabel}`;
    div.innerHTML = `${label}<small>${campusInfo}</small>`;
    div.addEventListener("pointerdown", (e) => {
      e.preventDefault();
      fields.buildingSearch.value = choice.displayLabel;
      syncSelectedBuilding(fields);
      closeBuildingOptions(fields);
      updateBuildingFeedback(fields);
    });
    list.append(div);
  }
}

export function highlightBuildingText(text, rawKeyword) {
  if (!rawKeyword) return text;
  const escaped = rawKeyword.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  return text.replace(new RegExp(`(${escaped})`, "gi"), "<mark>$1</mark>");
}

export function updateActiveDescendant(fields, options) {
  if (!options) options = document.querySelectorAll("#buildingOptions .combo-option");
  options.forEach((opt, i) => {
    const isActive = i === buildingActiveIndex;
    opt.classList.toggle("active", isActive);
    opt.setAttribute("aria-selected", String(isActive));
  });
  const active = options[buildingActiveIndex];
  if (active) {
    fields.buildingSearch.setAttribute("aria-activedescendant", active.id);
    active.scrollIntoView({ block: "nearest" });
  } else {
    fields.buildingSearch.removeAttribute("aria-activedescendant");
  }
}

export function closeBuildingOptions(fields) {
  document.querySelector("#buildingOptions").classList.remove("open");
  setState("buildingActiveIndex", -1);
  fields.buildingSearch.removeAttribute("aria-activedescendant");
}

export function chooseDefaultBuildingForCampus(fields) {
  const defaultChoice = preferredChoice() || choicesForCurrentCampus(fields)[0] || buildingChoices[0];
  if (defaultChoice) fields.buildingSearch.value = defaultChoice.displayLabel;
}

export function syncSelectedBuilding(fields) {
  const selected = selectedBuilding(fields);
  if (!selected) return;
  fields.client.value = selected.client;
  fields.campusName.value = selected.campusName;
  fields.buildingId.value = selected.id;
  fields.buildingName.value = selected.name;
  fields.campusGroup.value = selected.campusGroup;
}

export function resolveBuildingMatch(fields, text, campusValue) {
  const trimmed = text.trim();
  if (!trimmed) return { matched: false, source: "none", choice: null };
  const lower = trimmed.toLowerCase();
  const exactChoice = buildingChoices.find(
    (item) => item.displayName === trimmed || item.displayLabel === trimmed || buildingEnglishName(item.displayName) === lower
  );
  if (exactChoice) {
    const filtered = (campusValue && campusValue !== "") ? [exactChoice].filter(c => c.campusGroup === campusValue) : [exactChoice];
    return { matched: true, source: "exact", choice: filtered[0] || exactChoice };
  }
  const scope = campusValue ? buildingChoices.filter((c) => c.campusGroup === campusValue) : buildingChoices;
  const fuzzyHit = scope.find((item) => item.searchText.includes(lower));
  if (fuzzyHit) return { matched: true, source: "fuzzy", choice: fuzzyHit };
  return { matched: false, source: "none", choice: null };
}

export function updateBuildingFeedback(fields) {
  const fbEl = fields.buildingFeedback;
  if (!fbEl) return;
  const result = resolveBuildingMatch(fields, fields.buildingSearch.value, fields.campusGroup?.value);
  const comboWrap = fbEl.parentElement;
  comboWrap.classList.remove("has-match-exact", "has-match-fuzzy", "has-no-match");
  if (!result.matched) {
    if (fields.buildingSearch.value.trim().length > 0) {
      comboWrap.classList.add("has-no-match");
      fbEl.textContent = t("form.buildingNoMatch");
    } else { fbEl.textContent = ""; }
  } else if (result.source === "exact") {
    comboWrap.classList.add("has-match-exact");
    fbEl.textContent = "";
  } else {
    comboWrap.classList.add("has-match-fuzzy");
    fbEl.textContent = t("form.buildingFuzzyMatch");
  }
}

// ── Helpers ────────────────────────────────────────────────────────

function selectedBuilding(fields) {
  const text = fields.buildingSearch.value.trim();
  const normalizedText = text.toLowerCase();
  const exactChoice = buildingChoices.find(
    (item) => item.displayName === text || item.displayLabel === text || buildingEnglishName(item.displayName) === normalizedText
  );
  if (exactChoice) return pickVariantForRoom(fields, exactChoice.variants);
  const choices = choicesForCurrentCampus(fields);
  const choice = choices.find((item) => item.displayName === text || item.displayLabel === text)
    || choices.find((item) => item.searchText.includes(normalizedText))
    || preferredChoice() || choices[0] || buildingChoices[0];
  if (!choice) return null;
  return pickVariantForRoom(fields, choice.variants);
}

function pickVariantForRoom(fields, variants) {
  const floor = roomFloor(fields.roomName.value);
  if (floor != null) {
    const matched = variants.find((b) => b.minFloor != null && b.maxFloor != null && floor >= b.minFloor && floor <= b.maxFloor);
    if (matched) return matched;
  }
  return variants[0];
}

function preferredChoice() {
  return buildingChoices.find(
    (choice) => choice.variants.some((b) => b.client === "192.168.84.87" && b.id === "7126")
  );
}

function choicesForCurrentCampus(fields) {
  return buildingChoices.filter((choice) => choice.campusGroup === fields?.campusGroup?.value);
}

// ── Master loader (with localStorage cache) ───────────────────────

export async function loadBuildings(fields, { setMessageKey, loadStaticBuildings } = {}) {
  if (!canUseBackend()) {
    if (loadStaticBuildings) loadStaticBuildings(fields);
    if (setMessageKey) setMessageKey("message.staticPage");
    return;
  }

  // Try cache first
  const cached = loadCachedBuildings();
  if (cached) {
    applyBuildingsData(cached, fields);
    refreshBuildingsInBackground(fields); // silent background refresh
    return;
  }

  try {
    const payload = await fetchJson(apiUrl("/api/buildings"));
    if (Array.isArray(payload.data) && payload.data.length > 0) {
      const fresh = normalizeCampuses(payload.data);
      saveCachedBuildings(fresh);
      applyBuildingsData(fresh, fields);
    }
  } catch {
    if (loadStaticBuildings) loadStaticBuildings(fields);
    if (setMessageKey) setMessageKey("message.staticMode");
  }
}

function applyBuildingsData(campusData, fields) {
  setState("campuses", campusData);
  const flat = flattenBuildings(campusData);
  setState("allBuildings", flat);
  setState("buildingChoices", mergeBuildingChoices(flat));
  renderCampusOptions(fields);
  chooseDefaultBuildingForCampus(fields);
  renderBuildingOptions(fields);
  syncSelectedBuilding(fields);
}

async function refreshBuildingsInBackground(fields) {
  if (!canUseBackend()) return;
  try {
    const payload = await fetchJson(apiUrl("/api/buildings"));
    if (Array.isArray(payload.data) && payload.data.length > 0) {
      const fresh = normalizeCampuses(payload.data);
      if (hasBuildingsChanged(campuses, fresh)) {
        saveCachedBuildings(fresh);
        applyBuildingsData(fresh, fields);
      }
    }
  } catch { /* silent — keep using cache */ }
}

export function loadStaticBuildings(fields) {
  applyBuildingsData(staticCampuses(), fields);
}

export function staticDemoStatus() {
  return {
    client: "192.168.84.87",
    campus_name: "粤海",
    building_id: "7126",
    building_name: "风槐斋",
    room_id: "7322",
    room_name: "713",
    period: { begin: "2026-04-20", end: "2026-05-20", days: 30 },
    records: 30,
    threshold_kwh: 20,
    status: "low",
    remaining: 18.6,
    total_used_kwh: 42.8,
    daily_avg_kwh: 1.43,
    est_days_left: 13.0,
    last_record: "2026-05-20",
    trend: [
      { date: "2026-05-14", remaining: 27.8, daily_used_kwh: 1.5 },
      { date: "2026-05-15", remaining: 26.1, daily_used_kwh: 1.7 },
      { date: "2026-05-16", remaining: 24.9, daily_used_kwh: 1.2 },
      { date: "2026-05-17", remaining: 23.0, daily_used_kwh: 1.9 },
      { date: "2026-05-18", remaining: 21.4, daily_used_kwh: 1.6 },
      { date: "2026-05-19", remaining: 20.0, daily_used_kwh: 1.4 },
      { date: "2026-05-20", remaining: 18.6, daily_used_kwh: 1.4 },
    ],
    recharges: [
      { time: "2026-05-08", kwh: 50, yuan: 30.5, method: "微信支付" },
      { time: "2026-04-19", kwh: 30, yuan: 18.3, method: "支付宝" },
    ],
  };
}
