// ── Chart — trend rendering ────────────────────────────────────────
import { t, bilingualCampusName, bilingualBuildingName } from './i18n.js';
import { setState, currentStatusData, metricMode, customUsageLevels } from './state.js';
import {
  numberOrNull, formatNumber, formatMoneyNumber, formatMoney, escapeHtml,
  shortDate, chartAxis, chartAxisRange, formatAxisTick,
  roundUsageThreshold, normalizeUsageLevels,
  yuanPerKwh, estimateAvailableUntilDate, formatDisplayDate,
  loadUsageLevelSettings, saveUsageLevelSettings, readUsageLevelInputs,
} from './utils.js';

const DEFAULT_YUAN_PER_KWH = 0.61;
const MONEY_UNIT = "￥";
const MAX_CHART_POINTS = 60;

export { MAX_CHART_POINTS };

export function renderStatus(data, view) {
  revealResultsContainer();
  setState("currentStatusData", data);
  const remaining = numberOrNull(data.remaining);
  renderMetricCards(data, view);
  view.roomLabel.textContent = `${bilingualCampusName(data.campus_name) || "--"} ${bilingualBuildingName(data.building_name) || "--"} ${data.room_name || "--"}`;
  view.lastRecord.textContent = data.last_record || "--";
  view.records.textContent = formatRecordCount(data.records ?? 0);

  if (data.period) {
    view.period.textContent = t("format.dateRange", { begin: data.period.begin, end: data.period.end });
  } else {
    view.period.textContent = "--";
  }

  const status = data.status || "unknown";
  view.statusBadge.className = `badge ${status}`;
  view.statusBadge.textContent = statusText(status);
  setHeroStatusRaw(statusText(status), status);
  updateBalanceCardStatus(status);

  const threshold = Number(data.threshold_kwh || 20);
  const meterMax = Math.max(threshold * 3, 60);
  const percent = remaining == null ? 0 : Math.max(0, Math.min(100, (remaining / meterMax) * 100));
  view.meterFill.style.width = `${percent}%`;
  view.meterFill.style.background = statusColor(status);

  renderRecharges(data.recharges || [], view);
  renderTrend(data.trend || [], view);
}

function revealResultsContainer() {
  const rc = document.querySelector(".results-container");
  if (rc) rc.classList.add("visible");
}

// ── Metric cards ──────────────────────────────────────────────────

function renderMetricCards(data, view) {
  const rate = yuanPerKwh(data, DEFAULT_YUAN_PER_KWH);
  const dailyAvg = numberOrNull(data.daily_avg_kwh);
  const daysLeft = numberOrNull(data.est_days_left);
  const totalUsed = numberOrNull(data.total_used_kwh);

  setPowerMetric("remaining", numberOrNull(data.remaining), rate, view, {
    kwhUnit: "kWh", yuanUnit: MONEY_UNIT,
  });
  setPowerMetric("dailyAvg", dailyAvg, rate, view, {
    kwhUnit: "kWh / day", yuanUnit: `${MONEY_UNIT} / day`,
  });
  setDaysMetric(daysLeft, data.last_record, view);
  setPowerMetric("totalUsed", totalUsed, rate, view, {
    kwhUnit: "kWh", yuanUnit: MONEY_UNIT,
  });
}

function setPowerMetric(key, kwhValue, rate, view, units) {
  const isYuanMode = metricMode[key] === "yuan";
  const yuanValue = kwhValue == null ? null : kwhValue * rate;
  const primaryValue = isYuanMode ? yuanValue : kwhValue;
  const secondaryValue = isYuanMode ? kwhValue : yuanValue;
  const primaryUnit = isYuanMode ? units.yuanUnit : units.kwhUnit;
  const secondaryUnit = isYuanMode ? units.kwhUnit : units.yuanUnit;

  view[key].textContent = isYuanMode ? formatMoneyNumber(primaryValue) : formatNumber(primaryValue);
  view[`${key}Unit`].textContent = primaryUnit;
  view[`${key}Alt`].textContent = secondaryValue == null
    ? "--"
    : isYuanMode
      ? `${formatNumber(secondaryValue)} ${secondaryUnit}`
      : formatMoney(secondaryValue, MONEY_UNIT);
}

function setDaysMetric(daysLeft, lastRecord, view) {
  const isDateMode = metricMode.daysLeft === "date";
  // 预计可用天数最小为 0，避免余额为 0 或已欠费时显示负数
  const safeDaysLeft = daysLeft == null ? null : Math.max(0, daysLeft);
  const estimatedDate = estimateAvailableUntilDate(lastRecord, safeDaysLeft);
  const dateText = estimatedDate ? formatDisplayDate(estimatedDate) : "--";
  const daysText = safeDaysLeft == null ? "--" : `${formatNumber(safeDaysLeft)} ${t("unit.days")}`;

  const labelEl = document.querySelector('[data-metric-key="daysLeft"] .metric-label');
  if (labelEl) labelEl.textContent = isDateMode ? t("metrics.untilDate") : t("metrics.daysLeft");
  view.daysLeft.textContent = isDateMode ? dateText : formatNumber(safeDaysLeft);
  view.daysLeftUnit.textContent = isDateMode ? "" : t("unit.days");
  view.daysLeftUnit.hidden = isDateMode;
  view.daysLeftDate.textContent = isDateMode ? daysText : formatEstimatedDateText(lastRecord, safeDaysLeft);
}

