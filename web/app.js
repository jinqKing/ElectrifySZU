const form = document.querySelector("#queryForm");
const subscriptionForm = document.querySelector("#subscriptionForm");
const demoButton = document.querySelector("#demoButton");
const message = document.querySelector("#message");
const heroStatus = document.querySelector("#heroStatus");
const languageButtons = document.querySelectorAll("[data-lang]");

const fields = {
  campusGroup: document.querySelector("#campusGroup"),
  client: document.querySelector("#client"),
  campusName: document.querySelector("#campusName"),
  buildingSearch: document.querySelector("#buildingSearch"),
  buildingId: document.querySelector("#buildingId"),
  buildingName: document.querySelector("#buildingName"),
  roomName: document.querySelector("#roomName"),
  days: document.querySelector("#days"),
  subscriberEmail: document.querySelector("#subscriberEmail"),
};

const view = {
  remaining: document.querySelector("#remaining"),
  dailyAvg: document.querySelector("#dailyAvg"),
  daysLeft: document.querySelector("#daysLeft"),
  daysLeftDate: document.querySelector("#daysLeftDate"),
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
let currentStatusData = null;
let lastMessage = { key: "message.initial", values: {}, isError: false, raw: null };
let lastHeroStatus = { key: "status.waiting", values: {}, status: "unknown", raw: null };

const API_BASE = window.ELECTRIFYSZU_API_BASE || "";
const IS_STATIC_PAGE =
  location.protocol === "file:" ||
  location.hostname.endsWith(".github.io") ||
  location.hostname === "github.io";
const DEFAULT_LOCALE = "zh-CN";
const LOCALE_QUERY = {
  zh: "zh-CN",
  "zh-CN": "zh-CN",
  en: "en-US",
  "en-US": "en-US",
};
const translations = {
  "zh-CN": {
    "meta.title": "ElectrifySZU 深大宿舍电费快查",
    "hero.title": "宿舍不断电：电费仪表盘",
    "hero.subtitle": "搜索宿舍楼栋并输入房间号，自动完成查询并展示余额和使用情况。",
    "query.ariaLabel": "查询条件",
    "form.campus": "校区",
    "form.building": "宿舍楼栋",
    "form.buildingPlaceholder": "搜索宿舍楼栋",
    "form.room": "房间号",
    "form.roomPlaceholder": "例如 713",
    "form.days": "统计天数",
    "form.submit": "查询余额",
    "form.demo": "载入演示",
    "subscribe.email": "预警邮箱",
    "subscribe.submit": "订阅低电量预警",
    "subscribe.saving": "正在保存订阅...",
    "subscribe.saved": "订阅已保存。余额低于阈值时，系统每天最多发送一次预警邮件。",
    "subscribe.needsBackend": "订阅功能需要后端服务，GitHub Pages 预览页不会保存邮箱。",
    "message.initial": "连接校园网后查询真实余额，可先载入演示数据预览效果。",
    "message.staticPage": "GitHub Pages 只能托管静态页面，真实查询需要运行本地后端：uv run electrifyszu，或部署一个可访问的后端 API。",
    "message.staticMode": "当前为静态页面模式，真实查询需要连接后端服务。",
    "message.demoLoaded": "已载入静态演示数据。",
    "message.loading": "正在查询电费余额...",
    "message.complete": "查询完成。",
    "error.nonJson": "当前地址没有返回 JSON API。请确认后端服务已启动，且前端请求地址指向后端。",
    "error.requestFailed": "请求失败",
    "error.queryFailed": "查询失败",
    "metrics.remaining": "当前余额",
    "metrics.dailyAvg": "日均用电",
    "metrics.daysLeft": "预计可用",
    "metrics.totalUsed": "周期用电",
    "unit.days": "days",
    "unit.yuan": "元",
    "chart.ariaLabel": "用电趋势",
    "chart.title": "余额与用电趋势",
    "chart.note": "余额走势和每日用电量会在查询后自动更新。",
    "chart.svgLabel": "余额与用电趋势图",
    "chart.balanceLabel": "余额 kWh",
    "chart.dailyUseLabel": "柱: 日用电",
    "details.warning": "预警状态",
    "details.room": "房间",
    "details.lastRecord": "最近记录",
    "details.period": "统计周期",
    "details.records": "记录数",
    "recharge.title": "最近充值",
    "status.waiting": "等待查询",
    "status.needBackend": "需要后端",
    "status.queryFailed": "查询失败",
    "status.unchecked": "未查询",
    "powerStatus.ok": "电量充足",
    "powerStatus.low": "低电量",
    "powerStatus.critical": "即将耗尽",
    "powerStatus.unknown": "暂无数据",
    "empty.noData": "暂无数据",
    "empty.noTrend": "暂无趋势数据",
    "empty.unknownTime": "未知时间",
    "empty.unknownMethod": "未知方式",
    "format.records": "{count} 条",
    "format.dateRange": "{begin} 至 {end}",
    "campus.yuehai": "粤海 / Yuehai",
    "campus.lihu": "丽湖 / Lihu",
    "payment.wechat": "微信支付",
    "payment.alipay": "支付宝",
  },
  "en-US": {
    "meta.title": "ElectrifySZU SZU Dorm Power Monitor",
    "hero.title": "Dorm Power Dashboard",
    "hero.subtitle": "Search a dorm building, enter a room number, and check the balance and recent usage.",
    "query.ariaLabel": "Query filters",
    "form.campus": "Campus",
    "form.building": "Dorm building",
    "form.buildingPlaceholder": "Search dorm building",
    "form.room": "Room",
    "form.roomPlaceholder": "e.g. 713",
    "form.days": "Days",
    "form.submit": "Check balance",
    "form.demo": "Load demo",
    "subscribe.email": "Alert email",
    "subscribe.submit": "Subscribe to low-balance alerts",
    "subscribe.saving": "Saving subscription...",
    "subscribe.saved": "Subscription saved. The system sends at most one low-balance alert per day.",
    "subscribe.needsBackend": "Subscriptions need the backend service; the GitHub Pages preview will not save email addresses.",
    "message.initial": "Connect to the campus network for live balances, or load demo data to preview the dashboard.",
    "message.staticPage": "GitHub Pages can only host the static page. Live queries need the local backend: uv run electrifyszu, or a deployed API endpoint.",
    "message.staticMode": "Static page mode is active. Live queries need a backend service.",
    "message.demoLoaded": "Static demo data loaded.",
    "message.loading": "Checking power balance...",
    "message.complete": "Query complete.",
    "error.nonJson": "This address did not return a JSON API response. Confirm the backend is running and the frontend points to it.",
    "error.requestFailed": "Request failed",
    "error.queryFailed": "Query failed",
    "metrics.remaining": "Current balance",
    "metrics.dailyAvg": "Daily average",
    "metrics.daysLeft": "Estimated days",
    "metrics.totalUsed": "Period usage",
    "unit.days": "days",
    "unit.yuan": "yuan",
    "chart.ariaLabel": "Power usage trend",
    "chart.title": "Balance and Usage Trend",
    "chart.note": "Balance history and daily usage update automatically after a query.",
    "chart.svgLabel": "Balance and usage trend chart",
    "chart.balanceLabel": "Balance kWh",
    "chart.dailyUseLabel": "Bars: daily use",
    "details.warning": "Warning status",
    "details.room": "Room",
    "details.lastRecord": "Latest record",
    "details.period": "Period",
    "details.records": "Records",
    "recharge.title": "Recent top-ups",
    "status.waiting": "Waiting",
    "status.needBackend": "Backend needed",
    "status.queryFailed": "Query failed",
    "status.unchecked": "Not checked",
    "powerStatus.ok": "Enough power",
    "powerStatus.low": "Low power",
    "powerStatus.critical": "Nearly depleted",
    "powerStatus.unknown": "No data",
    "empty.noData": "No data",
    "empty.noTrend": "No trend data",
    "empty.unknownTime": "Unknown time",
    "empty.unknownMethod": "Unknown method",
    "format.records": "{count} records",
    "format.dateRange": "{begin} to {end}",
    "campus.yuehai": "粤海 / Yuehai",
    "campus.lihu": "丽湖 / Lihu",
    "payment.wechat": "WeChat Pay",
    "payment.alipay": "Alipay",
  },
};
const campusLabels = {
  粤海: "粤海 / Yuehai",
  丽湖: "丽湖 / Lihu",
};
const sourceCampusLabels = {
  北校区: "北校区",
  南校区: "南校区",
  丽湖校区: "丽湖校区",
  深大新斋区: "深大新斋区",
};
const buildingEnglishNames = {
  "乔林阁": "Qiaolin Hall",
  "乔木阁": "Qiaomu Hall",
  "乔森阁": "Qiaosen Hall",
  "乔相阁": "Qiaoxiang Hall",
  "乔梧阁": "Qiaowu Hall",
  "山茶斋": "Shancha Zhai",
  "红榴斋": "Hongliu Zhai",
  "米兰斋": "Milan Zhai",
  "海桐斋": "Haitong Zhai",
  "桃李斋": "Taoli Zhai",
  "凌霄斋": "Lingxiao Zhai",
  "银桦斋": "Yinhua Zhai",
  "木犀轩": "Muxi Xuan",
  "丹枫轩": "Danfeng Xuan",
  "紫檀轩": "Zitan Xuan",
  "石楠轩": "Shinan Xuan",
  "苏铁轩": "Sutie Xuan",
  "芸香阁": "Yunxiang Hall",
  "丁香阁": "Dingxiang Hall",
  "文杏阁": "Wenxing Hall",
  "海棠阁": "Haitang Hall",
  "疏影阁": "Shuying Hall",
  "杜衡阁": "Duheng Hall",
  "辛夷阁": "Xinyi Hall",
  "韵竹阁": "Yunzhu Hall",
  "云杉轩": "Yunshan Xuan",
  "紫藤轩": "Ziteng Xuan",
  "留学生公寓": "International Student Apartment",
  "春笛": "Chundi",
  "夏筝": "Xiazheng",
  "秋瑟": "Qiuse",
  "冬筑": "Dongzhu",
  "A栋风信子": "Building A Hyacinth",
  "B栋山楂树": "Building B Hawthorn",
  "C栋胡杨林": "Building C Poplar",
  "风槐斋": "Fenghuai Zhai",
  "雨鹃斋": "Yujuan Zhai",
  "蓬莱客舍": "Penglai House",
  "聚翰斋": "Juhan Zhai",
  "紫薇斋": "Ziwei Zhai",
  "红豆斋": "Hongdou Zhai",
};
let currentLocale = resolveInitialLocale();
const loadingStatusController = window.ElectrifySZULoadingStatus?.createController(message, loadingStatusOptions()) || null;

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  syncSelectedBuilding();
  if (!canUseBackend()) {
    setMessageKey("message.staticPage", {}, true);
    setHeroStatusKey("status.needBackend", {}, "critical");
    return;
  }
  await loadStatus(apiUrl("/api/status") + "?" + new URLSearchParams(new FormData(form)));
});

subscriptionForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  syncSelectedBuilding();
  if (!canUseBackend()) {
    setMessageKey("subscribe.needsBackend", {}, true);
    setHeroStatusKey("status.needBackend", {}, "critical");
    return;
  }
  await saveSubscription();
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
  setMessageKey("message.demoLoaded");
});

languageButtons.forEach((button) => {
  button.addEventListener("click", () => {
    setLanguage(button.dataset.lang);
  });
});

setLanguage(currentLocale, { persist: false });
loadBuildings();

async function loadBuildings() {
  if (!canUseBackend()) {
    loadStaticBuildings();
    setMessageKey("message.staticPage");
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
    setMessageKey("message.staticMode");
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
    throw new Error(t("error.nonJson"));
  }

  const payload = await response.json();
  if (!response.ok) {
    throw new Error(payload.hint || payload.error || t("error.requestFailed"));
  }
  return payload;
}

async function postJson(url, data) {
  const response = await fetch(url, {
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
    throw new Error(payload.hint || payload.error || t("error.requestFailed"));
  }
  return payload;
}

async function saveSubscription() {
  setSubscriptionBusy(true);
  setMessageKey("subscribe.saving");
  try {
    const payload = await postJson(apiUrl("/api/subscriptions"), {
      email: fields.subscriberEmail.value,
      client: fields.client.value,
      campusName: fields.campusName.value,
      buildingId: fields.buildingId.value,
      buildingName: fields.buildingName.value,
      roomName: fields.roomName.value,
    });
    setMessageRaw(payload.message || t("subscribe.saved"));
  } catch (error) {
    setMessageRaw(error.message, true);
  } finally {
    setSubscriptionBusy(false);
  }
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
      group.displayName,
      group.displayLabel,
      buildingEnglishName(group.displayName),
      group.campusName,
      bilingualCampusName(group.campusName),
      ...group.sourceCampusNames,
      ...[...group.sourceCampusNames].map(bilingualSourceCampusName),
      ...group.variants.map((building) => building.name),
      ...group.variants.map((building) => bilingualBuildingName(building.name)),
    ].join(" ").toLowerCase(),
    variants: group.variants.sort((a, b) => (a.minFloor || 0) - (b.minFloor || 0)),
  }));
}

