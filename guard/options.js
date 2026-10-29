const $=id=>document.getElementById(id);
let current,listedDomain="";
async function send(type,extra={}){const r=await chrome.runtime.sendMessage({type,...extra});if(!r.ok)throw new Error(r.error);return r.data;}
async function load(){
  current=(await send("state")).settings;
  for(const key of ["enabled","popupGuard","labMode","cloudOptIn","preventCollection","learnCollection","quarantineAds"])$(key).checked=current[key];
  for(const key of ["testEmail","apiToken"])$(key).value=current[key];
  for(const key of ["blockedDomains","allowSites"])$(key).value=current[key].join("\n");
}
$("form").onsubmit=async e=>{
  e.preventDefault();
  $("status").textContent="Applying rules…";
  try{
    const next={...current};
    for(const key of ["enabled","popupGuard","labMode","cloudOptIn","preventCollection","learnCollection","quarantineAds"])next[key]=$(key).checked;
    for(const key of ["testEmail","apiToken"])next[key]=$(key).value.trim();
    for(const key of ["blockedDomains","allowSites"]){
      next[key]=$(key).value.split(/\s+/).filter(Boolean);
      if(next[key].length>500 || next[key].some(d=>!GuardCore.domain(d)))throw new Error("Use at most 500 valid domains per list; no URL paths or wildcards.");
    }
    await send("save",{settings:next});await load();$("status").textContent="Rules applied. Reload existing tabs for a clean test.";
  }catch(error){$("status").textContent=error.message;}
};
$("ruleImport").onchange=async()=>{
  try{
    const file=$("ruleImport").files[0];if(!file)return;
    if(file.size>131072)throw new Error("Rule file is too large.");
    const data=JSON.parse(await file.text());
    if(data.schema!=="dataexodus.guard.domains.v1" || !Array.isArray(data.domains) ||
       data.domains.length>500 || data.domains.some(d=>typeof d!=="string" || !GuardCore.domain(d)))throw new Error("Invalid domain export.");
    $("blockedDomains").value=data.domains.map(GuardCore.domain).join("\n");
    $("status").textContent="Imported "+data.domains.length+" domains for review. Click Save to apply. Path rules and exceptions are not included.";
  }catch(error){$("status").textContent=error.message;}
};
$("lookup").onclick=async()=>{
  listedDomain="";$("blockDetected").hidden=true;
  try{
    if(!$("lookupConsent").checked)throw new Error("Confirm the URL disclosure first.");
    $("lookup").disabled=true;
    const checkedURL=$("lookupURL").value;
    const result=await send("reputation",{url:checkedURL,lookupOptIn:true});
    $("reputation").hidden=false;
    $("reputation").textContent=`Status: ${result.status}. ${(result.threat_types || []).join(", ")}\nThis is a URL reputation result, not a complete safety verdict. It did not change blocking rules.`;
    if(result.status==="listed"){
      listedDomain=new URL(checkedURL).hostname;
      $("blockDetected").textContent="Block destination domain: "+listedDomain;
      $("blockDetected").hidden=false;
    }
  }catch(error){$("status").textContent=error.message;}
  finally{$("lookup").disabled=false;}
};
$("blockDetected").onclick=async()=>{
  try{
    if(!listedDomain)return;
    // This explicit user action creates a domain rule, including subdomains.
    await send("save",{settings:{...current,blockedDomains:[...current.blockedDomains,listedDomain]}});
    await load();$("status").textContent="User domain rule applied. It includes subdomains and persists until removed in Settings.";
    $("blockDetected").hidden=true;
  }catch(error){$("status").textContent=error.message;}
};
load().catch(error=>$("status").textContent=error.message);
