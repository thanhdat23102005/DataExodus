// service-worker.js - DataExodus Core Engine v3.1
// Intercepts all network traffic, classifies requests, detects PII leaks,
// calculates risk scores, and blocks malware domains.
import { lookupTracker } from './trackers.js';

// ============================================================
// 1. PII HASH DETECTION
//    Pre-computed hashes for test@example.com
//    Swap these for hashes of your real identifier before
//    treating results as evidence — this is still a demo value.
// ============================================================
const TEST_EMAIL = "test@example.com";
const TARGET_HASHES = [
  "55502f40dc8b7c769880b10874abc9d0",                                          // MD5
  "567159d622ffbb50b11b0efd307be358624a26ee",                                  // SHA1
  "973dfe463ec85785f5f95af5ba3906eedb2d931c24e69824a89ea65dba4e813b",          // SHA256
  TEST_EMAIL,                                                                    // Plaintext
];

function containsPii(str) {
  if (!str) return null;
  const lower = str.toLowerCase();
  for (const hash of TARGET_HASHES) {
    if (lower.includes(hash)) {
      if (hash === TEST_EMAIL) return "plaintext";
      if (hash.length === 32) return "MD5";
      if (hash.length === 40) return "SHA1";
      return "SHA256";
    }
  }
  return null;
}

// ============================================================
// 2. MALWARE BLOCKER (Declarative Net Request)
//    Blocks known malicious domains and redirects to warning page.
//
//    FIX (v3.1): resourceTypes narrowed to main_frame/sub_frame only.
//    Redirecting a `script` or `xmlhttprequest` load to an HTML page
//    does not show the user anything — Chrome just blocks that one
//    sub-resource silently (the target isn't in web_accessible_resources,
//    and even if it were, serving HTML where JS/JSON was expected just
//    breaks the page instead of warning the user). Only full-page
//    navigations can meaningfully show warning.html.
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

/**
 * Proper third-party detection using eTLD+1 comparison.
 * Example: "cdn.facebook.com" vs "facebook.com" -> same party
 *          "facebook.com" vs "abc.net.au" -> third party
 */
function getBaseDomain(hostname) {
  if (!hostname) return "";
  const parts = hostname.split(".");
  // Handle .com.au, .gov.au, .co.uk style TLDs
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
//    Calculates a 0-100 weighted risk score for each tab.
//    Higher score = more privacy risk.
//
//    Weights (self-designed heuristic, not from a published model —
//    say so explicitly if this number appears in the report):
//    - Each unique tracker company:       +8 points
//    - Each unique country (non-AU):      +5 points
//    - Third-party request ratio > 50%:   +10 points
//    - PII leak detected:                 +30 points
//    - Advertising category tracker:      +3 extra per unique
//    Score is capped at 100.
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
      if (info.tracker.country !== "AU") {
        countries.add(info.tracker.country);
      }
      if (info.tracker.category === "Advertising") {
        hasAdvertising++;
      }
    }
  }

  score += companies.size * 8;       // Each unique tracker company
  score += countries.size * 5;        // Each unique foreign country
  score += hasAdvertising * 3;        // Advertising trackers are worse

  if (totalReqs > 0 && (thirdPartyReqs / totalReqs) > 0.5) {
    score += 10;                      // High third-party ratio
  }
  if (tabData.piiLeaked) {
    score += 30;                      // PII leak is very dangerous
  }

  return Math.min(score, 100);        // Cap at 100
}

