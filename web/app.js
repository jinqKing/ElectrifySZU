const form = document.querySelector("#queryForm");
const demoButton = document.querySelector("#demoButton");
const message = document.querySelector("#message");
const heroStatus = document.querySelector("#heroStatus");

const fields = {
  roomId: document.querySelector("#roomId"),
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

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  await loadStatus("/api/status?" + new URLSearchParams(new FormData(form)));
});

demoButton.addEventListener("click", async () => {
  await loadStatus("/api/demo-status");
});

async function loadStatus(url) {
  setBusy(true);
  setMessage("正在查询电费系统...");
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
  view.roomLabel.textContent = `${data.room_name || "--"} (${data.room_id || "--"})`;
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

function setBusy(isBusy) {
  form.querySelectorAll("button, input").forEach((element) => {
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
