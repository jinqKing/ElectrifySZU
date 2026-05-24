// ── i18n — Translation and locale switching ────────────────────────
import { setState, currentLocale } from './state.js';
import { baseBuildingName } from './utils.js';

const DEFAULT_LOCALE = "zh-CN";
const LOCALE_QUERY = { zh: "zh-CN", "zh-CN": "zh-CN", en: "en-US", "en-US": "en-US" };
const translations = window.ElectrifySZUI18n?.translations || {};
translations["zh-CN"] ||= {};
translations["en-US"] ||= {};

// Fallback translations for subscription (in case i18n-data is outdated)
translations["zh-CN"]["subscribe.emailPlaceholder"] ||= "学号或邮箱前缀";
translations["zh-CN"]["subscribe.emailHint"] ||= "自动补全 @email.szu.edu.cn；支持输入其他完整邮箱。";
translations["zh-CN"]["subscribe.invalidEmail"] ||= "请输入有效邮箱，或仅填写默认邮箱前缀。";
translations["zh-CN"]["subscribe.chooseOne"] ||= "请至少选择一种订阅类型。";
translations["zh-CN"]["subscribe.dialogResultTitle"] ||= "订阅已提交";
translations["zh-CN"]["subscribe.triggerOpen"] ||= "🔔 订阅电费预警邮件";
translations["zh-CN"]["subscribe.cancelBack"] ||= "✕ 返回";
translations["zh-CN"]["subscribe.summaryActive"] ||= "已订阅预警";
translations["zh-CN"]["subscribe.summaryPending"] ||= "待验证";
translations["en-US"]["subscribe.triggerOpen"] ||= "🔔 Setup alerts";
translations["en-US"]["subscribe.cancelBack"] ||= "✕ Back";
translations["en-US"]["subscribe.summaryActive"] ||= "alerts subscribed";
translations["en-US"]["subscribe.summaryPending"] ||= "awaiting verification";
translations["en-US"]["subscribe.emailPlaceholder"] ||= "NetID or email prefix";
translations["en-US"]["subscribe.emailHint"] ||= "Auto append @email.szu.edu.cn, support other emails";
translations["en-US"]["subscribe.invalidEmail"] ||= "Enter a valid email address, or only the default mailbox prefix.";
translations["en-US"]["subscribe.chooseOne"] ||= "Choose at least one subscription type.";
translations["en-US"]["subscribe.dialogResultTitle"] ||= "Subscription submitted";

export const campusLabels = {
  粤海: "粤海 / Yuehai",
  丽湖: "丽湖 / Lihu",
};

export const sourceCampusLabels = {
  北校区: "北校区",
  南校区: "南校区",
  丽湖校区: "丽湖校区",
  深大新斋区: "深大新斋区",
};

export const buildingEnglishNames = {
  "乔林阁": "Qiaolin Hall", "乔木阁": "Qiaomu Hall",
  "乔森阁": "Qiaosen Hall", "乔相阁": "Qiaoxiang Hall",
  "乔梧阁": "Qiaowu Hall",
  "山茶斋": "Shancha Zhai", "红榴斋": "Hongliu Zhai",
  "米兰斋": "Milan Zhai", "海桐斋": "Haitong Zhai",
  "桃李斋": "Taoli Zhai", "凌霄斋": "Lingxiao Zhai",
  "银桦斋": "Yinhua Zhai",
  "木犀轩": "Muxi Xuan", "丹枫轩": "Danfeng Xuan",
  "紫檀轩": "Zitan Xuan", "石楠轩": "Shinan Xuan",
  "苏铁轩": "Sutie Xuan",
  "芸香阁": "Yunxiang Hall", "丁香阁": "Dingxiang Hall",
  "文杏阁": "Wenxing Hall", "海棠阁": "Haitang Hall",
  "疏影阁": "Shuying Hall", "杜衡阁": "Duheng Hall",
  "辛夷阁": "Xinyi Hall", "韵竹阁": "Yunzhu Hall",
  "云杉轩": "Yunshan Xuan", "紫藤轩": "Ziteng Xuan",
  "留学生公寓": "International Student Apartment",
  "春笛": "Chundi", "夏筝": "Xiazheng",
  "秋瑟": "Qiuse", "冬筑": "Dongzhu",
  "A栋风信子": "Building A Hyacinth", "B栋山楂树": "Building B Hawthorn",
  "C栋胡杨林": "Building C Poplar",
  "风槐斋": "Fenghuai Zhai", "雨鹃斋": "Yujuan Zhai",
  "蓬莱客舍": "Penglai House",
  "聚翰斋": "Juhan Zhai", "紫薇斋": "Ziwei Zhai",
  "红豆斋": "Hongdou Zhai",
};

