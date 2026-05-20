const form = document.querySelector("#queryForm");
const demoButton = document.querySelector("#demoButton");
const message = document.querySelector("#message");
const heroStatus = document.querySelector("#heroStatus");

const fields = {
  campusGroup: document.querySelector("#campusGroup"),
  client: document.querySelector("#client"),
  campusName: document.querySelector("#campusName"),
  buildingSearch: document.querySelector("#buildingSearch"),
  buildingId: document.querySelector("#buildingId"),
  buildingName: document.querySelector("#buildingName"),
  roomName: document.querySelector("#roomName"),
  days: document.querySelector("#days"),
};

const view = {
  remaining: document.querySelector("#remaining"),
  dailyAvg: document.querySelector("#dailyAvg"),
  daysLeft: document.querySelector("#daysLeft"),
  totalUsed: document.querySelector("#totalUsed"),
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

let campuses = [];
let allBuildings = [];
let buildingChoices = [];

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  syncSelectedBuilding();
  await loadStatus("/api/status?" + new URLSearchParams(new FormData(form)));
});

fields.campusGroup.addEventListener("change", () => {
  chooseDefaultBuildingForCampus();
  renderBuildingOptions();
  syncSelectedBuilding();
});

fields.buildingSearch.addEventListener("change", syncSelectedBuilding);
fields.buildingSearch.addEventListener("input", () => {
  renderBuildingOptions(fields.buildingSearch.value);
});
fields.buildingSearch.addEventListener("focus", () => {
  renderBuildingOptions("");
});

document.addEventListener("click", (event) => {
  if (!event.target.closest(".combo")) {
    closeBuildingOptions();
  }
});

demoButton.addEventListener("click", async () => {
  await loadStatus("/api/demo-status");
});

loadBuildings();

async function loadBuildings() {
  try {
    const response = await fetch("/api/buildings");
    const payload = await response.json();
    if (Array.isArray(payload.data) && payload.data.length > 0) {
      campuses = normalizeCampuses(payload.data);
      allBuildings = flattenBuildings(campuses);
      buildingChoices = mergeBuildingChoices(allBuildings);
      renderCampusOptions();
      chooseDefaultBuildingForCampus();
      renderBuildingOptions();
      syncSelectedBuilding();
    }
  } catch {
    setMessage("暂时无法加载校区楼栋列表，已使用默认选项。", true);
  }
}

function normalizeCampuses(data) {
  if (data[0]?.client && Array.isArray(data[0]?.buildings)) {
    return data;
  }
  return [
    {
      client: "192.168.84.87",
      name: "粤海",
      buildings: data.map((building) => ({
        id: building.id,
        name: building.name,
      })),
    },
  ];
}

function flattenBuildings(campusData) {
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

function mergeBuildingChoices(buildings) {
  const groups = new Map();
  for (const building of buildings) {
    const key = `${building.campusGroup}:${baseBuildingName(building.name)}`;
    const current = groups.get(key) || {
      displayName: baseBuildingName(building.name),
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
    variants: group.variants.sort((a, b) => (a.minFloor || 0) - (b.minFloor || 0)),
  }));
}

function baseBuildingName(name) {
  return name
    .replace(/阁?\d+\s*-\s*\d+层?/g, "")
    .replace(/\d+\s*-\s*\d+楼/g, "")
    .replace(/\d+\s*-\s*\d+$/g, "")
    .replace(/阁$/, "")
    .trim();
}

function renderCampusOptions() {
  const preferredCampus = fields.campusGroup.value || "yuehai";
  const campusGroups = [
    { value: "yuehai", label: "粤海" },
    { value: "lihu", label: "丽湖" },
  ].filter((group) => allBuildings.some((building) => building.campusGroup === group.value));

  fields.campusGroup.innerHTML = "";
  for (const campus of campusGroups) {
    const option = document.createElement("option");
    option.value = campus.value;
    option.textContent = campus.label;
    if (campus.value === preferredCampus) {
      option.selected = true;
    }
    fields.campusGroup.append(option);
  }
}

function renderBuildingOptions(filter = "") {
  const keyword = filter.trim().toLowerCase();
  const options = buildingChoices
    .filter((choice) => {
      if (!keyword && choice.campusGroup !== fields.campusGroup.value) {
        return false;
      }
      if (!keyword) {
        return true;
      }
      return (
        choice.displayName.toLowerCase().includes(keyword) ||
        choice.sourceCampusName.toLowerCase().includes(keyword) ||
        choice.variants.some((building) => building.name.toLowerCase().includes(keyword))
      );
    })
    .slice(0, 5);

  const list = document.querySelector("#buildingOptions");
  list.innerHTML = "";
  list.classList.toggle("open", options.length > 0);
  for (const choice of options) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "combo-option";
    button.innerHTML = `${choice.displayName}<small>${choice.campusName} · ${choice.sourceCampusName}</small>`;
    button.addEventListener("click", () => {
      fields.buildingSearch.value = choice.displayName;
      syncSelectedBuilding();
      closeBuildingOptions();
    });
    list.append(button);
  }
}