function baseBuildingName(name) {
  const base = name
    .replace(/\d+\s*-\s*\d+\s*楼/g, "")
    .replace(/\d+\s*-\s*\d+\s*层/g, "")
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
    { value: "yuehai", labelKey: "campus.yuehai" },
    { value: "lihu", labelKey: "campus.lihu" },
  ].filter((group) => allBuildings.some((building) => building.campusGroup === group.value));

  fields.campusGroup.innerHTML = "";
  for (const campus of campusGroups) {
    const option = document.createElement("option");
    option.value = campus.value;
    option.dataset.i18n = campus.labelKey;
    option.textContent = t(campus.labelKey);
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
      return choice.searchText.includes(keyword);
    });

  const list = document.querySelector("#buildingOptions");
  list.innerHTML = "";
  list.classList.toggle("open", options.length > 0);
  for (const choice of options) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "combo-option";
    button.innerHTML = `${choice.displayLabel}<small>${bilingualCampusName(choice.campusName)} · ${choice.sourceCampusLabel}</small>`;
    button.addEventListener("click", () => {
      fields.buildingSearch.value = choice.displayLabel;
      syncSelectedBuilding();
      closeBuildingOptions();
    });
    list.append(button);
  }
}

async function loadStatus(url) {
  setBusy(true);
  startLoadingMessage();
  try {
    const payload = await fetchJson(url);
    if (!payload.ok) {
      throw new Error(payload.hint || payload.error || t("error.queryFailed"));
    }
    renderStatus(payload.data);
    setMessageKey("message.complete");
  } catch (error) {
    setMessageRaw(error.message, true);
    setHeroStatusKey("status.queryFailed", {}, "critical");
  } finally {
    setBusy(false);
  }
}