export function t(key, values = {}) {
  const dict = translations[currentLocale] || translations[DEFAULT_LOCALE];
  const fallback = Object.prototype.hasOwnProperty.call(translations[DEFAULT_LOCALE], key)
    ? translations[DEFAULT_LOCALE][key] : key;
  const copy = Object.prototype.hasOwnProperty.call(dict, key) ? dict[key] : fallback;
  return copy.replace(/\{(\w+)\}/g, (_, name) => values[name] ?? "");
}

export function bilingualCampusName(name) {
  return campusLabels[name] || name || "";
}

export function bilingualSourceCampusName(name) {
  return sourceCampusLabels[name] || name || "";
}

export function buildingEnglishName(name) {
  if (!name) return "";
  const base = baseBuildingName(name);
  return buildingEnglishNames[base] || "";
}

export function bilingualBuildingName(name) {
  if (!name) return "";
  const english = buildingEnglishName(name);
  return english ? `${name} / ${english}` : name;
}

export function resolveInitialLocale() {
  const requested = new URLSearchParams(location.search).get("lang");
  const queryLocale = LOCALE_QUERY[requested];
  if (queryLocale) return queryLocale;
  try {
    const stored = localStorage.getItem("electrifyszu.locale");
    if (translations[stored]) return stored;
  } catch { /* ignore */ }
  return DEFAULT_LOCALE;
}

/**
 * setLanguage — updates DOM for all i18n attributes.
 * Must be imported and called from app.js after DOM refs are ready.
 */
export function setLanguage(locale, options = {}) {
  if (!translations[locale]) locale = DEFAULT_LOCALE;
  const prevLocale = currentLocale;
  setState("currentLocale", locale);
  document.documentElement.lang = locale;
  document.title = t("meta.title");

  if (options.persist !== false) {
    try { localStorage.setItem("electrifyszu.locale", locale); } catch { /* ignore */ }
  }

  // Update language switcher buttons
  document.querySelectorAll("[data-lang]").forEach((button) => {
    const isSelected = button.dataset.lang === locale;
    button.classList.toggle("active", isSelected);
    button.setAttribute("aria-pressed", String(isSelected));
  });

  // Bulk update data-i18n attributes
  document.querySelectorAll("[data-i18n]").forEach((el) => {
    el.textContent = t(el.dataset.i18n);
  });
  document.querySelectorAll("[data-i18n-placeholder]").forEach((el) => {
    el.setAttribute("placeholder", t(el.dataset.i18nPlaceholder));
  });
  document.querySelectorAll("[data-i18n-aria-label]").forEach((el) => {
    el.setAttribute("aria-label", t(el.dataset.i18nAriaLabel));
  });
  document.querySelectorAll("[data-i18n-alt]").forEach((el) => {
    el.setAttribute("alt", t(el.dataset.i18nAlt));
  });
  document.querySelectorAll(".field-hint[data-i18n]").forEach((el) => {
    el.textContent = t(el.dataset.i18n);
  });

  // Re-render UI elements that embed text
  return { prevLocale }; // caller can use this to trigger re-renders
}