async function loadStatus(url) {
  setBusy(true);
  setMessage("正在查询电费余额...");
  try {
    const response = await fetch(url);
    const payload = await response.json();
    if (!payload.ok) {
      throw new Error(payload.hint || payload.error || "查询失败");
    }
    renderStatus(payload.data);
    setMessage("查询完成。");
  } catch (error) {
    setMessage(error.message, true);
    setHeroStatus("查询失败", "critical");
  } finally {
    setBusy(false);
  }
}

function renderStatus(data) {
  const remaining = numberOrNull(data.remaining);
  view.remaining.textContent = formatNumber(remaining);
  view.dailyAvg.textContent = formatNumber(data.daily_avg_kwh);
  view.daysLeft.textContent = data.est_days_left == null ? "--" : formatNumber(data.est_days_left);
  view.totalUsed.textContent = formatNumber(data.total_used_kwh);
  view.roomLabel.textContent = `${data.campus_name || "--"} ${data.building_name || "--"} ${data.room_name || "--"}`;
  view.lastRecord.textContent = data.last_record || "--";
  view.records.textContent = `${data.records ?? 0} 条`;

  if (data.period) {
    view.period.textContent = `${data.period.begin} 至 ${data.period.end}`;
  } else {
    view.period.textContent = "--";
  }

  const status = data.status || "unknown";
  view.statusBadge.className = `badge ${status}`;
  view.statusBadge.textContent = statusText(status);
  setHeroStatus(statusText(status), status);

  const threshold = Number(data.threshold_kwh || 20);
  const meterMax = Math.max(threshold * 3, 60);
  const percent = remaining == null ? 0 : Math.max(0, Math.min(100, (remaining / meterMax) * 100));
  view.meterFill.style.width = `${percent}%`;
  view.meterFill.style.background = statusColor(status);

  renderRecharges(data.recharges || []);
  renderTrend(data.trend || []);
}

function renderRecharges(recharges) {
  view.rechargeCount.textContent = `${recharges.length} 条`;
  view.rechargeList.innerHTML = "";
  view.rechargeList.classList.toggle("empty", recharges.length === 0);

  if (recharges.length === 0) {
    view.rechargeList.textContent = "暂无数据";
    return;
  }

  for (const item of recharges.slice(0, 5)) {
    const row = document.createElement("div");
    row.className = "recharge-item";
    row.innerHTML = `
      <div>
        <strong>+${formatNumber(item.kwh)} kWh</strong>
        <span>${item.time || "未知时间"} · ${item.method || "未知方式"}</span>
      </div>
      <strong>${formatNumber(item.yuan)} 元</strong>
    `;
    view.rechargeList.append(row);
  }
}

function renderTrend(trend) {
  const points = trend.filter((item) => numberOrNull(item.remaining) != null).slice(-30);
  view.trendChart.innerHTML = "";
  view.trendChart.classList.toggle("empty", points.length < 2);

  if (points.length < 2) {
    view.trendChart.textContent = "暂无趋势数据";
    view.chartRange.textContent = "暂无数据";
    return;
  }

  const width = 920;
  const height = 280;
  const padding = { top: 18, right: 28, bottom: 42, left: 54 };
  const plotWidth = width - padding.left - padding.right;
  const plotHeight = height - padding.top - padding.bottom;
  const remainingValues = points.map((item) => Number(item.remaining));
  const usedValues = points.map((item) => Number(item.daily_used_kwh || 0));
  const maxRemaining = Math.max(...remainingValues, 1);
  const minRemaining = Math.min(...remainingValues, 0);
  const maxUsed = Math.max(...usedValues, 1);
  const x = (index) => padding.left + (index / (points.length - 1)) * plotWidth;
  const y = (value) => {
    const range = Math.max(maxRemaining - minRemaining, 1);
    return padding.top + (1 - (value - minRemaining) / range) * plotHeight;
  };
  const barWidth = Math.max(6, Math.min(22, plotWidth / points.length / 2));
  const line = points.map((item, index) => `${x(index)},${y(Number(item.remaining))}`).join(" ");
  const area = `${padding.left},${height - padding.bottom} ${line} ${width - padding.right},${height - padding.bottom}`;

  const bars = points.map((item, index) => {
    const barHeight = (Number(item.daily_used_kwh || 0) / maxUsed) * (plotHeight * 0.42);
    const bx = x(index) - barWidth / 2;
    const by = height - padding.bottom - barHeight;
    return `<rect class="chart-bar" x="${bx}" y="${by}" width="${barWidth}" height="${barHeight}" rx="3"></rect>`;
  }).join("");

  const dots = points.map((item, index) => (
    `<circle class="chart-dot" cx="${x(index)}" cy="${y(Number(item.remaining))}" r="4"></circle>`
  )).join("");

  const firstDate = shortDate(points[0].date);
  const lastDate = shortDate(points[points.length - 1].date);
  view.chartRange.textContent = `${firstDate} 至 ${lastDate}`;

  view.trendChart.innerHTML = `
    <svg viewBox="0 0 ${width} ${height}" role="img" aria-label="余额与用电趋势图">
      <line class="chart-axis" x1="${padding.left}" y1="${height - padding.bottom}" x2="${width - padding.right}" y2="${height - padding.bottom}"></line>
      <line class="chart-axis" x1="${padding.left}" y1="${padding.top}" x2="${padding.left}" y2="${height - padding.bottom}"></line>
      <line class="chart-grid" x1="${padding.left}" y1="${padding.top}" x2="${width - padding.right}" y2="${padding.top}"></line>
      <line class="chart-grid" x1="${padding.left}" y1="${padding.top + plotHeight / 2}" x2="${width - padding.right}" y2="${padding.top + plotHeight / 2}"></line>
      ${bars}
      <polygon class="chart-area" points="${area}"></polygon>
      <polyline class="chart-line" points="${line}"></polyline>
      ${dots}
      <text class="chart-label" x="${padding.left}" y="${height - 14}">${firstDate}</text>
      <text class="chart-label" x="${width - padding.right - 52}" y="${height - 14}">${lastDate}</text>
      <text class="chart-label" x="${padding.left}" y="14">余额 kWh</text>
      <text class="chart-label" x="${width - padding.right - 88}" y="14">柱: 日用电</text>
    </svg>
  `;
}