export function toggleMetricMode(key, view) {
  if (!key || !metricMode[key]) return;
  const card = document.querySelector(`[data-metric-key="${key}"]`);
  if (card) {
    card.classList.remove("is-switching");
    void card.offsetWidth;
    card.classList.add("is-switching");
    window.setTimeout(() => card.classList.remove("is-switching"), 360);
  }
  metricMode[key] = metricMode[key] === "yuan" || metricMode[key] === "date"
    ? (key === "daysLeft" ? "days" : "kwh")
    : (key === "daysLeft" ? "date" : "yuan");
  if (currentStatusData) renderMetricCards(currentStatusData, view);
}

// ── Recharge list ─────────────────────────────────────────────────

function renderRecharges(recharges, view) {
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
      <strong>${formatNumber(item.yuan)} ${t("unit.yuan")}</strong>`;
    view.rechargeList.append(row);
  }
}

// ── Trend chart ───────────────────────────────────────────────────

export function renderTrend(trend, view) {
  const validPoints = trend.filter((item) => numberOrNull(item.remaining) != null);
  const truncated = validPoints.length > MAX_CHART_POINTS;
  const points = validPoints.slice(-(truncated ? MAX_CHART_POINTS : validPoints.length));
  view.trendChart.innerHTML = "";
  view.trendChart.classList.toggle("empty", points.length < 2);

  if (points.length < 2) {
    view.trendChart.textContent = t("empty.noTrend");
    view.chartRange.textContent = t("empty.noData");
    return;
  }

  const width = 920;
  const height = 320;
  const padding = { top: 36, right: 72, bottom: 52, left: 70 };
  const plotWidth = width - padding.left - padding.right;
  const plotHeight = height - padding.top - padding.bottom;
  const remainingValues = points.map((item) => Number(item.remaining));
  const usedValues = points.map((item) => Math.max(0, Number(item.daily_used_kwh || 0)));
  const maxRemaining = Math.max(...remainingValues, 1);
  const minRemaining = Math.min(...remainingValues);
  const maxUsed = Math.max(...usedValues, 0);
  const balanceAxis = chartAxisRange(minRemaining, maxRemaining, 5);
  const usageAxis = chartAxis(maxUsed, 5, 1.12);
  const usageLevels = resolveUsageLevels(usedValues);
  syncUsageLevelInputs(usedValues);
  const x = (index) => padding.left + (index / (points.length - 1)) * plotWidth;
  const y = (value) => {
    const range = Math.max(balanceAxis.max - balanceAxis.min, 1);
    const ratio = Math.max(0, Math.min(1, (value - balanceAxis.min) / range));
    return height - padding.bottom - ratio * plotHeight;
  };
  const usageY = (value) => {
    const ratio = Math.max(0, Math.min(1, value / usageAxis.max));
    return height - padding.bottom - ratio * plotHeight;
  };
  const barWidth = Math.max(8, Math.min(24, plotWidth / points.length / 2));
  const line = points.map((item, index) => `${x(index)},${y(Number(item.remaining))}`).join(" ");
  const area = `${padding.left},${height - padding.bottom} ${line} ${width - padding.right},${height - padding.bottom}`;
  const selectedIndex = points.length - 1;

  const usageClass = (value) => {
    if (value >= usageLevels.high) return "high";
    if (value >= usageLevels.medium) return "medium";
    return "low";
  };

  const bars = points.map((item, index) => {
    const used = Math.max(0, Number(item.daily_used_kwh || 0));
    const barHeight = used > 0 ? Math.max(4, height - padding.bottom - usageY(used)) : 0;
    const bx = x(index) - barWidth / 2;
    const by = height - padding.bottom - barHeight;
    return `<rect class="chart-bar ${usageClass(used)}" x="${bx}" y="${by}" width="${barWidth}" height="${barHeight}" rx="4"></rect>`;
  }).join("");

  const dots = points.map((item, index) =>
    `<circle class="chart-dot" cx="${x(index)}" cy="${y(Number(item.remaining))}" r="4"></circle>`
  ).join("");

  const hotZoneHalfW = Math.max(14, barWidth / 2 + 9);
  const interactions = points.map((item, index) => {
    const cx = x(index);
    const activeAttr = index === selectedIndex ? " active" : "";
    return `
      <g class="chart-zone${activeAttr}" data-chart-index="${index}" tabindex="0" role="button" aria-label="${escapeHtml(chartPointLabel(item))}">
        <rect class="chart-hotzone" x="${cx - hotZoneHalfW}" y="${padding.top}" width="${hotZoneHalfW * 2}" height="${plotHeight}" fill="transparent" />
        <circle class="chart-indicator" cx="${cx}" cy="${height - padding.bottom + 5}" r="4" />
      </g>`;
  }).join("");

  const firstDate = shortDate(points[0].date);
  const lastDate = shortDate(points[points.length - 1].date);
  view.chartRange.textContent = t("format.dateRange", { begin: firstDate, end: lastDate });

  const ticks = balanceAxis.ticks.map((balanceValue, index) => {
    const fraction = index / balanceAxis.intervals;
    const tickY = height - padding.bottom - fraction * plotHeight;
    const usageValue = usageAxis.max * fraction;
    const gridClass = index === 0 ? "chart-grid baseline" : "chart-grid";
    return `
      <g class="chart-tick">
        <line class="${gridClass}" x1="${padding.left}" y1="${tickY}" x2="${width - padding.right}" y2="${tickY}"></line>
        <line class="chart-tick-mark" x1="${padding.left - 5}" y1="${tickY}" x2="${padding.left}" y2="${tickY}"></line>
        <line class="chart-tick-mark" x1="${width - padding.right}" y1="${tickY}" x2="${width - padding.right + 5}" y2="${tickY}"></line>
        <text class="chart-axis-label left" x="${padding.left - 10}" y="${tickY + 4}">${formatAxisTick(balanceValue, balanceAxis.step)}</text>
        <text class="chart-axis-label right" x="${width - padding.right + 10}" y="${tickY + 4}">${formatAxisTick(usageValue, usageAxis.step)}</text>
      </g>`;
  }).join("");

  const truncationNotice = truncated
    ? `<div class="chart-truncation"><span>⚠ 仅显示最近 ${MAX_CHART_POINTS} 天趋势，共 ${validPoints.length} 条记录</span></div>`
    : "";

  view.trendChart.innerHTML = `
    <div class="chart-canvas">
      <svg viewBox="0 0 ${width} ${height}" role="img" aria-label="${t("chart.svgLabel")}">
        <line class="chart-axis" x1="${padding.left}" y1="${height - padding.bottom}" x2="${width - padding.right}" y2="${height - padding.bottom}"></line>
        <line class="chart-axis" x1="${padding.left}" y1="${padding.top}" x2="${padding.left}" y2="${height - padding.bottom}"></line>
        <line class="chart-axis" x1="${width - padding.right}" y1="${padding.top}" x2="${width - padding.right}" y2="${height - padding.bottom}"></line>
        ${ticks}
        ${bars}
        <polygon class="chart-area" points="${area}"></polygon>
        <polyline class="chart-line" points="${line}"></polyline>
        ${dots}
        <g class="chart-interaction" aria-label="${t("chart.tooltipHint")}">
          ${interactions}
        </g>
        <text class="chart-label" x="${padding.left}" y="${height - 16}">${escapeHtml(firstDate)}</text>
        <text class="chart-label" x="${width - padding.right}" y="${height - 16}" text-anchor="end">${escapeHtml(lastDate)}</text>
        <text class="chart-label chart-title-label" x="${padding.left}" y="20">${t("chart.balanceLabel")}</text>
        <text class="chart-label chart-title-label" x="${width - padding.right}" y="20" text-anchor="end">${t("chart.dailyUseLabel")}</text>
      </svg>
      <div class="chart-tooltip" role="status" aria-live="polite"></div>
    </div>
    ${truncationNotice}`;

  const svgEl = view.trendChart.querySelector("svg");
  attachTrendInteractions(points, svgEl, view, { width, height, padding, x, y, barWidth, selectedIndex });
}

function computeSvgScale(svgEl, viewBoxSize) {
  const rect = svgEl.getBoundingClientRect();
  return { sx: rect.width / viewBoxSize.width, sy: rect.height / viewBoxSize.height };
}

function attachTrendInteractions(points, svgEl, view, geometry) {
  const zones = Array.from(svgEl.querySelectorAll(".chart-zone"));
  const tooltip = view.trendChart.querySelector(".chart-tooltip");
  if (!zones.length || !tooltip) return;

  const vbSize = { width: geometry.width, height: geometry.height };

  const showPoint = (index) => {
    const item = points[index];
    if (!item) return;
    const scale = computeSvgScale(svgEl, vbSize);
    const pixelX = geometry.x(index) * scale.sx;
    const pixelY = geometry.y(Number(item.remaining)) * scale.sy;
    tooltip.innerHTML = chartTooltipMarkup(item);
    tooltip.style.left = `${pixelX}px`;
    tooltip.style.top = `${pixelY}px`;
    // Flip tooltip below the dot when too close to chart top edge,
    // so it doesn't get clipped by overflow-y: hidden on .trend-chart
    if (pixelY < 120) {
      tooltip.classList.add("direction-down");
    } else {
      tooltip.classList.remove("direction-down");
    }
    tooltip.classList.add("visible");
    zones.forEach((zone, zi) => zone.classList.toggle("active", zi === index));
  };

  const hidePoint = () => {
    tooltip.classList.remove("visible");
    zones.forEach((zone) => zone.classList.remove("active"));
  };

  showPoint(geometry.selectedIndex);

  zones.forEach((zone, index) => {
    zone.addEventListener("pointerenter", () => showPoint(index));
    zone.addEventListener("focus", () => showPoint(index));
    zone.addEventListener("click", () => showPoint(index));
    zone.addEventListener("keydown", (event) => {
      if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
      event.preventDefault();
      const direction = event.key === "ArrowLeft" ? -1 : 1;
      const nextIndex = Math.max(0, Math.min(points.length - 1, index + direction));
      zones[nextIndex].focus();
    });
  });

  const canvas = view.trendChart.querySelector(".chart-canvas");
  canvas.addEventListener("mouseleave", () => {
    setTimeout(() => { if (!tooltip.matches(":hover")) hidePoint(); }, 50);
  });
}

function chartTooltipMarkup(item) {
  return `
    <strong>${escapeHtml(item.date || "--")}</strong>
    <span>${escapeHtml(t("chart.tooltipBalance"))}: ${formatNumber(item.remaining)} kWh</span>
    <span>${escapeHtml(t("chart.tooltipUsage"))}: ${formatNumber(item.daily_used_kwh || 0)} kWh</span>`;
}

function chartPointLabel(item) {
  return `${item.date || "--"}, ${t("chart.tooltipBalance")} ${formatNumber(item.remaining)} kWh, ${t("chart.tooltipUsage")} ${formatNumber(item.daily_used_kwh || 0)} kWh`;
}

// ── Usage level controls ──────────────────────────────────────────

function resolveUsageLevels(usedValues) {
  const maxUsed = Math.max(...usedValues, 1);
  const automatic = {
    medium: roundUsageThreshold(maxUsed * 0.42),
    high: roundUsageThreshold(maxUsed * 0.72),
  };
  const medium = customUsageLevels.medium ?? automatic.medium;
  const high = customUsageLevels.high ?? automatic.high;
  return normalizeUsageLevels(medium, high);
}

function syncUsageLevelInputs(usedValues) {
  const levels = resolveUsageLevels(usedValues.length ? usedValues : [1]);
  const mediumInput = document.querySelector("#mediumUseThreshold");
  const highInput = document.querySelector("#highUseThreshold");
  if (mediumInput) {
    mediumInput.value = roundUsageThreshold(levels.medium).toFixed(1);
    mediumInput.classList.toggle("auto", customUsageLevels.medium == null);
  }
  if (highInput) {
    highInput.value = roundUsageThreshold(levels.high).toFixed(1);
    highInput.classList.toggle("auto", customUsageLevels.high == null);
  }
}

// ── Helpers ────────────────────────────────────────────────────────

function formatRecordCount(count) {
  return t("format.records", { count });
}

function paymentMethodText(method) {
  if (!method) return t("empty.unknownMethod");
  return { 微信支付: t("payment.wechat"), 支付宝: t("payment.alipay") }[method] || method;
}

function statusText(status) {
  const map = { ok: "powerStatus.ok", low: "powerStatus.low", critical: "powerStatus.critical", unknown: "powerStatus.unknown" };
  return t(map[status] || "powerStatus.unknown");
}

function statusColor(status) {
  return { ok: "#0f9f6e", low: "#d98616", critical: "#d73939", unknown: "#657386" }[status] || "#657386";
}

function updateBalanceCardStatus(status) {
  const balanceCard = document.querySelector(".metric.balance");
  if (!balanceCard) return;
  balanceCard.classList.remove("status-ok", "status-low", "status-critical");
  if (["ok", "low", "critical"].includes(status)) balanceCard.classList.add(`status-${status}`);
}

function formatEstimatedDateText(lastRecord, daysLeft) {
  const estimatedDate = estimateAvailableUntilDate(lastRecord, daysLeft);
  if (!estimatedDate) return "暂无预计日期";
  return `预计到 ${formatDisplayDate(estimatedDate)}`;
}

function setHeroStatusRaw(text, status) {
  const heroStatus = document.querySelector("#heroStatus");
  if (!heroStatus) return;
  heroStatus.querySelector("span:last-child").textContent = text;
  heroStatus.querySelector(".pulse").style.background = statusColor(status);
}
