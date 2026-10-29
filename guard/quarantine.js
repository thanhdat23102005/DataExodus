/* No external fetch, iframe URL, navigation or code supplied by the website.
 * A sandbox preview runs on the DataExodus service when the user asks; this
 * page renders its JSON as text, and the screenshot only as a data: image. */
const $=id=>document.getElementById(id);
const escapeHTML=value=>String(value).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const REASONS={
  network_rule:"A browser network rule stopped this navigation to a listed domain.",
  ad_click:"You clicked an ad. The browser stopped the click before it reached the ad network.",
  identity_url:"This navigation carried your protected identifier to another site. The browser stopped it; the address was not kept.",
  popup_without_link:"A scripted popup or blocked link was intercepted after your click; the page report is unverified.",
  transparent_overlay:"A transparent link overlay was intercepted after your click; review for possible false positives.",
  opened_directly:"This page was opened directly, not by a Guard rule. Treat the destination as unverified.",
};
let recordId="";
async function send(type,extra={}){
  const response=await chrome.runtime.sendMessage({type,...extra});
  if(!response || !response.ok)throw new Error(response?response.error:"No response from Guard");
  return response.data;
}
async function adopt(){
  // Worker-opened tabs carry only a random id. A Chrome redirect carries
  // ?reason=…#<original URL>: hand it to the worker, then replace the
  // fragment so the URL leaves the address bar and this history entry.
  const hash=location.hash.slice(1);
  if(/^[a-f0-9-]{36}$/i.test(hash))return hash;
  const params=new URLSearchParams(location.search);
  const adopted=await send("quarantine_adopt",{reason:params.get("reason"),url:hash});
  history.replaceState(null,"","#"+(adopted?.id || ""));
  return adopted?.id || "";
}
function item(list,text){const li=document.createElement("li");li.textContent=text;list.append(li);}
function render(record){
  let summary="No destination metadata is available. No website was loaded.";
  if(record){
    let reason=REASONS[record.reason] || "A suspicious navigation was intercepted.";
    if(record.network)reason+=" Ad network: "+record.network+".";
    if(record.reason==="identity_url" && !record.verified)reason+=" Guard could not confirm that one of its rules sent you here.";
    $("reason").textContent=reason;
    if(record.destination){
      $("origin").textContent="Destination origin: "+record.destination.origin;
      summary="Destination: "+record.destination.origin+"\nPath segments: "+record.destination.path_segments+
        "\nQuery fields: "+record.destination.query_fields+"\nFragment present: "+record.destination.has_fragment+"\nRemote content loaded: no";
    }
    $("sandboxPreview").hidden=!record.has_url;
    $("sandboxPreview").title=record.sandbox_configured?"":"Set the local service token in Guard Settings first.";
    $("direct").hidden=!record.direct_available;
    $("original").hidden=!record.has_url;
  }
  $("preview").srcdoc="<!doctype html><meta http-equiv=\"Content-Security-Policy\" content=\"default-src 'none'; base-uri 'none'; form-action 'none'\"><h2>Offline metadata only</h2><pre>"+escapeHTML(summary)+"</pre>";
}
function renderSandbox(r){
  $("sandbox").hidden=false;
  if(!r.ok){$("verdict").textContent="The sandbox could not open the link: "+(r.error || "unknown error");return;}
  const stuck=!r.clean_url;
  $("verdict").textContent=stuck?"The link never left the ad network: no destination page":
    r.trackers.length?`The landing page loads ${r.trackers.length} tracker(s)`:"No trackers recognised on the landing page";
  $("verdict").className="verdict "+(stuck || r.trackers.length?"tracking":"clean");
  $("detail").textContent=`${r.redirect_chain.length} hop(s), ${r.request_count} request(s) inside the sandbox`+
    (r.refused_internal?.length?`, ${r.refused_internal.length} refused because they targeted a local address`:"")+
    ". None carried your cookies or logins."+(r.sandbox_host?" Opened on: "+r.sandbox_host+".":"");
  $("chain").replaceChildren();for(const hop of r.redirect_chain)item($("chain"),hop);
  $("clean").textContent=r.clean_url || "(not available)";
  $("trackers").replaceChildren();
  if(r.trackers.length)for(const t of r.trackers)item($("trackers"),[t.domain,t.owner,t.category,t.country].filter(Boolean).join(" · "));
  else item($("trackers"),r.classifier_available===false?"Tracker lists not installed on the service (run setup_data.py there).":"None recognised.");
  $("shot").replaceChildren();
  if(typeof r.screenshot_jpeg_b64==="string" && /^[A-Za-z0-9+/=]+$/.test(r.screenshot_jpeg_b64)){
    const img=document.createElement("img");img.alt="Screenshot of the destination taken inside the sandbox browser";
    img.src="data:image/jpeg;base64,"+r.screenshot_jpeg_b64;$("shot").append(img);
  }
  $("title").textContent=r.title?"Page title: "+r.title:"";
  // Score and reasons from the service (protection/verdict.py), shown as text.
  const a=r.assessment,level=a && ["low","caution","danger"].includes(a.level)?a.level:"unknown";
  $("assessment").hidden=!a;
  if(a){
    $("score").textContent=(a.label || "Not assessed")+(typeof a.score==="number"?" · score "+a.score+" / 100":"");
    $("score").className="score "+level;
    $("reasons").replaceChildren();
    for(const x of (Array.isArray(a.reasons)?a.reasons:[]).slice(0,8))item($("reasons"),"+"+(Number(x.points)||0)+"  "+x.text);
    if(!$("reasons").children.length)item($("reasons"),"No risk signals were observed in this visit.");
    $("note").textContent=a.note || "";
  }
  // A dangerous destination is not offered as a one-click "clean" link.
  $("openClean").hidden=stuck || level==="danger";
}
async function act(fn){try{$("status").textContent="";await fn();}catch(error){$("status").textContent=error.message;}}
$("sandboxPreview").onclick=()=>act(async()=>{
  $("sandboxPreview").disabled=true;$("status").textContent="Opening the link in the isolated sandbox…";
  try{renderSandbox(await send("sandbox_preview",{id:recordId}));$("status").textContent="";}
  catch(error){throw new Error("Sandbox unavailable ("+error.message+"). Nothing was opened.");}
  finally{$("sandboxPreview").disabled=false;}
});
$("openClean").onclick=()=>act(()=>send("open_destination",{id:recordId,target:"clean"}));
$("direct").onclick=()=>act(()=>send("open_destination",{id:recordId,target:"direct"}));
$("original").onclick=()=>act(()=>send("open_destination",{id:recordId,target:"original"}));
$("back").onclick=()=>{if(history.length>1)history.back();else $("close").click();};
$("close").onclick=()=>act(()=>send("close_quarantine"));
adopt().then(id=>{recordId=id;return send("quarantine_state",{id});}).then(render)
  .catch(error=>{render(null);$("status").textContent=error.message;});
