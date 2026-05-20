const form = document.querySelector("#queryForm");
const demoButton = document.querySelector("#demoButton");
const message = document.querySelector("#message");
const heroStatus = document.querySelector("#heroStatus");

const fields = {
  client: document.querySelector("#client"),
  campusName: document.querySelector("#campusName"),
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
};

let campuses = [];

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  syncNames();
  await loadStatus("/api/status?" + new URLSearchParams(new FormData(form)));
});

fields.client.addEventListener("change", () => {
  renderBuildingOptions();
  syncNames();
});

fields.buildingId.addEventListener("change", syncNames);

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
      renderCampusOptions();
      renderBuildingOptions();
      syncNames();
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
      name: "深大新斋区",
      buildings: data.map((building) => ({
        id: building.id,
        name: building.name,
      })),
    },
  ];
}

function renderCampusOptions() {
  const preferredClient = fields.client.value || "192.168.84.87";
  fields.client.innerHTML = "";
  for (const campus of campuses) {
    const option = document.createElement("option");
    option.value = campus.client;
    option.textContent = campus.name;
    option.dataset.name = campus.name;
    if (campus.client === preferredClient) {
      option.selected = true;
    }
    fields.client.append(option);
  }
}

function renderBuildingOptions() {
  const campus = selectedCampus();
  const preferredBuilding = campus?.client === "192.168.84.87" ? "7126" : "";
  fields.buildingId.innerHTML = "";
  for (const building of campus?.buildings || []) {
    const option = document.createElement("option");
    option.value = building.id;
    option.textContent = building.name;
    option.dataset.name = building.name;
    if (building.id === preferredBuilding) {
      option.selected = true;
    }
    fields.buildingId.append(option);
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

function selectedCampus() {
  return campuses.find((campus) => campus.client === fields.client.value) || campuses[0];
}

function syncNames() {
  const campusOption = fields.client.options[fields.client.selectedIndex];
  const buildingOption = fields.buildingId.options[fields.buildingId.selectedIndex];
  fields.campusName.value = campusOption?.dataset.name || campusOption?.textContent || "";
  fields.buildingName.value = buildingOption?.dataset.name || buildingOption?.textContent || "";
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