function renderStatus(data) {
  currentStatusData = data;
  const remaining = numberOrNull(data.remaining);
  view.remaining.textContent = formatNumber(remaining);
  view.dailyAvg.textContent = formatNumber(data.daily_avg_kwh);
  view.daysLeft.textContent = data.est_days_left == null ? "--" : formatNumber(data.est_days_left);
  view.daysLeftDate.textContent = formatEstimatedDateText(data.last_record, data.est_days_left);
  view.totalUsed.textContent = formatNumber(data.total_used_kwh);
  view.roomLabel.textContent = `${bilingualCampusName(data.campus_name) || "--"} ${bilingualBuildingName(data.building_name) || "--"} ${data.room_name || "--"}`;
  view.lastRecord.textContent = data.last_record || "--";
  view.records.textContent = formatRecordCount(data.records ?? 0);

  if (data.period) {
    view.period.textContent = t("format.dateRange", {
      begin: data.period.begin,
      end: data.period.end,
    });
  } else {
    view.period.textContent = "--";
  }

  const status = data.status || "unknown";
  view.statusBadge.className = `badge ${status}`;
  view.statusBadge.textContent = statusText(status);
  setHeroStatusRaw(statusText(status), status);

  const threshold = Number(data.threshold_kwh || 20);
  const meterMax = Math.max(threshold * 3, 60);
  const percent = remaining == null ? 0 : Math.max(0, Math.min(100, (remaining / meterMax) * 100));
  view.meterFill.style.width = `${percent}%`;
  view.meterFill.style.background = statusColor(status);

  renderRecharges(data.recharges || []);
  renderTrend(data.trend || []);
}

function renderRecharges(recharges) {
  view.rechargeCount.textContent = formatRecordCount(recharges.length);
  view.rechargeList.innerHTML = "";
  view.rechargeList.classList.toggle("empty", recharges.length === 0);

  if (recharges.length === 0) {
    view.rechargeList.textContent = t("empty.noData");
    return;
  }

  for (const item of recharges.slice(0, 5)) {
    const row = document.createElement("div");
    row.className = "recharge-item";
    row.innerHTML = `
      <div>
        <strong>+${formatNumber(item.kwh)} kWh</strong>
        <span>${item.time || t("empty.unknownTime")} · ${paymentMethodText(item.method)}</span>
      </div>
      <strong>${formatNumber(item.yuan)} ${t("unit.yuan")}</strong>
    `;
    view.rechargeList.append(row);
  }
}

