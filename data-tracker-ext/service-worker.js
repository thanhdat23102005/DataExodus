// service-worker.js - DataExodus Core Engine v3.3
// Intercepts all network traffic, classifies requests, detects PII leaks,
// calculates risk scores, and blocks malware domains.
import { lookupTracker } from './trackers.js';

// ============================================================
// 1. PII DETECTION (loaded from the identity index the popup builds)
//
//    FIX (v3.3): v3.2 loaded hashes via a fire-and-forget
//    chrome.storage.local.get callback at top level. MV3 evicts this
//    service worker after ~30s idle, so on every wake-up there was a
//    window where request listeners ran with an empty hash list and
//    scanned nothing — and a missed scan looks exactly like "no leak
//    found". Now the load is a promise the listener awaits.
// ============================================================
let piiIndex = null;        // { plaintexts: string[], hashes: { hex: algoName } }
let piiHashEntries = [];    // cached Object.entries(piiIndex.hashes)

const piiReady = chrome.storage.local.get("piiIndex").then((res) => {
  setPiiIndex(res.piiIndex || null);
});

function setPiiIndex(index) {
  piiIndex = index;
  piiHashEntries = index && index.hashes ? Object.entries(index.hashes) : [];
}

chrome.storage.onChanged.addListener((changes, area) => {
  if (area !== "local") return;
  if (changes.piiIndex) setPiiIndex(changes.piiIndex.newValue || null);
  if (changes.gatewayConfig) setGatewayConfig(changes.gatewayConfig.newValue);
});

function containsPii(str) {
  if (!str || !piiIndex) return null;
  const lower = str.toLowerCase();
  for (const plain of piiIndex.plaintexts) {
    if (lower.includes(plain)) return "plaintext";
  }
  for (const [hash, algo] of piiHashEntries) {
    if (lower.includes(hash)) return algo;
  }
  return null;
}

// ============================================================
// 2. MALWARE BLOCKER (Declarative Net Request)
//    resourceTypes stays main_frame/sub_frame: redirecting a script or
//    xhr load to an HTML page shows the user nothing, it just breaks
//    that sub-resource silently.
// ============================================================
const MALWARE_DOMAINS = [
  "malware-demo.com",
  "phishing-test.com",
];

chrome.runtime.onInstalled.addListener(async () => {
  const rules = MALWARE_DOMAINS.map((domain, i) => ({
    id: i + 1,
    priority: 1,
    action: {
      type: "redirect",
      redirect: { extensionPath: "/warning.html" },
    },
    condition: {
      urlFilter: domain,
      resourceTypes: ["main_frame", "sub_frame"],
    },
  }));

  await chrome.declarativeNetRequest.updateDynamicRules({
    removeRuleIds: rules.map((r) => r.id),
    addRules: rules,
  });
});

// ============================================================
// 3. HELPER FUNCTIONS
// ============================================================
function getDomain(urlStr) {
  try {
    return new URL(urlStr).hostname;
  } catch (e) {
    return null;
  }
}

function getBaseDomain(hostname) {
  if (!hostname) return "";
  const parts = hostname.split(".");
  const multiPartTlds = ["com.au", "gov.au", "net.au", "org.au", "co.uk", "co.nz"];
  const lastTwo = parts.slice(-2).join(".");
  if (multiPartTlds.includes(lastTwo) && parts.length >= 3) {
    return parts.slice(-3).join(".");
  }
  if (parts.length >= 2) {
    return parts.slice(-2).join(".");
  }
  return hostname;
}

function isThirdParty(sourceDomain, destDomain) {
  if (!sourceDomain || !destDomain) return false;
  return getBaseDomain(sourceDomain) !== getBaseDomain(destDomain);
}

// ============================================================
// 4. RISK SCORING ALGORITHM
//    Self-designed heuristic, not from a published model - say so
//    explicitly wherever this number appears in the report.
//    Only covert (third-party) PII adds the 30-point penalty.
// ============================================================
function calculateRiskScore(tabData) {
  let score = 0;
  const companies = new Set();
  const countries = new Set();
  let totalReqs = 0;
  let thirdPartyReqs = 0;
  let hasAdvertising = 0;

  for (const info of Object.values(tabData.requests)) {
    totalReqs += info.count;
    if (info.isThirdParty) thirdPartyReqs += info.count;
    if (info.tracker) {
      companies.add(info.tracker.company);
      if (info.tracker.country !== "AU") countries.add(info.tracker.country);
      if (info.tracker.category === "Advertising") hasAdvertising++;
    }
  }

  score += companies.size * 8;
  score += countries.size * 5;
  score += hasAdvertising * 3;
  if (totalReqs > 0 && (thirdPartyReqs / totalReqs) > 0.5) score += 10;
  if (tabData.piiLeaked) score += 30;

  return Math.min(score, 100);
}

