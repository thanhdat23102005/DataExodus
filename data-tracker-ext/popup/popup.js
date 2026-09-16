// popup.js - DataExodus Popup Logic v3.3
import { md5 } from '../md5.js';

const FLAGS = {
  US: "🇺🇸", FR: "🇫🇷", CN: "🇨🇳", MT: "🇲🇹", AU: "🇦🇺",
  GB: "🇬🇧", DE: "🇩🇪", SG: "🇸🇬", JP: "🇯🇵", IE: "🇮🇪",
};
const COUNTRY_NAMES = {
  US: "United States", FR: "France", CN: "China", MT: "Malta", AU: "Australia",
  GB: "United Kingdom", DE: "Germany", SG: "Singapore", JP: "Japan", IE: "Ireland",
};

const DEFAULT_GATEWAY_URL = "http://192.168.0.83:5000/api/telemetry";

// Anything shorter matches far too much: a 2-4 character string turns up
// inside ordinary ids and timestamps in almost every URL, which is what
// made the earlier "04XXXXXXXX" placeholder flood the results with noise.
const MIN_IDENTIFIER_LENGTH = 6;

function getRiskColor(score) {
  if (score <= 20) return "#4caf50";
  if (score <= 50) return "#ff9800";
  if (score <= 75) return "#f44336";
  return "#b71c1c";
}

function getRiskText(score) {
  if (score <= 20) return "Low Risk";
  if (score <= 50) return "Moderate Risk";
  if (score <= 75) return "High Risk";
  return "Critical Risk";
}

// -----------------------------------------------------------------
// IDENTIFIER NORMALISATION
//
// A tracker does not hash what you typed, it hashes what its own
// pipeline normalised first. pipeline/pii.py already does this on the
// Python side; v3.2 hashed a single string, so an identifier entered as
// "0412 345 678" produced hashes of a value containing spaces and could
// never match anything. Every plausible form gets hashed instead.
// -----------------------------------------------------------------
function identifierVariants(raw) {
  const value = String(raw || "").trim().toLowerCase();
  if (!value) return [];
  const variants = new Set([value]);

  if (value.includes("@")) {
    const atIndex = value.lastIndexOf("@");
    const local = value.slice(0, atIndex);
    const domain = value.slice(atIndex + 1);
    const isGoogle = domain === "gmail.com" || domain === "googlemail.com";
    const bare = local.includes("+") ? local.slice(0, local.indexOf("+")) : local;

    if (bare !== local) variants.add(`${bare}@${domain}`);
    if (isGoogle) {
      variants.add(`${local.replace(/\./g, "")}@${domain}`);
      variants.add(`${bare.replace(/\./g, "")}@${domain}`);
    }
  } else {
    const digits = value.replace(/\D/g, "");
    if (digits.length >= MIN_IDENTIFIER_LENGTH) {
      variants.add(digits);
      if (digits.startsWith("0")) {
        variants.add(`61${digits.slice(1)}`);
        variants.add(`+61${digits.slice(1)}`);
      } else if (digits.startsWith("61")) {
        variants.add(`0${digits.slice(2)}`);
        variants.add(`+${digits}`);
      }
    }
  }

  return [...variants].filter((v) => v.length >= MIN_IDENTIFIER_LENGTH);
}