function renderTrend(trend) {
  const points = trend.filter((item) => numberOrNull(item.remaining) != null).slice(-30);
  view.trendChart.innerHTML = "";
  view.trendChart.classList.toggle("empty", points.length < 2);

  if (points.length < 2) {
    view.trendChart.textContent = t("empty.noTrend");
    view.chartRange.textContent = t("empty.noData");
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
  view.chartRange.textContent = t("format.dateRange", {
    begin: firstDate,
    end: lastDate,
  });

  view.trendChart.innerHTML = `
    <svg viewBox="0 0 ${width} ${height}" role="img" aria-label="${t("chart.svgLabel")}">
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
      <text class="chart-label" x="${padding.left}" y="14">${t("chart.balanceLabel")}</text>
      <text class="chart-label" x="${width - padding.right - 96}" y="14">${t("chart.dailyUseLabel")}</text>
    </svg>
  `;
}

function chooseDefaultBuildingForCampus() {
  const defaultChoice = preferredChoice() || choicesForCurrentCampus()[0] || buildingChoices[0];
  if (defaultChoice) {
    fields.buildingSearch.value = defaultChoice.displayLabel;
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
  const normalizedText = text.toLowerCase();
  const exactChoice = buildingChoices.find(
    (item) => item.displayName === text || item.displayLabel === text || buildingEnglishName(item.displayName) === text
  );
  if (exactChoice) {
    return pickVariantForRoom(exactChoice.variants);
  }

  const choices = choicesForCurrentCampus();
  const choice =
    choices.find((item) => item.displayName === text || item.displayLabel === text) ||
    choices.find((item) => item.searchText.includes(normalizedText)) ||
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

function setSubscriptionBusy(isBusy) {
  subscriptionForm.querySelectorAll("button, input").forEach((element) => {
    element.disabled = isBusy;
  });
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

function statusText(status) {
  return {
    ok: t("powerStatus.ok"),
    low: t("powerStatus.low"),
    critical: t("powerStatus.critical"),
    unknown: t("powerStatus.unknown"),
  }[status] || t("powerStatus.unknown");
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
  return number.toLocaleString(currentLocale, {
    maximumFractionDigits: 2,
    minimumFractionDigits: Number.isInteger(number) ? 0 : 1,
  });
}

function formatRecordCount(count) {
  return t("format.records", { count });
}

function paymentMethodText(method) {
  if (!method) {
    return t("empty.unknownMethod");
  }
  return {
    微信支付: t("payment.wechat"),
    支付宝: t("payment.alipay"),
  }[method] || method;
}

function bilingualCampusName(name) {
  return campusLabels[name] || name || "";
}

function bilingualSourceCampusName(name) {
  return sourceCampusLabels[name] || name || "";
}

function bilingualBuildingName(name) {
  if (!name) {
    return "";
  }
  const english = buildingEnglishName(name);
  return english ? `${name} / ${english}` : name;
}

function buildingEnglishName(name) {
  if (!name) {
    return "";
  }
  const base = baseBuildingName(name);
  return buildingEnglishNames[base] || "";
}

function resolveInitialLocale() {
  const requested = new URLSearchParams(location.search).get("lang");
  const queryLocale = LOCALE_QUERY[requested];
  if (queryLocale) {
    return queryLocale;
  }

  try {
    const stored = localStorage.getItem("electrifyszu.locale");
    if (translations[stored]) {
      return stored;
    }
  } catch {
    // localStorage may be unavailable on some static hosts.
  }

  return DEFAULT_LOCALE;
}

function setLanguage(locale, options = {}) {
  if (!translations[locale]) {
    locale = DEFAULT_LOCALE;
  }
  currentLocale = locale;
  document.documentElement.lang = locale;
  document.title = t("meta.title");

  if (options.persist !== false) {
    try {
      localStorage.setItem("electrifyszu.locale", locale);
    } catch {
      // The language switch still works for the current page.
    }
  }

  languageButtons.forEach((button) => {
    const isSelected = button.dataset.lang === locale;
    button.classList.toggle("active", isSelected);
    button.setAttribute("aria-pressed", String(isSelected));
  });

  document.querySelectorAll("[data-i18n]").forEach((element) => {
    element.textContent = t(element.dataset.i18n);
  });
  document.querySelectorAll("[data-i18n-placeholder]").forEach((element) => {
    element.setAttribute("placeholder", t(element.dataset.i18nPlaceholder));
  });
  document.querySelectorAll("[data-i18n-aria-label]").forEach((element) => {
    element.setAttribute("aria-label", t(element.dataset.i18nAriaLabel));
  });

  if (buildingChoices.length > 0) {
    renderCampusOptions();
  }
  if (currentStatusData) {
    renderStatus(currentStatusData);
  } else {
    view.rechargeCount.textContent = formatRecordCount(0);
  }

  if (loadingStatusController?.isActive() && lastMessage.key === "message.loading") {
    loadingStatusController.updateConfig(loadingStatusOptions());
  } else if (lastMessage.raw != null) {
    setMessage(lastMessage.raw, lastMessage.isError);
  } else {
    setMessage(t(lastMessage.key, lastMessage.values), lastMessage.isError);
  }

  if (lastHeroStatus.raw != null) {
    setHeroStatus(lastHeroStatus.raw, lastHeroStatus.status);
  } else {
    setHeroStatus(t(lastHeroStatus.key, lastHeroStatus.values), lastHeroStatus.status);
  }
}

function t(key, values = {}) {
  const dictionary = translations[currentLocale] || translations[DEFAULT_LOCALE];
  const fallback = translations[DEFAULT_LOCALE][key] || key;
  return (dictionary[key] || fallback).replace(/\{(\w+)\}/g, (_, name) => values[name] ?? "");
}

function loadingStatusOptions() {
  return {
    locale: currentLocale,
    mainText: t("message.loading"),
  };
}

function startLoadingMessage() {
  lastMessage = { key: "message.loading", values: {}, isError: false, raw: null };
  if (!loadingStatusController) {
    setMessage(t("message.loading"));
    return;
  }
  message.classList.remove("error");
  loadingStatusController.start(loadingStatusOptions());
}

function shortDate(value) {
  const text = String(value || "");
  return text.length >= 10 ? text.slice(5, 10) : text || "--";
}

function formatEstimatedDateText(lastRecord, daysLeft) {
  const estimatedDate = estimateAvailableUntilDate(lastRecord, daysLeft);
  if (!estimatedDate) {
    return currentLocale === "zh-CN" ? "暂无预计日期" : "No estimated date";
  }
  return currentLocale === "zh-CN"
    ? `预计到 ${formatDisplayDate(estimatedDate)}`
    : `Until ${formatDisplayDate(estimatedDate)}`;
}

function estimateAvailableUntilDate(lastRecord, daysLeft) {
  const baseDate = parseIsoDate(lastRecord);
  const days = numberOrNull(daysLeft);
  if (!baseDate || days == null || days < 0) {
    return null;
  }
  const estimatedDate = new Date(baseDate);
  estimatedDate.setDate(estimatedDate.getDate() + Math.ceil(days));
  return estimatedDate;
}

function parseIsoDate(value) {
  if (value == null || value === "") {
    return null;
  }

  if (typeof value === "number" && Number.isFinite(value)) {
    const excelEpoch = new Date(1899, 11, 30);
    const date = new Date(excelEpoch);
    date.setDate(date.getDate() + Math.floor(value));
    return date;
  }

  const text = String(value).trim();
  const matchedDate = text.match(/(\d{4})[-/](\d{1,2})[-/](\d{1,2})/);
  if (matchedDate) {
    const [, yearText, monthText, dayText] = matchedDate;
    const year = Number(yearText);
    const month = Number(monthText);
    const day = Number(dayText);
    const date = new Date(year, month - 1, day);
    if (
      date.getFullYear() === year &&
      date.getMonth() === month - 1 &&
      date.getDate() === day
    ) {
      return date;
    }
  }

  const parsed = new Date(text);
  if (Number.isNaN(parsed.getTime())) {
    return null;
  }
  return new Date(parsed.getFullYear(), parsed.getMonth(), parsed.getDate());
}

function formatDisplayDate(date) {
  return new Intl.DateTimeFormat(currentLocale, {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(date);
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
