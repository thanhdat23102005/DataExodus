// DataExodus Extension — Popup UI

const AGENT_URL = "http://localhost:8000";

async function refresh() {
  try {
    const resp = await fetch(`${AGENT_URL}/summary`);
    const data = await resp.json();
    document.getElementById("total").textContent = data.total_requests.toLocaleString();
    document.getElementById("trackers").textContent = data.tracker_requests.toLocaleString();
    document.getElementById("offshore").textContent = data.offshore_requests.toLocaleString();
    document.getElementById("pii").textContent = data.pii_requests.toLocaleString();
    document.getElementById("status").textContent = "Agent: connected";
    document.getElementById("status").style.color = "#2a2";
  } catch (e) {
    document.getElementById("status").textContent = "Agent: disconnected";
    document.getElementById("status").style.color = "#c22";
  }
}

// Toggle button
chrome.storage.local.get(["enabled"], (res) => {
  const btn = document.getElementById("toggle");
  const enabled = res.enabled !== false;
  btn.textContent = enabled ? "Pause collection" : "Resume collection";
  btn.onclick = () => {
    const newVal = !enabled;
    chrome.storage.local.set({ enabled: newVal }, () => {
      btn.textContent = newVal ? "Pause collection" : "Resume collection";
      location.reload();
    });
  };
});

refresh();
setInterval(refresh, 3000);
