// DataExodus Extension — Background Service Worker
// Batches requests and pushes to local agent every 5 seconds.

const AGENT_ORIGIN = "http://localhost:8000";
const AGENT_URL = `${AGENT_ORIGIN}/ingest`;
const BATCH_MS = 5000;
const BADGE_MS = 4000;
// Traffic light: badge colour states the risk of the page you're looking at.
const BADGE_COLORS = { green: "#0ca30c", yellow: "#fab219", red: "#d03b3b" };
let buffer = [];
let enabled = true;

// Never measure ourselves: the extension's own POSTs to the agent, the
// dashboard's polling, and chrome-internal pages would otherwise dominate the
// feed and inflate every count.
function isSelfTraffic(url) {
  return /^(chrome|chrome-extension|about|devtools):/.test(url) ||
         /^https?:\/\/(localhost|127\.0\.0\.1|\[::1\])(:\d+)?\//.test(url);
}

chrome.storage.local.get(["enabled"], (res) => {
  enabled = res.enabled !== false;
});

chrome.storage.onChanged.addListener((changes) => {
  if (changes.enabled) enabled = changes.enabled.newValue;
});

// Capture request bodies
chrome.webRequest.onBeforeRequest.addListener(
  (details) => {
    if (!enabled || isSelfTraffic(details.url)) return;
    let body = null;
    if (details.requestBody) {
      if (details.requestBody.raw) {
        try {
          const bytes = details.requestBody.raw[0]?.bytes;
          if (bytes) body = new TextDecoder().decode(bytes);
        } catch (e) {}
      } else if (details.requestBody.formData) {
        body = JSON.stringify(details.requestBody.formData);
      }
    }
    buffer.push({
      ts: details.timeStamp,
      url: details.url,
      type: details.type,
      method: details.method,
      tabId: details.tabId,
      initiator: details.initiator,
      body: body,
    });
  },
  { urls: ["<all_urls>"] },
  ["requestBody"]
);

// Capture headers & cookies
chrome.webRequest.onSendHeaders.addListener(
  (details) => {
    if (!enabled || isSelfTraffic(details.url)) return;
    // Find existing entry or append
    const entry = buffer.find(e => e.ts === details.timeStamp && e.url === details.url);
    const headers = {};
    let cookies = null;
    for (const h of details.requestHeaders || []) {
      headers[h.name] = h.value;
      if (h.name.toLowerCase() === "cookie") cookies = h.value;
    }
    if (entry) {
      entry.headers = headers;
      entry.cookies = cookies;
    } else {
      buffer.push({
        ts: details.timeStamp,
        url: details.url,
        type: details.type,
        method: details.method,
        tabId: details.tabId,
        initiator: details.initiator,
        headers,
        cookies,
      });
    }
  },
  { urls: ["<all_urls>"] },
  ["requestHeaders"]
);

// Flush batch periodically
async function flush() {
  if (!buffer.length) return;
  const batch = buffer.splice(0, buffer.length);
  try {
    const resp = await fetch(AGENT_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ events: batch }),
    });
    if (!resp.ok) throw new Error(resp.statusText);
  } catch (e) {
    // Agent offline — push back (with cap)
    buffer.unshift(...batch);
    if (buffer.length > 10000) buffer.length = 10000;
  }
}

// --- Traffic-light badge -------------------------------------------------
// Green / amber / red on the toolbar icon for the ACTIVE tab, driven by the
// agent's rolling per-site risk (GET /site/{domain}). Badge text is the
// tracker count, so a clean site shows a bare green icon with no number.
async function updateBadge(tabId) {
  try {
    const tab = await chrome.tabs.get(tabId);
    if (!tab || !tab.url || !/^https?:/.test(tab.url)) {
      chrome.action.setBadgeText({ text: "", tabId });
      return;
    }
    const host = new URL(tab.url).hostname;
    const info = await fetch(`${AGENT_ORIGIN}/site/${encodeURIComponent(host)}`).then(r => r.json());
    const level = info.risk_level || "green";
    chrome.action.setBadgeBackgroundColor({ color: BADGE_COLORS[level] || BADGE_COLORS.green, tabId });
    chrome.action.setBadgeText({
      text: info.tracker_requests > 0 ? String(Math.min(info.tracker_requests, 99)) : "",
      tabId,
    });
    chrome.action.setTitle({
      title: info.tracker_requests
        ? `DataExodus — ${info.tracker_requests} tracker request(s), risk: ${level}`
        : "DataExodus — no trackers detected on this page yet",
      tabId,
    });
  } catch (e) {
    // Agent offline: leave the badge as-is rather than flickering it blank.
  }
}

async function updateActiveBadge() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (tab) updateBadge(tab.id);
}

chrome.alarms.create("flush", { periodInMinutes: BATCH_MS / 60000 });
chrome.alarms.create("badge", { periodInMinutes: BADGE_MS / 60000 });
chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name === "flush") flush();
  if (alarm.name === "badge") updateActiveBadge();
});

// Also flush on tab change / window close
chrome.tabs.onActivated.addListener(({ tabId }) => { flush(); updateBadge(tabId); });
chrome.tabs.onUpdated.addListener((tabId, info, tab) => {
  if (info.status === "complete" && tab.active) updateBadge(tabId);
});
chrome.windows.onRemoved.addListener(flush);
updateActiveBadge();
