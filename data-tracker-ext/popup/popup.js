// popup.js - DataExodus Popup Logic v3.0
// Reads tracked data from chrome.storage and renders the visualization.
// Note: background flushes to storage every ~400ms (debounced), so this
// view can lag live browsing by up to that amount — expected, not a bug.

const FLAGS = {
  US: "🇺🇸", FR: "🇫🇷", CN: "🇨🇳", MT: "🇲🇹", AU: "🇦🇺",
  GB: "🇬🇧", DE: "🇩🇪", SG: "🇸🇬", JP: "🇯🇵", IE: "🇮🇪",
};
const COUNTRY_NAMES = {
  US: "United States", FR: "France", CN: "China", MT: "Malta", AU: "Australia",
  GB: "United Kingdom", DE: "Germany", SG: "Singapore", JP: "Japan", IE: "Ireland",
};

function getRiskColor(score) {
  if (score <= 20) return "#4caf50";   // Green - Safe
  if (score <= 50) return "#ff9800";   // Orange - Moderate
  if (score <= 75) return "#f44336";   // Red - High
  return "#b71c1c";                     // Dark Red - Critical
}

function getRiskText(score) {
  if (score <= 20) return "Low Risk";
  if (score <= 50) return "Moderate Risk";
  if (score <= 75) return "High Risk";
  return "Critical Risk";
}

document.addEventListener("DOMContentLoaded", async () => {
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

  // --- Header ---
  document.getElementById("current-domain").textContent = tabData.domain || tabData.url;

  // --- PII Alert ---
  if (tabData.piiLeaked && tabData.piiDetails.length > 0) {
    const alertEl = document.getElementById("pii-alert");
    alertEl.classList.remove("hidden");
    const detail = tabData.piiDetails[0];
    document.getElementById("pii-detail").textContent =
      `${detail.type.toUpperCase()} hash of email sent to ${detail.company} (${detail.destination})`;
  }

  // --- Risk Score Gauge ---
  const score = tabData.riskScore || 0;
  const fillEl = document.getElementById("risk-fill");
  fillEl.style.width = score + "%";
  fillEl.style.background = getRiskColor(score);
  document.getElementById("risk-score").textContent = score;
  const riskTextEl = document.getElementById("risk-text");
  riskTextEl.textContent = getRiskText(score);
  riskTextEl.style.color = getRiskColor(score);

  // --- Stats ---
  let totalReqs = 0;
  let thirdPartyReqs = 0;
  let trackerReqs = 0;
  const countriesSet = new Set();
  const companiesMap = new Map(); // company -> count

  const requests = tabData.requests || {};
  const entries = Object.entries(requests).sort((a, b) => b[1].count - a[1].count);

  entries.forEach(([domain, info]) => {
    totalReqs += info.count;
    if (info.isThirdParty) thirdPartyReqs += info.count;
    if (info.tracker) {
      trackerReqs += info.count;
      countriesSet.add(info.tracker.country);
      const prev = companiesMap.get(info.tracker.company) || 0;
      companiesMap.set(info.tracker.company, prev + info.count);
    }
  });

  document.getElementById("total-reqs").textContent = totalReqs;
  document.getElementById("third-party-reqs").textContent = thirdPartyReqs;
  document.getElementById("tracker-reqs").textContent = trackerReqs;
  document.getElementById("country-count").textContent = countriesSet.size;

  // --- Countries ---
  if (countriesSet.size > 0) {
    document.getElementById("countries-section").classList.remove("hidden");
    const countriesList = document.getElementById("countries-list");
    countriesList.innerHTML = "";
    for (const code of countriesSet) {
      const chip = document.createElement("div");
      chip.className = "country-chip";
      chip.textContent = `${FLAGS[code] || "🌐"} ${COUNTRY_NAMES[code] || code}`;
      countriesList.appendChild(chip);
    }
  }

  // --- Domain List ---
  const domainList = document.getElementById("domain-list");
  domainList.innerHTML = "";

  if (entries.length === 0) {
    domainList.innerHTML = '<div class="empty-state">No requests tracked yet.</div>';
    return;
  }

  entries.forEach(([domain, info]) => {
    const item = document.createElement("div");
    item.className = "domain-item";
    if (info.piiLeak) item.classList.add("pii-row");

    // Domain name
    const nameSpan = document.createElement("span");
    nameSpan.className = "domain-name";
    nameSpan.textContent = domain;
    nameSpan.title = domain;
    item.appendChild(nameSpan);

    // Company name (if tracker)
    if (info.tracker) {
      const compSpan = document.createElement("span");
      compSpan.className = "domain-company";
      compSpan.textContent = `${FLAGS[info.tracker.country] || ""} ${info.tracker.company}`;
      item.appendChild(compSpan);
    }

    // Badge
    if (info.piiLeak) {
      const b = document.createElement("span");
      b.className = "badge badge-pii";
      b.textContent = `PII (${info.piiType})`;
      item.appendChild(b);
    } else if (info.tracker) {
      const b = document.createElement("span");
      b.className = "badge badge-tracker";
      b.textContent = info.tracker.category;
      item.appendChild(b);
    } else if (info.isThirdParty) {
      const b = document.createElement("span");
      b.className = "badge badge-3p";
      b.textContent = "3rd-Party";
      item.appendChild(b);
    } else {
      const b = document.createElement("span");
      b.className = "badge badge-safe";
      b.textContent = "1st-Party";
      item.appendChild(b);
    }

    // Count badge
    const countBadge = document.createElement("span");
    countBadge.className = "badge badge-count";
    countBadge.textContent = info.count;
    item.appendChild(countBadge);

    domainList.appendChild(item);
  });
});
