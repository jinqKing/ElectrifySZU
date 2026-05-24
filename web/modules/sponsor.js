// ── Sponsor — support modal ───────────────────────────────────────
const $ = (s) => document.querySelector(s);

let lastFocused = null;

export function setupSponsor() {
  const btn = $("#sponsorButton");
  const close = $("#supportClose");
  const backdrop = $("[data-support-close]");
  const dialog = $("#supportDialog");

  btn?.addEventListener("click", open);
  close?.addEventListener("click", closeFn);
  backdrop?.addEventListener("click", closeFn);
  dialog?.addEventListener("click", (e) => e.stopPropagation());
}

function open() {
  const modal = $("#supportModal");
  const dialog = $("#supportDialog");
  const btn = $("#sponsorButton");
  if (!modal || !dialog) return;
  lastFocused = document.activeElement instanceof HTMLElement ? document.activeElement : btn;
  modal.hidden = false;
  btn?.setAttribute("aria-expanded", "true");
  document.body.classList.add("modal-open");
  dialog.focus();
}

function closeFn() {
  const modal = $("#supportModal");
  const btn = $("#sponsorButton");
  if (!modal) return;
  modal.hidden = true;
  btn?.setAttribute("aria-expanded", "false");
  document.body.classList.remove("modal-open");
  if (lastFocused && document.contains(lastFocused)) lastFocused.focus();
  else btn?.focus();
  lastFocused = null;
}

// Keyboard: Escape to close, Tab trapping inside dialog
export function setupSponsorKeyboard() {
  window.addEventListener("keydown", (event) => {
    const modal = $("#supportModal");
    const dialog = $("#supportDialog");
    if (!modal || modal.hidden) return;
    if (event.key === "Escape") { closeFn(); return; }
    if (event.key === "Tab") trapFocus(event, dialog);
  });
}

function trapFocus(event, dialog) {
  if (!dialog) return;
  const selector = "a[href],button:not([disabled]),input:not([disabled]),select:not([disabled]),textarea:not([disabled]),[tabindex]:not([tabindex='-1'])";
  const elms = Array.from(dialog.querySelectorAll(selector)).filter((el) => el.offsetParent !== null);
  if (!elms.length) { event.preventDefault(); dialog.focus(); return; }
  const first = elms[0], last = elms[elms.length - 1];
  const active = document.activeElement;
  if (active === dialog) { event.preventDefault(); (event.shiftKey ? last : first).focus(); return; }
  if (!dialog.contains(active)) { event.preventDefault(); first.focus(); return; }
  if (event.shiftKey && active === first) { event.preventDefault(); last.focus(); return; }
  if (!event.shiftKey && active === last) { event.preventDefault(); first.focus(); }
}