// ============================================================
// 5. IN-MEMORY STATE
//    One canonical mutable object per tab. Requests mutate it directly
//    and synchronously, so there is no read-a-copy/write-a-copy window
//    for concurrent requests to lose updates in. chrome.storage.local
//    is only a periodic snapshot, written so the popup can read it.
//
//    Trade-off: if MV3 evicts this worker between flushes, up to
//    FLUSH_INTERVAL_MS of activity for a tab is lost. Bounded and small.
// ============================================================
const tabDataCache = new Map();
const hydrating = new Map();
const dirtyTabs = new Set();
const FLUSH_INTERVAL_MS = 400;
const MAX_PII_DETAILS = 50;

function defaultTabData(url) {
  const domain = getDomain(url);
  return {
    url,
    domain,
    baseDomain: getBaseDomain(domain),
    requests: {},
    piiLeaked: false,
    piiDetails: [],
    riskScore: 0,
  };
}

async function ensureTabData(tabId, fallbackUrl) {
  if (tabDataCache.has(tabId)) return tabDataCache.get(tabId);

  let hydration = hydrating.get(tabId);
  if (!hydration) {
    hydration = (async () => {
      const key = `tabData_${tabId}`;
      const stored = await chrome.storage.local.get(key);
      if (!tabDataCache.has(tabId)) {
        tabDataCache.set(tabId, stored[key] || defaultTabData(fallbackUrl));
      }
    })();
    hydrating.set(tabId, hydration);
  }

  await hydration;
  hydrating.delete(tabId);
  return tabDataCache.get(tabId);
}

function markDirty(tabId) {
  dirtyTabs.add(tabId);
}

// ============================================================
// 6. GATEWAY TELEMETRY (Raspberry Pi backend)
//
//    FIX (v3.3), three problems with v3.2:
//    a) the gateway address was hardcoded, so the extension only worked
//       on one LAN - it broke the moment the laptop moved networks;
//    b) every flush re-sent each tab's ENTIRE accumulated request map,
//       so a long session on a busy page shipped the same growing blob
//       ~2.5x per second. Only changed destinations are sent now;
//    c) failures were swallowed by an empty catch, so a gateway that was
//       off (or an address that was wrong) looked identical to one that
//       was working. Status is recorded and shown in the popup.
//
//    Full page URLs are deliberately NOT sent - only hostnames. A URL
//    carries search terms, session ids and query parameters, and this is
//    a privacy tool.
// ============================================================
const DEFAULT_GATEWAY_URL = "http://192.168.0.83:5000/api/telemetry";
const GATEWAY_TIMEOUT_MS = 4000;

let gatewayConfig = { url: DEFAULT_GATEWAY_URL, enabled: true };
let gatewayFlushInFlight = false;
const pendingTelemetry = new Map();  // tabId -> { domains: Set, sentPii: number }

const gatewayReady = chrome.storage.local.get("gatewayConfig").then((res) => {
  setGatewayConfig(res.gatewayConfig);
});

function setGatewayConfig(cfg) {
  gatewayConfig = {
    url: (cfg && cfg.url) || DEFAULT_GATEWAY_URL,
    enabled: cfg ? cfg.enabled !== false : true,
  };
}

function markTelemetryChange(tabId, destDomain) {
  let pending = pendingTelemetry.get(tabId);
  if (!pending) {
    pending = { domains: new Set(), sentPii: 0 };
    pendingTelemetry.set(tabId, pending);
  }
  pending.domains.add(destDomain);
}

function buildTelemetryPayload() {
  const tabs = {};
  let changes = 0;

  for (const [tabId, pending] of pendingTelemetry) {
    const data = tabDataCache.get(tabId);
    if (!data) continue;

    const requests = {};
    for (const domain of pending.domains) {
      if (data.requests[domain]) requests[domain] = data.requests[domain];
    }
    const newPii = data.piiDetails.slice(pending.sentPii);
    if (Object.keys(requests).length === 0 && newPii.length === 0) continue;

    tabs[`tabData_${tabId}`] = {
      domain: data.domain,
      baseDomain: data.baseDomain,
      riskScore: data.riskScore,
      piiLeaked: data.piiLeaked,
      newPiiDetails: newPii,
      requests,
    };
    changes++;
  }

  return changes > 0 ? tabs : null;
}

async function recordGatewayStatus(ok, detail) {
  await chrome.storage.local.set({
    gatewayStatus: { ok, detail: detail || null, at: Date.now() },
  });
}

async function sendTelemetry() {
  if (!gatewayConfig.enabled || gatewayFlushInFlight) return;

  const snapshot = new Map();
  for (const [tabId, pending] of pendingTelemetry) {
    snapshot.set(tabId, { domains: new Set(pending.domains), sentPii: pending.sentPii });
  }

  const telemetry = buildTelemetryPayload();
  if (!telemetry) return;

  gatewayFlushInFlight = true;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), GATEWAY_TIMEOUT_MS);

  try {
    const res = await fetch(gatewayConfig.url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ telemetry, timestamp: Date.now(), delta: true }),
      signal: controller.signal,
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);

    // Only clear what was actually delivered. A failed send leaves the
    // pending set intact so the next flush retries it instead of
    // dropping the requests on the floor.
    for (const [tabId, sent] of snapshot) {
      const pending = pendingTelemetry.get(tabId);
      if (!pending) continue;
      for (const domain of sent.domains) pending.domains.delete(domain);
      const data = tabDataCache.get(tabId);
      if (data) pending.sentPii = data.piiDetails.length;
    }
    await recordGatewayStatus(true);
  } catch (err) {
    const detail = err.name === "AbortError" ? "timeout" : String(err.message || err);
    await recordGatewayStatus(false, detail);
  } finally {
    clearTimeout(timer);
    gatewayFlushInFlight = false;
  }
}