function chooseDefaultBuildingForCampus() {
  const defaultChoice = preferredChoice() || choicesForCurrentCampus()[0] || buildingChoices[0];
  if (defaultChoice) {
    fields.buildingSearch.value = defaultChoice.displayName;
  }
}

function syncSelectedBuilding() {
  const selected = selectedBuilding();
  if (!selected) {
    return;
  }
  fields.client.value = selected.client;
  fields.campusName.value = selected.campusName;
  fields.buildingId.value = selected.id;
  fields.buildingName.value = selected.name;
  fields.campusGroup.value = selected.campusGroup;
}

function selectedBuilding() {
  const text = fields.buildingSearch.value.trim();
  const exactChoice = buildingChoices.find((item) => item.displayName === text);
  if (exactChoice) {
    return pickVariantForRoom(exactChoice.variants);
  }

  const choices = choicesForCurrentCampus();
  const choice =
    choices.find((item) => item.displayName === text) ||
    choices.find((item) => item.displayName.includes(text)) ||
    preferredChoice() ||
    choices[0] ||
    buildingChoices[0];

  if (!choice) {
    return null;
  }

  return pickVariantForRoom(choice.variants);
}

function pickVariantForRoom(variants) {
  const floor = roomFloor(fields.roomName.value);
  if (floor != null) {
    const matched = variants.find((building) => {
      if (building.minFloor == null || building.maxFloor == null) {
        return false;
      }
      return floor >= building.minFloor && floor <= building.maxFloor;
    });
    if (matched) {
      return matched;
    }
  }
  return variants[0];
}

function preferredChoice() {
  return buildingChoices.find(
    (choice) => choice.variants.some((building) => building.client === "192.168.84.87" && building.id === "7126")
  );
}

function choicesForCurrentCampus() {
  return buildingChoices.filter((choice) => choice.campusGroup === fields.campusGroup.value);
}

function closeBuildingOptions() {
  document.querySelector("#buildingOptions").classList.remove("open");
}

function roomFloor(roomName) {
  const match = String(roomName || "").match(/\d+/);
  if (!match) {
    return null;
  }
  const digits = match[0];
  if (digits.length < 3) {
    return null;
  }
  return Number(digits.slice(0, -2));
}

function floorRange(name) {
  const match = name.match(/(\d+)\s*-\s*(\d+)(?:层|楼)?/);
  if (!match) {
    return { minFloor: null, maxFloor: null };
  }
  return { minFloor: Number(match[1]), maxFloor: Number(match[2]) };
}

function setBusy(isBusy) {
  form.querySelectorAll("button, input, select").forEach((element) => {
    element.disabled = isBusy;
  });
}

function setMessage(text, isError = false) {
  message.textContent = text;
  message.classList.toggle("error", isError);
}

function setHeroStatus(text, status = "unknown") {
  heroStatus.querySelector("span:last-child").textContent = text;
  heroStatus.querySelector(".pulse").style.background = statusColor(status);
}

function statusText(status) {
  return {
    ok: "电量充足",
    low: "低电量",
    critical: "即将耗尽",
    unknown: "暂无数据",
  }[status] || "暂无数据";
}

function statusColor(status) {
  return {
    ok: "#0f9f6e",
    low: "#d98616",
    critical: "#d73939",
    unknown: "#657386",
  }[status] || "#657386";
}

function numberOrNull(value) {
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

function formatNumber(value) {
  const number = numberOrNull(value);
  if (number == null) {
    return "--";
  }
  return number.toLocaleString("zh-CN", {
    maximumFractionDigits: 2,
    minimumFractionDigits: Number.isInteger(number) ? 0 : 1,
  });
}

function shortDate(value) {
  const text = String(value || "");
  return text.length >= 10 ? text.slice(5, 10) : text || "--";
}
