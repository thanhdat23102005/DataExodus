// DataExodus extension: merge request phases by Chrome requestId.
// Collection is local. Pending in-memory events may be lost if the MV3 worker stops.
const AGENT_ORIGIN = "http://localhost:8000";
const AGENT_URL = `${AGENT_ORIGIN}/ingest`;
const BADGE_COLORS = { green: "#0ca30c", yellow: "#fab219", red: "#d03b3b" };
const pending = new Map();
let buffer = [];
let enabled = true;
let flushTimer = null;
let flushing = false;

function isSelfTraffic(url) {
  return /^(chrome|chrome-extension|about|devtools):/.test(url) ||
         /^https?:\/\/(localhost|127\.0\.0\.1|\[::1\]):8000(\/|$)/.test(url);
}
chrome.storage.local.get(["enabled"], res => { enabled = res.enabled !== false; });
chrome.storage.onChanged.addListener(changes => {
  if (changes.enabled) {
    enabled = changes.enabled.newValue;
    if (!enabled) { pending.clear(); buffer = []; }
  }
});
function newEntry(d) {
  return { requestId: d.requestId, ts: d.timeStamp / 1000, url: d.url,
           type: d.type, method: d.method, tabId: d.tabId, initiator: d.initiator };
}
chrome.webRequest.onBeforeRequest.addListener(d => {
  if (!enabled || isSelfTraffic(d.url)) return;
  let body = null;
  try {
    if (d.requestBody?.raw) {
      body = d.requestBody.raw.map(part => part.bytes ? new TextDecoder().decode(part.bytes) : "").join("");
    } else if (d.requestBody?.formData) body = JSON.stringify(d.requestBody.formData);
  } catch (_) {}
  if (pending.size > 2000) pending.delete(pending.keys().next().value);
  pending.set(d.requestId, { ...newEntry(d), body: body?.slice(0, 131072) ?? null });
}, {urls:["<all_urls>"]}, ["requestBody"]);
chrome.webRequest.onSendHeaders.addListener(d => {
  if (!enabled || isSelfTraffic(d.url)) return;
  const entry = pending.get(d.requestId) || newEntry(d);
  entry.headers = {};
  for (const h of d.requestHeaders || []) {
    entry.headers[h.name] = String(h.value ?? "");
    if (h.name.toLowerCase() === "cookie") entry.cookies = String(h.value ?? "").slice(0,65536);
  }
  pending.set(d.requestId, entry);
}, {urls:["<all_urls>"]}, ["requestHeaders", "extraHeaders"]);
function finishRequest(d) {
  const entry = pending.get(d.requestId);
  if (!entry) return;
  pending.delete(d.requestId);
  if (!enabled) return;
  buffer.push(entry);
  if (buffer.length > 10000) buffer.splice(0, buffer.length - 10000);
  if (!flushTimer) flushTimer = setTimeout(() => {flushTimer = null; flush();}, 1000);
}
for (const event of [chrome.webRequest.onCompleted, chrome.webRequest.onErrorOccurred, chrome.webRequest.onBeforeRedirect]) {
  event.addListener(finishRequest, {urls:["<all_urls>"]});
}
async function flush() {
  if (!enabled || !buffer.length || flushing) return;
  flushing = true;
  const batch = buffer.splice(0, 500);
  try {
    const response = await fetch(AGENT_URL, {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({events:batch})});
    if (!response.ok) throw new Error(response.statusText);
  } catch (_) {
    if (enabled) buffer = [...batch, ...buffer].slice(-10000);
  } finally { flushing = false; }
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

// Chrome 120+ supports a 30-second minimum alarm interval.
// The short timer above is best-effort; these alarms provide a fallback.
chrome.alarms.create("flush", { periodInMinutes: 0.5 });
chrome.alarms.create("badge", { periodInMinutes: 0.5 });
chrome.alarms.onAlarm.addListener(alarm => {
  if (alarm.name === "flush") flush();
  if (alarm.name === "badge") updateActiveBadge();
});
chrome.tabs.onActivated.addListener(({tabId}) => { flush(); updateBadge(tabId); });
chrome.tabs.onUpdated.addListener((tabId, info, tab) => {
  if (info.status === "complete") { flush(); if (tab.active) updateBadge(tabId); }
});
chrome.windows.onRemoved.addListener(flush);
updateActiveBadge();
