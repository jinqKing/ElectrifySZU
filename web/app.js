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

const API_BASE = window.ELECTRIFYSZU_API_BASE || "";
const IS_STATIC_PAGE =
  location.protocol === "file:" ||
  location.hostname.endsWith(".github.io") ||
  location.hostname === "github.io";
const STATIC_PAGE_MESSAGE =
  "GitHub Pages 只能托管静态页面，真实查询需要运行本地后端：uv run electrifyszu，或部署一个可访问的后端 API。";

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  syncSelectedBuilding();
  if (!canUseBackend()) {
    setMessage(STATIC_PAGE_MESSAGE, true);
    setHeroStatus("需要后端", "critical");
    return;
  }
  await loadStatus(apiUrl("/api/status") + "?" + new URLSearchParams(new FormData(form)));
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
  renderStatus(staticDemoStatus());
  setMessage("已载入静态演示数据。");
});

loadBuildings();

async function loadBuildings() {
  if (!canUseBackend()) {
    loadStaticBuildings();
    setMessage(STATIC_PAGE_MESSAGE);
    return;
  }

  try {
    const payload = await fetchJson(apiUrl("/api/buildings"));
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
    loadStaticBuildings();
    setMessage("当前为静态页面模式，真实查询需要连接后端服务。");
  }
}

function canUseBackend() {
  return Boolean(API_BASE) || !IS_STATIC_PAGE;
}

function apiUrl(path) {
  if (!API_BASE) {
    return path;
  }
  return new URL(path, API_BASE).toString();
}

async function fetchJson(url) {
  const response = await fetch(url);
  const contentType = (response.headers.get("content-type") || "").toLowerCase();
  if (!contentType.includes("application/json")) {
    throw new Error("当前地址没有返回 JSON API。请确认后端服务已启动，且前端请求地址指向后端。");
  }

  const payload = await response.json();
  if (!response.ok) {
    throw new Error(payload.hint || payload.error || "请求失败");
  }
  return payload;
}

function loadStaticBuildings() {
  campuses = staticCampuses();
  allBuildings = flattenBuildings(campuses);
  buildingChoices = mergeBuildingChoices(allBuildings);
  renderCampusOptions();
  chooseDefaultBuildingForCampus();
  renderBuildingOptions();
  syncSelectedBuilding();
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
  const base = name
    .replace(/阁?\d+\s*-\s*\d+层?/g, "")
    .replace(/\d+\s*-\s*\d+楼/g, "")
    .replace(/\d+\s*-\s*\d+$/g, "")
    .trim();
  if (base.startsWith("乔") && !base.endsWith("阁")) {
    return `${base}阁`;
  }
  return base;
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
      if (!keyword) {
        return true;
      }
      return (
        choice.displayName.toLowerCase().includes(keyword) ||
        choice.sourceCampusName.toLowerCase().includes(keyword) ||
        choice.variants.some((building) => building.name.toLowerCase().includes(keyword))
      );
    });

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
    const payload = await fetchJson(url);
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

function staticCampuses() {
  return [
    {
      client: "192.168.84.1",
      name: "北校区",
      buildings: [
        { id: "6363", name: "乔林11-12层" },
        { id: "6364", name: "乔木11-12层" },
        { id: "6875", name: "乔森阁2-10层" },
        { id: "6876", name: "乔森11-20层" },
        { id: "6877", name: "乔相阁2-10层" },
        { id: "6878", name: "乔相11-20层" },
        { id: "6121", name: "乔林阁1-10层" },
        { id: "6122", name: "乔木阁1-10层" },
        { id: "7724", name: "乔梧阁2-10层" },
        { id: "7725", name: "乔梧阁11-20" },
        { id: "54", name: "山茶斋" },
        { id: "55", name: "红榴斋" },
        { id: "56", name: "米兰斋" },
        { id: "57", name: "海桐斋" },
        { id: "58", name: "桃李斋" },
        { id: "59", name: "凌霄斋" },
        { id: "61", name: "银桦斋" },
        { id: "63", name: "木犀轩" },
        { id: "64", name: "丹枫轩" },
        { id: "65", name: "紫檀轩" },
        { id: "66", name: "石楠轩" },
        { id: "67", name: "苏铁轩" },
        { id: "68", name: "芸香阁" },
        { id: "69", name: "丁香阁" },
        { id: "70", name: "文杏阁" },
        { id: "71", name: "海棠阁" },
        { id: "72", name: "疏影阁" },
        { id: "73", name: "杜衡阁" },
        { id: "74", name: "辛夷阁" },
        { id: "75", name: "韵竹阁" },
        { id: "76", name: "云杉轩" },
        { id: "77", name: "紫藤轩" },
        { id: "8147", name: "留学生公寓" },
      ],
    },
    {
      client: "192.168.84.110",
      name: "南校区",
      buildings: [
        { id: "6875", name: "春笛3-8楼" },
        { id: "6876", name: "夏筝3-17楼" },
        { id: "6877", name: "秋瑟3-8楼" },
        { id: "6878", name: "冬筑3-6楼" },
        { id: "7119", name: "春笛9-17楼" },
        { id: "7828", name: "秋瑟9-17楼" },
        { id: "8240", name: "冬筑7-10楼" },
        { id: "8241", name: "冬筑11-14楼" },
        { id: "8242", name: "冬筑15-17楼" },
      ],
    },
    {
      client: "172.21.101.11",
      name: "丽湖校区",
      buildings: [
        { id: "10057", name: "A栋风信子" },
        { id: "10934", name: "B栋山楂树" },
        { id: "10935", name: "C栋胡杨林" },
      ],
    },
    {
      client: "192.168.84.87",
      name: "深大新斋区",
      buildings: [
        { id: "7126", name: "风槐斋" },
        { id: "7603", name: "雨鹃斋" },
        { id: "17887", name: "蓬莱客舍" },
        { id: "18118", name: "聚翰斋" },
        { id: "18119", name: "紫薇斋" },
        { id: "18120", name: "红豆斋" },
      ],
    },
  ];
}

function staticDemoStatus() {
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
