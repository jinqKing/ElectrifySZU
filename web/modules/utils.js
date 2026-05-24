// ── Pure utility functions — zero dependencies ─────────────────────

export function numberOrNull(value) {
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

export function escapeHtml(value) {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

export function formatNumber(value, locale = "zh-CN") {
  const number = numberOrNull(value);
  if (number == null) return "--";
  return number.toLocaleString(locale, {
    maximumFractionDigits: 2,
    minimumFractionDigits: Number.isInteger(number) ? 0 : 1,
  });
}

export function formatMoneyNumber(value, locale = "zh-CN") {
  const number = numberOrNull(value);
  if (number == null) return "--";
  return number.toLocaleString(locale, {
    maximumFractionDigits: 2,
    minimumFractionDigits: 2,
  });
}

export function formatMoney(value, moneyUnit, locale = "zh-CN") {
  const text = formatMoneyNumber(value, locale);
  return text === "--" ? text : `${moneyUnit}${text}`;
}

export function yuanPerKwh(data, defaultYuanPerKwh) {
  const rates = (data.recharges || [])
    .map((item) => {
      const yuan = numberOrNull(item.yuan);
      const kwh = numberOrNull(item.kwh);
      return yuan != null && kwh > 0 ? yuan / kwh : null;
    })
    .filter((rate) => rate != null && Number.isFinite(rate) && rate > 0);
  if (rates.length === 0) return defaultYuanPerKwh;
  return rates.reduce((sum, rate) => sum + rate, 0) / rates.length;
}

export function shortDate(value) {
  const text = String(value || "");
  return text.length >= 10 ? text.slice(5, 10) : text || "--";
}

export function parseIsoDate(value) {
  if (value == null || value === "") return null;
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
    if (date.getFullYear() === year && date.getMonth() === month - 1 && date.getDate() === day) return date;
  }
  const parsed = new Date(text);
  if (Number.isNaN(parsed.getTime())) return null;
  return new Date(parsed.getFullYear(), parsed.getMonth(), parsed.getDate());
}

export function estimateAvailableUntilDate(lastRecord, daysLeft) {
  const baseDate = parseIsoDate(lastRecord);
  const days = numberOrNull(daysLeft);
  if (!baseDate || days == null || days < 0) return null;
  const estimatedDate = new Date(baseDate);
  estimatedDate.setDate(estimatedDate.getDate() + Math.ceil(days));
  return estimatedDate;
}

export function formatDisplayDate(date, locale = "zh-CN") {
  return new Intl.DateTimeFormat(locale, {
    year: "numeric", month: "2-digit", day: "2-digit",
  }).format(date);
}

export function roomFloor(roomName) {
  const match = String(roomName || "").match(/\d+/);
  if (!match) return null;
  const digits = match[0];
  if (digits.length < 3) return null;
  return Number(digits.slice(0, -2));
}

export function floorRange(name) {
  const match = name.match(/(\d+)\s*-\s*(\d+)(?:层|楼)?/);
  if (!match) return { minFloor: null, maxFloor: null };
  return { minFloor: Number(match[1]), maxFloor: Number(match[2]) };
}

export function niceAxisStep(value) {
  const number = Math.max(Number(value) || 0, 0);
  if (number <= 0) return 1;
  const magnitude = 10 ** Math.floor(Math.log10(number));
  const normalized = number / magnitude;
  const steps = [1, 1.2, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10];
  const matched = steps.find((step) => normalized <= step) ?? 10;
  return matched * magnitude;
}

export function chartAxis(maxValue, intervals = 5, headroom = 1) {
  const safeMax = Math.max(0, numberOrNull(maxValue) ?? 0);
  const target = safeMax > 0 ? safeMax * headroom : 1;
  const step = niceAxisStep(target / intervals);
  const max = step * intervals;
  const ticks = Array.from({ length: intervals + 1 }, (_, index) => step * index);
  return { intervals, min: 0, max, step, ticks };
}

export function chartAxisRange(minValue, maxValue, intervals = 5) {
  const safeMin = Math.max(0, numberOrNull(minValue) ?? 0);
  const safeMax = Math.max(safeMin, numberOrNull(maxValue) ?? safeMin);
  if (safeMax === safeMin) {
    let step = niceAxisStep(Math.max(Math.abs(safeMax), 1) / 10);
    let min = 0;
    let max = 0;
    do {
      min = Math.max(0, Math.floor((safeMin - step * 2) / step) * step);
      max = min + step * intervals;
      if (max <= safeMax) step = niceAxisStep(step * 1.01);
    } while (max <= safeMax);
    const ticks = Array.from({ length: intervals + 1 }, (_, index) => min + step * index);
    return { intervals, min, max, step, ticks };
  }
  let step = niceAxisStep((safeMax - safeMin) / intervals);
  let min = Math.floor(safeMin / step) * step;
  let max = min + step * intervals;
  while (max < safeMax) {
    step = niceAxisStep(step * 1.01);
    min = Math.floor(safeMin / step) * step;
    max = min + step * intervals;
  }
  if (min < 0) {
    min = 0;
    max = step * intervals;
    while (max < safeMax) { step = niceAxisStep(step * 1.01); max = step * intervals; }
  }
  const ticks = Array.from({ length: intervals + 1 }, (_, index) => min + step * index);
  return { intervals, min, max, step, ticks };
}

export function formatAxisTick(value, step, locale = "zh-CN") {
  const absStep = Math.abs(step);
  let maximumFractionDigits = 0;
  if (absStep < 1) maximumFractionDigits = absStep < 0.1 ? 2 : 1;
  else if (!Number.isInteger(absStep)) maximumFractionDigits = 1;
  return Number(value).toLocaleString(locale, { maximumFractionDigits });
}

export function baseBuildingName(name) {
  const base = name
    .replace(/\d+\s*-\s*\d+\s*楼/g, "")
    .replace(/\d+\s*-\s*\d+\s*层/g, "")
    .replace(/\d+\s*-\s*\d+$/g, "")
    .trim();
  if (base.startsWith("乔") && !base.endsWith("阁")) return `${base}阁`;
  return base;
}

export function roundUsageThreshold(value) {
  return Math.round(Math.max(0, Number(value) || 0) * 10) / 10;
}

export function formatThresholdInput(value) {
  return roundUsageThreshold(value).toFixed(1);
}

export function normalizeUsageLevels(medium, high) {
  const normalizedMedium = Math.max(0, numberOrNull(medium) ?? 0);
  const normalizedHigh = Math.max(normalizedMedium, numberOrNull(high) ?? normalizedMedium);
  return { medium: roundUsageThreshold(normalizedMedium), high: roundUsageThreshold(normalizedHigh) };
}

export function debounce(fn, delay) {
  let timer;
  return function (...args) {
    clearTimeout(timer);
    timer = setTimeout(() => fn.apply(this, args), delay);
  };
}
