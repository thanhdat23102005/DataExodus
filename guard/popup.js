let state;
const $=id=>document.getElementById(id);
async function send(type,extra={}){const r=await chrome.runtime.sendMessage({type,...extra});if(!r.ok)throw new Error(r.error);return r.data;}
async function load(){
  state=await send("state");
  $("mode").textContent=state.startupError || `${state.settings.enabled?"Protection on":"Protection paused"} · ${state.settings.cloudOptIn?"Cloud explanations enabled":"Local explanations only"}${state.settings.labMode?" · LAB MODE":""}`;
  $("toggle").textContent=state.settings.enabled?"Pause protection":"Resume protection";
  $("blocked").textContent=state.events.filter(e=>e.enforcement==="network_blocked").length;
  $("quarantined").textContent=state.events.filter(e=>e.enforcement==="navigation_quarantined").length;
  $("observed").textContent=state.events.filter(e=>e.kind==="identity_match").length;
  $("learned").textContent=state.learnedRulesCount || 0;
  $("events").replaceChildren();
  for(const e of state.events.slice(0,12)){
    const li=document.createElement("li"), label=document.createElement("b"), detail=document.createElement("div");
    label.textContent=e.domain || "Unknown destination";
    detail.textContent=`${e.enforcement} · ${e.signals.join(", ")}${e.evidence_quality==="page_report_unverified"?" · page report, unverified":""}`;
    detail.className="badge";li.append(label,detail);$("events").append(li);
  }
}
async function action(fn){try{$("status").textContent="";await fn();}catch(e){$("status").textContent=e.message;}}
$("settings").onclick=()=>chrome.runtime.openOptionsPage();
$("toggle").onclick=()=>action(async()=>{await send("save",{settings:{...state.settings,enabled:!state.settings.enabled}});await load();});
$("clear").onclick=()=>action(async()=>{await send("clear");await load();});
$("resetLearning").onclick=()=>action(async()=>{await send("reset_learning");await load();});
$("xray").onclick=()=>action(async()=>{
  const [tab]=await chrome.tabs.query({active:true,currentWindow:true});
  let r;
  try{r=await chrome.tabs.sendMessage(tab.id,{type:"xray"},{frameId:0});}
  catch{throw new Error("X-Ray works on http(s) pages. Reload the page once after installing Guard.");}
  $("xrayResult").textContent=!r?.on?"X-Ray off.":
    `X-Ray on: ${r.pixels} pixel(s), ${r.hidden_frames} hidden frame(s), ${r.overlays} invisible link(s), ${r.third_party_script_hosts} third-party script host(s). Heuristic view of the page, not proof of sending.`;
});
$("explain").onclick=()=>action(async()=>{
  $("explain").disabled=true;
  try{const a=await send("analyze");$("advice").hidden=false;$("advice").textContent=`${a.source} · ${a.cloud_status}\n${a.explanation}\nNext: ${a.next_step}\nAdvisory only; no protection settings changed.`;}
  finally{$("explain").disabled=false;}
});
$("export").onclick=()=>action(async()=>{
  const payload={schema:"dataexodus.guard.v1",exported_at:new Date().toISOString(),
    limits:"Recent bounded local events; page reports unverified; observations do not establish prevention.",
    events:state.events};
  const url=URL.createObjectURL(new Blob([JSON.stringify(payload,null,2)],{type:"application/json"}));
  const a=document.createElement("a");a.href=url;a.download="DataExodus_Guard_Evidence.json";a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
});
action(load);