async function digestHex(algorithm, text) {
  const buffer = await crypto.subtle.digest(algorithm, new TextEncoder().encode(text));
  return [...new Uint8Array(buffer)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

// Hashes are stored lowercase and the haystack is lowercased before
// comparison, so uppercase hex on the wire still matches.
async function buildIdentityIndex(rawInput) {
  const plaintexts = identifierVariants(rawInput);
  if (plaintexts.length === 0) return null;

  const hashes = {};
  for (const variant of plaintexts) {
    hashes[md5(variant)] = "MD5";
    hashes[await digestHex("SHA-1", variant)] = "SHA-1";
    hashes[await digestHex("SHA-256", variant)] = "SHA-256";
    hashes[await digestHex("SHA-512", variant)] = "SHA-512";
  }

  return { plaintexts, hashes, variantCount: plaintexts.length, createdAt: Date.now() };
}

// -----------------------------------------------------------------
// VIEWS
// -----------------------------------------------------------------
function show(viewId) {
  for (const id of ["onboarding-view", "main-view", "settings-view"]) {
    document.getElementById(id).classList.toggle("hidden", id !== viewId);
  }
}

async function loadGatewayConfig() {
  const { gatewayConfig } = await chrome.storage.local.get("gatewayConfig");
  return {
    url: (gatewayConfig && gatewayConfig.url) || DEFAULT_GATEWAY_URL,
    enabled: gatewayConfig ? gatewayConfig.enabled !== false : true,
  };
}

document.addEventListener("DOMContentLoaded", async () => {
  const { piiIndex } = await chrome.storage.local.get("piiIndex");

  if (!piiIndex || !piiIndex.plaintexts || piiIndex.plaintexts.length === 0) {
    show("onboarding-view");
  } else {
    show("main-view");
    renderDashboard();
  }

  document.getElementById("save-pii-btn").addEventListener("click", async () => {
    const input = document.getElementById("pii-input").value;
    const errorEl = document.getElementById("pii-error");
    const index = await buildIdentityIndex(input);

    if (!index) {
      errorEl.textContent =
        `Enter an email address, or a phone number of at least ${MIN_IDENTIFIER_LENGTH} digits. ` +
        `Shorter values match unrelated traffic and make every result meaningless.`;
      errorEl.classList.remove("hidden");
      return;
    }

    errorEl.classList.add("hidden");
    await chrome.storage.local.set({ piiIndex: index });
    show("main-view");
    renderDashboard();
  });

  document.getElementById("open-settings-btn").addEventListener("click", async () => {
    const cfg = await loadGatewayConfig();
    document.getElementById("gateway-url").value = cfg.url;
    document.getElementById("gateway-enabled").checked = cfg.enabled;
    show("settings-view");
  });

  document.getElementById("save-settings-btn").addEventListener("click", async () => {
    const url = document.getElementById("gateway-url").value.trim();
    const enabled = document.getElementById("gateway-enabled").checked;
    await chrome.storage.local.set({
      gatewayConfig: { url: url || DEFAULT_GATEWAY_URL, enabled },
    });
    show("main-view");
    renderDashboard();
  });

  document.getElementById("back-btn").addEventListener("click", () => {
    show("main-view");
    renderDashboard();
  });

  document.getElementById("reset-pii-btn").addEventListener("click", async () => {
    await chrome.storage.local.remove("piiIndex");
    document.getElementById("pii-input").value = "";
    show("onboarding-view");
  });
});

// -----------------------------------------------------------------
// DASHBOARD RENDERING
// -----------------------------------------------------------------
async function renderGatewayStatus() {
  const el = document.getElementById("gateway-status");
  const cfg = await loadGatewayConfig();

  if (!cfg.enabled) {
    el.textContent = "Gateway: off";
    el.className = "gateway-status off";
    return;
  }

  const { gatewayStatus } = await chrome.storage.local.get("gatewayStatus");
  if (!gatewayStatus) {
    el.textContent = "Gateway: waiting for first send";
    el.className = "gateway-status off";
  } else if (gatewayStatus.ok) {
    el.textContent = "Gateway: connected";
    el.className = "gateway-status ok";
  } else {
    el.textContent = `Gateway: unreachable (${gatewayStatus.detail || "error"})`;
    el.className = "gateway-status bad";
  }
}

async function renderDashboard() {
  renderGatewayStatus();

  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab || !tab.id) {
    document.getElementById("current-domain").textContent = "Cannot access tab.";
    return;
  }

  const storageKey = `tabData_${tab.id}`;
  const data = await chrome.storage.local.get(storageKey);
  const tabData = data[storageKey];

  if (!tabData) {
    document.getElementById("current-domain").textContent = "No data yet for this tab.";
    document.getElementById("domain-list").innerHTML =
      '<div class="empty-state">Browse a website to start tracking.</div>';
    return;
  }

  document.getElementById("current-domain").textContent = tabData.domain || tabData.url;

  const details = tabData.piiDetails || [];
  const covert = details.filter((d) => d.scope === "covert");
  const intentional = details.filter((d) => d.scope === "intentional");

  const alertEl = document.getElementById("pii-alert");
  if (covert.length > 0) {
    alertEl.classList.remove("hidden");
    const first = covert[0];
    document.getElementById("pii-detail").textContent =
      `${first.type.toUpperCase()} of your identifier sent to ${first.company} (${first.destination})`;
  } else {
    alertEl.classList.add("hidden");
  }

  const noteEl = document.getElementById("pii-note");
  if (intentional.length > 0) {
    noteEl.classList.remove("hidden");
    noteEl.textContent =
      `${intentional.length} first-party match${intentional.length > 1 ? "es" : ""} on this site ` +
      `(sent to the site itself — recorded, not counted as a leak).`;
  } else {
    noteEl.classList.add("hidden");
  }

  const score = tabData.riskScore || 0;
  const fillEl = document.getElementById("risk-fill");
  fillEl.style.width = score + "%";
  fillEl.style.background = getRiskColor(score);
  document.getElementById("risk-score").textContent = score;
  const riskTextEl = document.getElementById("risk-text");
  riskTextEl.textContent = getRiskText(score);
  riskTextEl.style.color = getRiskColor(score);

  let totalReqs = 0;
  let thirdPartyReqs = 0;
  let trackerReqs = 0;
  const countriesSet = new Set();

  const requests = tabData.requests || {};
  const entries = Object.entries(requests).sort((a, b) => b[1].count - a[1].count);

  entries.forEach(([, info]) => {
    totalReqs += info.count;
    if (info.isThirdParty) thirdPartyReqs += info.count;
    if (info.tracker) {
      trackerReqs += info.count;
      countriesSet.add(info.tracker.country);
    }
  });

  document.getElementById("total-reqs").textContent = totalReqs;
  document.getElementById("third-party-reqs").textContent = thirdPartyReqs;
  document.getElementById("tracker-reqs").textContent = trackerReqs;
  document.getElementById("country-count").textContent = countriesSet.size;

  const countriesSection = document.getElementById("countries-section");
  if (countriesSet.size > 0) {
    countriesSection.classList.remove("hidden");
    const countriesList = document.getElementById("countries-list");
    countriesList.innerHTML = "";
    for (const code of countriesSet) {
      const chip = document.createElement("div");
      chip.className = "country-chip";
      chip.textContent = `${FLAGS[code] || "🌐"} ${COUNTRY_NAMES[code] || code}`;
      countriesList.appendChild(chip);
    }
  } else {
    countriesSection.classList.add("hidden");
  }

  const domainList = document.getElementById("domain-list");
  domainList.innerHTML = "";

  if (entries.length === 0) {
    domainList.innerHTML = '<div class="empty-state">No requests tracked yet.</div>';
    return;
  }

  entries.forEach(([domain, info]) => {
    const item = document.createElement("div");
    item.className = "domain-item";
    if (info.piiScope === "covert") item.classList.add("pii-row");

    const nameSpan = document.createElement("span");
    nameSpan.className = "domain-name";
    nameSpan.textContent = domain;
    nameSpan.title = domain;
    item.appendChild(nameSpan);

    if (info.tracker) {
      const compSpan = document.createElement("span");
      compSpan.className = "domain-company";
      compSpan.textContent = `${FLAGS[info.tracker.country] || ""} ${info.tracker.company}`;
      item.appendChild(compSpan);
    }

    const badge = document.createElement("span");
    if (info.piiScope === "covert") {
      badge.className = "badge badge-pii";
      badge.textContent = `PII (${info.piiType})`;
    } else if (info.piiScope === "intentional") {
      badge.className = "badge badge-pii-first";
      badge.textContent = `PII 1st-party`;
    } else if (info.tracker) {
      badge.className = "badge badge-tracker";
      badge.textContent = info.tracker.category;
    } else if (info.isThirdParty) {
      badge.className = "badge badge-3p";
      badge.textContent = "3rd-Party";
    } else {
      badge.className = "badge badge-safe";
      badge.textContent = "1st-Party";
    }
    item.appendChild(badge);

    const countBadge = document.createElement("span");
    countBadge.className = "badge badge-count";
    countBadge.textContent = info.count;
    item.appendChild(countBadge);

    domainList.appendChild(item);
  });
}