async function flushDirtyTabs() {
  if (dirtyTabs.size > 0) {
    const toWrite = {};
    for (const tabId of dirtyTabs) {
      const data = tabDataCache.get(tabId);
      if (data) toWrite[`tabData_${tabId}`] = data;
    }
    dirtyTabs.clear();
    if (Object.keys(toWrite).length > 0) {
      await chrome.storage.local.set(toWrite);
    }
  }
  await sendTelemetry();
}

setInterval(flushDirtyTabs, FLUSH_INTERVAL_MS);
chrome.runtime.onSuspend?.addListener(() => {
  flushDirtyTabs();
});

// ============================================================
// 7. MAIN REQUEST LISTENER
// ============================================================
chrome.webRequest.onBeforeRequest.addListener(
  (details) => {
    if (details.tabId === -1) return;

    (async () => {
      try {
        const destDomain = getDomain(details.url);
        if (!destDomain) return;

        const tab = await chrome.tabs.get(details.tabId);
        if (!tab || !tab.url) return;
        const sourceDomain = getDomain(tab.url);
        if (!sourceDomain) return;

        const thirdParty = isThirdParty(sourceDomain, destDomain);
        const trackerInfo = lookupTracker(destDomain);

        await piiReady;

        let piiType = containsPii(details.url);
        if (!piiType && details.requestBody) {
          if (details.requestBody.formData) {
            piiType = containsPii(JSON.stringify(details.requestBody.formData));
          } else if (details.requestBody.raw) {
            for (const raw of details.requestBody.raw) {
              if (raw.bytes) {
                const str = String.fromCharCode.apply(null, new Uint8Array(raw.bytes));
                piiType = containsPii(str);
                if (piiType) break;
              }
            }
          }
        }

        const tabData = await ensureTabData(details.tabId, tab.url);

        // Everything below mutates the same in-memory object directly.
        // No await between here and the end of the block, so no other
        // request for this tab can interleave mid-update.

        // Scope matters: typing your email into a site's own search box
        // sends it first-party, which you chose to do. That same value
        // reaching a third party is the covert case the study is about.
        // Both are recorded; only the covert one raises the alarm.
        const piiScope = piiType ? (thirdParty ? "covert" : "intentional") : null;

        if (piiScope === "covert") {
          tabData.piiLeaked = true;
        }
        if (piiScope) {
          tabData.piiDetails.push({
            type: piiType,
            scope: piiScope,
            destination: destDomain,
            company: trackerInfo ? trackerInfo.company : "Unknown",
          });
          if (tabData.piiDetails.length > MAX_PII_DETAILS) {
            tabData.piiDetails.splice(0, tabData.piiDetails.length - MAX_PII_DETAILS);
          }
        }

        if (!tabData.requests[destDomain]) {
          tabData.requests[destDomain] = {
            count: 0,
            isThirdParty: thirdParty,
            tracker: trackerInfo,
            piiLeak: false,
            piiType: null,
            piiScope: null,
          };
        }
        tabData.requests[destDomain].count++;
        if (piiScope) {
          tabData.requests[destDomain].piiLeak = piiScope === "covert";
          tabData.requests[destDomain].piiType = piiType;
          tabData.requests[destDomain].piiScope = piiScope;
        }

        tabData.riskScore = calculateRiskScore(tabData);

        markDirty(details.tabId);
        markTelemetryChange(details.tabId, destDomain);
      } catch (err) {
        // Tab might be closed or chrome:// URL
      }
    })();
  },
  { urls: ["<all_urls>"] },
  ["requestBody"]
);

// ============================================================
// 8. TAB LIFECYCLE MANAGEMENT
// ============================================================
chrome.tabs.onRemoved.addListener(async (tabId) => {
  tabDataCache.delete(tabId);
  dirtyTabs.delete(tabId);
  hydrating.delete(tabId);
  pendingTelemetry.delete(tabId);
  await chrome.storage.local.remove(`tabData_${tabId}`);
});

chrome.tabs.onUpdated.addListener(async (tabId, changeInfo) => {
  if (changeInfo.status === "loading" && changeInfo.url) {
    const fresh = defaultTabData(changeInfo.url);
    tabDataCache.set(tabId, fresh);
    pendingTelemetry.delete(tabId);
    // Flush immediately so the popup doesn't show the previous page's
    // stale data if opened right after navigation starts.
    await chrome.storage.local.set({ [`tabData_${tabId}`]: fresh });
    dirtyTabs.delete(tabId);
  }
});
