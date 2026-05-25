// ── Application configuration ──────────────────────────────────────
// Centralised defaults. Override via __SERVER_CONFIG__ at deploy time.

export const BUILDING_DEFAULTS = {
  client: "192.168.84.87",
  buildingId: "7126",
  buildingName: "风槐斋",
  campusName: "粤海",
};

// Allow server-side injection via template substitution (deploy-time).
if (typeof window.__SERVER_CONFIG__ !== "undefined") {
  const overrides = window.__SERVER_CONFIG__.buildingDefaults;
  if (overrides) {
    Object.assign(BUILDING_DEFAULTS, overrides);
  }
}
