// ── Buildings — data loading, caching, search ──────────────────────
import { setState, campuses, allBuildings, buildingChoices, buildingActiveIndex,
         BUILDINGS_CACHE_KEY, BUILDINGS_CACHE_TTL } from './state.js';
import { t, bilingualCampusName, bilingualSourceCampusName, bilingualBuildingName,
         buildingEnglishName, campusLabels, sourceCampusLabels, buildingEnglishNames } from './i18n.js';
import { floorRange, baseBuildingName, roomFloor, escapeHtml, debounce } from './utils.js';
import { canUseBackend, apiUrl, fetchJson } from './api.js';
import { BUILDING_DEFAULTS } from './config.js';

export { buildingActiveIndex };

const pageQuery = new URLSearchParams(location.search);
let _firstLoad = true;

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
    client: BUILDING_DEFAULTS.client,
    name: BUILDING_DEFAULTS.campusName,
    buildings: data.map((b) => ({ id: b.id, name: b.name })),
  }];
}

export function flattenBuildings(campusData) {
  return campusData.flatMap((campus) => {
    const campusGroup = campus.group || (campus.client === "apartment" ? "apartment" : "yuehai");
    const uiCampus = campusGroup === "lihu" ? "丽湖" : campusGroup === "apartment" ? "公寓" : "粤海";
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

// ── Fallback JSON loader ────────────────────────────────────────────

// Derive base URL from import.meta.url so paths work in any deployment.
const _DATA_BASE = new URL('../data/', import.meta.url).href;

async function _fetchJSON(relativePath) {
  const url = new URL(relativePath, _DATA_BASE).href;
  const resp = await fetch(url);
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
  return resp.json();
}

// ── Render ─────────────────────────────────────────────────────────

const _CAMPUS_GROUPS = [
  { value: "yuehai", labelKey: "campus.yuehai" },
  { value: "lihu", labelKey: "campus.lihu" },
  { value: "apartment", labelKey: "campus.apartment" },
];

export function renderCampusOptions(fields) {
  const preferredCampus = fields.campusGroupId.value || "yuehai";
  const campusGroups = _CAMPUS_GROUPS.filter((group) =>
    allBuildings.some((b) => b.campusGroup === group.value)
  );
  fields.campusOptions.innerHTML = "";
  for (const campus of campusGroups) {
    const div = document.createElement("div");
    div.className = "combo-option";
    div.setAttribute("role", "option");
    div.dataset.value = campus.value;
    div.dataset.i18n = campus.labelKey;
    div.textContent = t(campus.labelKey);
    if (campus.value === preferredCampus) {
      div.classList.add("active");
      div.setAttribute("aria-selected", "true");
    }
    div.addEventListener("pointerdown", (e) => {
      e.preventDefault();
      selectCampus(fields, campus.value);
    });
    fields.campusOptions.append(div);
  }
}

export function openCampusOptions(fields) {
  fields.campusOptions.classList.add("open");
  fields.campusSearch.setAttribute("aria-expanded", "true");
}

export function closeCampusOptions(fields) {
  fields.campusOptions.classList.remove("open");
  fields.campusSearch.setAttribute("aria-expanded", "false");
}

export function selectCampus(fields, value) {
  const campus = _CAMPUS_GROUPS.find((c) => c.value === value);
  if (!campus) return;
  fields.campusGroupId.value = value;
  fields.campusSearch.value = t(campus.labelKey);
  closeCampusOptions(fields);
  chooseDefaultBuildingForCampus(fields);
  renderBuildingOptions(fields);
  syncSelectedBuilding(fields);
}

export function renderBuildingOptions(fields, filter = "", { manageOpenState = true } = {}) {
  const keyword = filter.trim().toLowerCase();
  const options = buildingChoices.filter((choice) => {
    if (!keyword) return true;
    return choice.searchText.includes(keyword);
  });
  renderBuildingOptionsForList(fields, options, filter.trim(), { manageOpenState });
}

export function renderBuildingOptionsForList(fields, options, rawKeyword = "", { manageOpenState = true } = {}) {
  const list = document.querySelector("#buildingOptions");
  // Preserve open state so programmatic re-renders (e.g. background refresh)
  // don't snap the dropdown closed while the user is looking at it.
  const wasOpen = list.classList.contains("open");
  list.innerHTML = "";
  setState("buildingActiveIndex", -1);
  fields.buildingSearch.removeAttribute("aria-activedescendant");

  if (options.length === 0 && rawKeyword) {
    const empty = document.createElement("div");
    empty.className = "combo-empty";
    empty.textContent = t("form.buildingNoResults");
    list.append(empty);
    if (manageOpenState) { list.classList.add("open"); fields.buildingSearch.setAttribute("aria-expanded", "true"); }
    return;
  }
  if (options.length === 0) {
    if (manageOpenState) { list.classList.remove("open"); fields.buildingSearch.setAttribute("aria-expanded", "false"); }
    return;
  }

  if (!manageOpenState) {
    // Called from applyBuildingsData — leave open state as-is.
    if (wasOpen) { list.classList.add("open"); fields.buildingSearch.setAttribute("aria-expanded", "true"); }
  } else if (rawKeyword || document.activeElement === fields.buildingSearch) {
    list.classList.add("open");
    fields.buildingSearch.setAttribute("aria-expanded", "true");
  } else {
    list.classList.remove("open");
    fields.buildingSearch.setAttribute("aria-expanded", "false");
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
  fields.buildingSearch.setAttribute("aria-expanded", "false");
  setState("buildingActiveIndex", -1);
  fields.buildingSearch.removeAttribute("aria-activedescendant");
}

export function chooseDefaultBuildingForCampus(fields) {
  const campusVal = fields.campusGroupId?.value;
  const campusChoices = campusVal ? choicesForCurrentCampus(fields) : [];
  const defaultChoice = campusChoices[0] || preferredChoice() || buildingChoices[0];
  if (defaultChoice) fields.buildingSearch.value = defaultChoice.displayLabel;
}

export function syncSelectedBuilding(fields) {
  const selected = selectedBuilding(fields);
  if (!selected) return;
  fields.client.value = selected.client;
  fields.campusName.value = selected.campusName;
  fields.buildingId.value = selected.id;
  fields.buildingName.value = selected.name;
  fields.campusGroupId.value = selected.campusGroup;
  // Sync campus search display
  const campus = _CAMPUS_GROUPS.find((c) => c.value === selected.campusGroup);
  if (campus && fields.campusSearch) fields.campusSearch.value = t(campus.labelKey);
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
  const result = resolveBuildingMatch(fields, fields.buildingSearch.value, fields.campusGroupId?.value);
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
    (choice) => choice.variants.some(
      (b) => b.client === BUILDING_DEFAULTS.client && b.id === BUILDING_DEFAULTS.buildingId
    )
  );
}

function choicesForCurrentCampus(fields) {
  return buildingChoices.filter((choice) => choice.campusGroup === fields?.campusGroupId?.value);
}

// ── Master loader (with localStorage cache) ───────────────────────

export async function loadBuildings(fields, { setMessageKey } = {}) {
  if (!canUseBackend()) {
    await loadStaticBuildings(fields);
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
    await loadStaticBuildings(fields);
    if (setMessageKey) setMessageKey("message.staticMode");
  }
}

function applyBuildingsData(campusData, fields) {
  setState("campuses", campusData);
  const flat = flattenBuildings(campusData);
  setState("allBuildings", flat);
  setState("buildingChoices", mergeBuildingChoices(flat));
  renderCampusOptions(fields);
  // Sync campus search display
  {
    const cur = fields.campusGroupId.value || "yuehai";
    const campus = _CAMPUS_GROUPS.find((c) => c.value === cur);
    if (campus && fields.campusSearch) fields.campusSearch.value = t(campus.labelKey);
  }
  chooseDefaultBuildingForCampus(fields);
  // Pass manageOpenState:false so renderBuildingOptions only rebuilds
  // the option list — it won't touch open/closed state.  That keeps
  // background refreshes from snapping the dropdown closed.
  renderBuildingOptions(fields, "", { manageOpenState: false });
  syncSelectedBuilding(fields);

  // On first page load, gently animate the building dropdown open
  // to hint that the user can directly select a building.
  // Deferred via setTimeout so the forced reflow doesn't block the
  // initial paint / event loop — otherwise clicks feel laggy.
  if (_firstLoad) {
    _firstLoad = false;
    const list = document.querySelector("#buildingOptions");
    if (list && list.childElementCount > 0) {
      setTimeout(() => {
        // Paint one frame at opacity:0 so the animation entry is invisible.
        list.style.opacity = "0";
        list.classList.add("open");
        fields.buildingSearch.setAttribute("aria-expanded", "true");
        requestAnimationFrame(() => {
          // Clear inline opacity and start the CSS animation in the same
          // rAF tick — the browser sees the animation's from {opacity:0}
          // and paints no flash frame.
          list.style.opacity = "";
          list.classList.add("open-animated");
        });
      }, 0);
    }
  }
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

export async function loadStaticBuildings(fields) {
  try {
    const data = await _fetchJSON('buildings-fallback.json');
    applyBuildingsData(data, fields);
  } catch {
    // Ultimate fallback: one building so the UI doesn't break
    applyBuildingsData([{
      client: BUILDING_DEFAULTS.client,
      name: BUILDING_DEFAULTS.campusName,
      buildings: [{ id: BUILDING_DEFAULTS.buildingId, name: BUILDING_DEFAULTS.buildingName }],
    }], fields);
  }
}

/** Lazy-load demo status data (used only when user clicks "载入演示"). */
export async function fetchDemoStatus() {
  try {
    return await _fetchJSON('demo-status.json');
  } catch {
    return null;
  }
}