// ============================================================
// 5. IN-MEMORY STATE (FIX for v3.0 race condition)
//
//    v3.0 used chrome.storage.local as the read-modify-write target
//    for every single request: get() -> mutate -> set(). Because
//    storage.local access is a real async round-trip, a burst of
//    concurrent requests (normal on any modern page) could interleave:
//    two requests both read the same "old" snapshot, both mutate their
//    own copy, and whichever set() finishes last silently overwrites
//    the other's update. Counts and even PII-leak flags could be lost
//    with no error and no way to detect it after the fact.
//
//    Fix: keep one canonical mutable object per tab in memory
//    (tabDataCache). Every request mutates that same object directly,
//    in place, synchronously — there is no read-a-copy/write-a-copy
//    step for the race to land in. chrome.storage.local is now only
//    a periodic, debounced *snapshot* of that in-memory state, written
//    just so the popup (a separate context) can read it.
//
//    Trade-off: MV3 service workers can be evicted from memory after
//    ~30s idle. If that happens, up to FLUSH_INTERVAL_MS of unflushed
//    activity for a tab can be lost. That window is bounded and small
//    (default 400ms) — acceptable for this project's purposes, but
//    worth stating explicitly rather than pretending it's perfect.
// ============================================================
const tabDataCache = new Map();   // tabId -> tabData (canonical, in-memory)
const hydrating = new Map();      // tabId -> in-flight storage read promise
const dirtyTabs = new Set();      // tabIds with unflushed changes
const FLUSH_INTERVAL_MS = 400;

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

// Returns the canonical in-memory tabData for a tab, hydrating it from
// chrome.storage.local at most once (e.g. after a service worker restart).
// Concurrent callers for the same brand-new tab are guaranteed to share
// a single hydration read via the `hydrating` map, never duplicate it.
async function ensureTabData(tabId, fallbackUrl) {
  if (tabDataCache.has(tabId)) {
    return tabDataCache.get(tabId);
  }

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

async function flushDirtyTabs() {
  if (dirtyTabs.size === 0) return;
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

setInterval(flushDirtyTabs, FLUSH_INTERVAL_MS);
// Best-effort final flush if Chrome gives the service worker a chance
// to run code before suspending it. Not guaranteed to fire.
chrome.runtime.onSuspend?.addListener(() => {
  flushDirtyTabs();
});

// ============================================================
// 6. MAIN REQUEST LISTENER
//    Intercepts every outgoing HTTP request and records it.
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

        // --- PII Leak Detection ---
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

        // --- Get the canonical in-memory record (only async on first use) ---
        const tabData = await ensureTabData(details.tabId, tab.url);

        // --- Everything below mutates the SAME in-memory object directly.
        //     No await between here and the end of the block, so no other
        //     request for this tab can interleave mid-update. ---
        if (piiType) {
          tabData.piiLeaked = true;
          tabData.piiDetails.push({
            type: piiType,
            destination: destDomain,
            company: trackerInfo ? trackerInfo.company : "Unknown",
          });
        }

        if (!tabData.requests[destDomain]) {
          tabData.requests[destDomain] = {
            count: 0,
            isThirdParty: thirdParty,
            tracker: trackerInfo,   // null if not a tracker, { company, country, category } if it is
            piiLeak: false,
            piiType: null,
          };
        }
        tabData.requests[destDomain].count++;
        if (piiType) {
          tabData.requests[destDomain].piiLeak = true;
          tabData.requests[destDomain].piiType = piiType;
        }

        tabData.riskScore = calculateRiskScore(tabData);

        markDirty(details.tabId);
      } catch (err) {
        // Tab might be closed or chrome:// URL
      }
    })();
  },
  { urls: ["<all_urls>"] },
  ["requestBody"]
);

// ============================================================
// 7. TAB LIFECYCLE MANAGEMENT
// ============================================================
chrome.tabs.onRemoved.addListener(async (tabId) => {
  tabDataCache.delete(tabId);
  dirtyTabs.delete(tabId);
  hydrating.delete(tabId);
  await chrome.storage.local.remove(`tabData_${tabId}`);
});

chrome.tabs.onUpdated.addListener(async (tabId, changeInfo) => {
  if (changeInfo.status === "loading" && changeInfo.url) {
    const fresh = defaultTabData(changeInfo.url);
    tabDataCache.set(tabId, fresh);
    // Flush immediately so the popup doesn't show the previous page's
    // stale data if opened right after navigation starts.
    await chrome.storage.local.set({ [`tabData_${tabId}`]: fresh });
    dirtyTabs.delete(tabId);
  }
});
