/* Chrome DNR enforces network policy. MAIN-world reports never change it. */
importScripts("core.js");
const C=GuardCore, API="http://127.0.0.1:8010";
let settings=C.config(),tokens=[],events=[],learned=[],quarantines={},startupError="",serial=Promise.resolve(),generation=0;
const pageRate=new Map(),quarantineRate=new Map(),identityNavigations=new Map(),linkIntents=new Map();
const quarantineURL=()=>chrome.runtime.getURL("quarantine.html");
const wire=rules=>rules.map(({category,signals,...rule})=>rule);
const ALLOW_ONCE=1000000;
const ready=(async()=>{
  await chrome.storage.local.setAccessLevel({accessLevel:"TRUSTED_CONTEXTS"});
  await chrome.storage.session.setAccessLevel({accessLevel:"TRUSTED_CONTEXTS"});
  const stored=await chrome.storage.local.get(["settings","events"]);
  const session=await chrome.storage.session.get(["learned","quarantines"]);
  settings=C.config(stored.settings);events=(stored.events || []).slice(0,200);
  learned=(session.learned || []).filter(e=>C.domain(e.source) && C.domain(e.target) && Array.isArray(e.signals)).slice(0,100);
  quarantines=session.quarantines || {};
  tokens=await C.identityTokens(settings.testEmail,crypto);
  if(!tokens.length || !settings.enabled || !settings.preventCollection || !settings.learnCollection)learned=[];
  try{await installRules(settings,tokens,learned);await chrome.storage.session.set({learned});}
  catch{startupError="Rule installation failed. Open settings and retry.";}
})();
function exclusive(fn){const next=serial.then(fn,fn);serial=next.catch(()=>{});return next;}
async function installRules(next,nextTokens,nextLearned){
  const dnr=chrome.declarativeNetRequest;
  const old=await dnr.getDynamicRules(),oldSession=await dnr.getSessionRules();
  const dynamic=C.rules(next,nextTokens,quarantineURL()),session=C.learnedRules(next,nextLearned);
  for(const rule of dynamic.filter(r=>r.condition.regexFilter)){
    const supported=await dnr.isRegexSupported({regex:rule.condition.regexFilter,isCaseSensitive:false});
    if(!supported.isSupported)throw new Error("A URL rule is unsupported by this browser.");
  }
  let changed=false;
  try{
    await dnr.updateDynamicRules({removeRuleIds:old.map(r=>r.id),addRules:wire(dynamic)});changed=true;
    await dnr.updateSessionRules({removeRuleIds:oldSession.map(r=>r.id),addRules:wire(session)});
  }catch(error){
    if(changed)try{
      await dnr.updateDynamicRules({removeRuleIds:dynamic.map(r=>r.id),addRules:old});
      await dnr.updateSessionRules({removeRuleIds:session.map(r=>r.id),addRules:oldSession});
    }catch{startupError="Rule update and rollback failed. Reload the extension and verify its rules.";}
    throw error;
  }
}
async function record(event){await exclusive(async()=>{
  // No URLs, paths, headers, cookies, body values or matched identity digests.
  events=[{...event,time:new Date().toISOString()},...events].slice(0,200);
  await chrome.storage.local.set({events});
});}
function resource(type){return type==="main_frame"?"navigation":["image","script"].includes(type)?type:"request";}
/* Quarantine records live in chrome.storage.session: memory only, readable
 * by extension pages only, gone when the tab or browser closes. The full URL
 * is kept so the user can preview it in the sandbox or open it anyway; it is
 * never shown in evidence, exported, or sent anywhere without a click. */
async function saveQuarantine(entry){
  await exclusive(async()=>{
    quarantines[entry.id]=entry;
    const rows=Object.values(quarantines).sort((a,b)=>b.created_at.localeCompare(a.created_at)).slice(0,50);
    quarantines=Object.fromEntries(rows.map(e=>[e.id,e]));
    await chrome.storage.session.set({quarantines});
  });
}
function newQuarantine(tabId,url,reason,extra={}){
  return {id:crypto.randomUUID(),tab_id:tabId,destination:url?C.destination(url):null,url:url || null,reason,
    network:null,verified:false,source_origin:"",created_at:new Date().toISOString(),preview:null,...extra};
}
chrome.declarativeNetRequest.onRuleMatchedDebug.addListener(async info=>{
  await ready;
  const rule=[...C.rules(settings,tokens,quarantineURL()),...C.learnedRules(settings,learned)].find(r=>r.id===info.rule.ruleId);
  if(!rule)return;  // allow-once rules are the user's own choice, not evidence
  const routed=rule.action.type==="redirect";
  if(rule.category==="identity_url" && info.request.type==="main_frame")identityNavigations.set(info.request.tabId,Date.now());
  await record({kind:"network_rule",domain:C.host(info.request.url),
    signals:rule.id===C.NAV_RULE?C.navigationSignals(info.request.url,settings):rule.signals,
    resource_type:resource(info.request.type),enforcement:routed?"navigation_quarantined":"network_blocked",
    evidence_quality:"chrome_rule_match",tab_id:info.request.tabId});
});
async function learnDestination(d,found,expectedGeneration){
  if(!settings.enabled || !settings.preventCollection || !settings.learnCollection)return;
  const source=C.host(d.initiator),target=C.host(d.url);
  if(!C.domain(source) || !C.domain(target) || source===target || C.allowed(d.initiator,settings))return;
  await exclusive(async()=>{
    if(generation!==expectedGeneration || !settings.enabled || !settings.preventCollection || !settings.learnCollection || !tokens.length)return;
    if(learned.some(e=>e.source===source && e.target===target) || learned.length>=100)return;
    const next=[...learned,{source,target,signals:found}];
    const rule=C.learnedRules(settings,next).at(-1);
    await chrome.declarativeNetRequest.updateSessionRules({addRules:wire([rule])});
    learned=next;await chrome.storage.session.set({learned});
  });
}
chrome.webRequest.onBeforeRequest.addListener(async d=>{
  await ready;
  if(!settings.enabled || !tokens.length || d.tabId<0 || d.initiator?.startsWith("chrome-extension://"))return;
  let body="";
  if(d.requestBody?.raw)body=d.requestBody.raw.map(p=>p.bytes?new TextDecoder().decode(p.bytes):"").join("");
  else if(d.requestBody?.formData)body=JSON.stringify(d.requestBody.formData);
  const found=C.detect(d.url+"\n"+body,tokens),observedGeneration=generation;
  if(!found.length)return;
  const third=C.thirdParty(d.url,d.initiator);
  await record({kind:"identity_match",domain:C.host(d.url),signals:found,resource_type:resource(d.type),
    enforcement:"observed_only",evidence_quality:"local_identifier_match",...(third===null?{}:{third_party:third}),tab_id:d.tabId});
  try{await learnDestination(d,found,observedGeneration);}catch{startupError="A collection signal was observed, but its follow-up rule could not be installed.";}
}, {urls:["http://*/*","https://*/*"]},["requestBody"]);
async function callAPI(path,payload,timeout=22000){
  if(!settings.apiToken)throw new Error("Configure the local service token in Settings first.");
  const response=await fetch(API+path,{method:"POST",headers:{"Content-Type":"application/json","Authorization":"Bearer "+settings.apiToken},
    body:JSON.stringify(payload),signal:AbortSignal.timeout(timeout)});
  if(!response.ok)throw new Error("Local service returned HTTP "+response.status+". Check token and call budget.");
  return response.json();
}
function ownUI(sender){
  const url=sender.url?.split(/[?#]/)[0];
  return (sender.frameId==null || sender.frameId===0) &&
    [chrome.runtime.getURL("options.html"),chrome.runtime.getURL("popup.html")].includes(url);
}
function quarantineUI(sender){
  return sender.tab && sender.frameId===0 && sender.url?.split(/[?#]/)[0]===quarantineURL();
}
async function openQuarantine(message,sender){
  if(!sender.tab || !settings.enabled || !settings.popupGuard || !settings.quarantineAds ||
    message.gesture!==true || C.allowed(sender.url || "",settings))return {opened:false};
  if(!["popup_without_link","transparent_overlay"].includes(message.signal))return {opened:false};
  const destination=C.destination(message.url,sender.url);
  if(!destination)return {opened:false};
  const now=Date.now();
  if(now-(quarantineRate.get(sender.tab.id) || 0)<1500)return {opened:false};
  quarantineRate.set(sender.tab.id,now);
  const url=new URL(message.url,sender.url).href,id=crypto.randomUUID();
  const tab=await chrome.tabs.create({url:quarantineURL()+"#"+id,active:true,openerTabId:sender.tab.id});
  await saveQuarantine(newQuarantine(tab.id,url,message.signal,{id,network:C.adClick(url,settings),
    source_origin:C.destination(sender.url)?.origin || ""}));
  return {opened:true};
}
async function adoptQuarantine(message,sender){
  // A DNR redirect brought this tab here with the URL in the fragment. The
  // page is web accessible, so any site can open it with any fragment: the
  // reason is re-derived from current policy, never taken from the page.
  let url=null,reason="opened_directly",network=null,verified=false;
  if(message.reason==="identity_url"){
    reason="identity_url";verified=Date.now()-(identityNavigations.get(sender.tab.id) || 0)<15000;
  }else if(typeof message.url==="string" && C.destination(message.url)){
    url=new URL(message.url).href;
    const ad=C.adClick(url,settings);
    if(settings.enabled && settings.quarantineAds && ad){reason="ad_click";network=ad;verified=true;}
    else if(settings.enabled && C.blocked(url,settings)){reason="network_rule";verified=true;}
  }
  const entry=newQuarantine(sender.tab.id,url,reason,{network,verified});
  await saveQuarantine(entry);
  return {id:entry.id};
}
function quarantineEntry(sender,id){
  return Object.values(quarantines).filter(e=>e.tab_id===sender.tab.id && (!id || e.id===id))
    .sort((a,b)=>b.created_at.localeCompare(a.created_at))[0] || null;
}
function quarantineView(entry){
  if(!entry)return null;
  const {url,preview,...rest}=entry;
  return {...rest,has_url:!!url,direct_available:!!(url && C.adDestination(url)),
    clean_available:!!preview?.clean_url,sandbox_configured:!!settings.apiToken};
}
async function allowOnce(tabId,url){
  // "Open anyway": a session rule lets this one tab past Guard's navigation
  // rules; removed once that page has loaded.
  const id=ALLOW_ONCE+tabId;
  await chrome.declarativeNetRequest.updateSessionRules({removeRuleIds:[id],addRules:[{id,priority:100,
    action:{type:"allow"},condition:{tabIds:[tabId],resourceTypes:["main_frame"]}}]});
  const done=(updated,info)=>{
    if(updated!==tabId || info.status!=="complete")return;
    chrome.declarativeNetRequest.updateSessionRules({removeRuleIds:[id]}).catch(()=>{});
    chrome.tabs.onUpdated.removeListener(done);
  };
  chrome.tabs.onUpdated.addListener(done);
  await chrome.tabs.update(tabId,{url});
}
async function handleQuarantine(message,sender){
  if(!quarantineUI(sender))throw new Error("Quarantine top-level page required");
  await serial;
  if(message.type==="close_quarantine"){await chrome.tabs.remove(sender.tab.id);return {ok:true};}
  if(message.type==="quarantine_adopt")return adoptQuarantine(message,sender);
  const entry=quarantineEntry(sender,message.id);
  if(message.type==="quarantine_state")return quarantineView(entry);
  if(!entry || !entry.url)throw new Error("No destination is held in this tab.");
  if(message.type==="sandbox_preview"){
    // The only URL sent to the sandbox service is the one Guard holds for
    // this tab; the page cannot substitute another.
    const result=await callAPI("/sandbox/preview",{url:entry.url},45000);
    await exclusive(async()=>{
      if(!quarantines[entry.id])return;
      quarantines[entry.id].preview={clean_url:result.ok && C.destination(result.clean_url || "")?result.clean_url:null};
      await chrome.storage.session.set({quarantines});
    });
    return result;
  }
  if(message.type==="open_destination"){
    const url={clean:entry.preview?.clean_url,direct:C.adDestination(entry.url),original:entry.url}[message.target];
    if(!url || !C.destination(url))throw new Error("That destination is not available.");
    await allowOnce(sender.tab.id,url);
    return {ok:true};
  }
  throw new Error("Unknown operation");
}
async function handle(message,sender){
  await ready;
  if(sender.id!==chrome.runtime.id)throw new Error("Unknown sender");
  if(message.type==="public_config")return C.publicConfig(settings);
  if(["quarantine_adopt","quarantine_state","close_quarantine","sandbox_preview","open_destination"].includes(message.type))
    return handleQuarantine(message,sender);
  if(message.type==="quarantine")return openQuarantine(message,sender);
  if(message.type==="link_intent"){
    // The link a user just clicked, so a new tab it opens is not taken for a
    // pop-under. Held in memory for seconds per tab, never stored.
    if(!sender.tab || typeof message.href!=="string" || !C.destination(message.href))return {ok:false};
    const now=Date.now(),list=(linkIntents.get(sender.tab.id) || []).filter(i=>now-i.time<i.ttl).slice(-9);
    linkIntents.set(sender.tab.id,[...list,{href:message.href,time:now,ttl:message.menu===true?60000:3000}]);
    return {ok:true};
  }
  if(message.type==="page_event"){
    if(!sender.tab || !settings.enabled || C.allowed(sender.url || "",settings))return {ok:false};
    const now=Date.now(),prev=pageRate.get(sender.tab.id) || {start:now,count:0};
    if(now-prev.start>60000){prev.start=now;prev.count=0;}
    if(++prev.count>30)return {ok:false};pageRate.set(sender.tab.id,prev);
    const overlay=message.signal==="transparent_overlay";
    if(!overlay && message.signal!=="popup_without_link")return {ok:false};
    await record({kind:overlay?"overlay":"popup",domain:C.domain(message.domain),signals:[message.signal],
      resource_type:"popup",enforcement:"interaction_prevented",evidence_quality:"page_report_unverified",tab_id:sender.tab.id});
    return {ok:true};
  }
  if(!ownUI(sender))throw new Error("This operation requires extension UI");
  if(message.type==="state")return {settings,events,startupError,learnedRulesCount:learned.length};
  if(message.type==="clear"){await exclusive(async()=>{events=[];await chrome.storage.local.set({events});});return {ok:true};}
  if(message.type==="reset_learning"){await exclusive(async()=>{
    const old=await chrome.declarativeNetRequest.getSessionRules();
    await chrome.declarativeNetRequest.updateSessionRules({removeRuleIds:old.map(r=>r.id),addRules:[]});
    learned=[];generation++;await chrome.storage.session.set({learned});
  });return {ok:true};}
  if(message.type==="save")return exclusive(async()=>{
    const next=C.config(message.settings),nextTokens=await C.identityTokens(next.testEmail,crypto);
    await installRules(next,nextTokens,[]);
    settings=next;tokens=nextTokens;learned=[];startupError="";generation++;
    await chrome.storage.local.set({settings});await chrome.storage.session.set({learned});
    const tabs=await chrome.tabs.query({});
    await Promise.allSettled(tabs.filter(t=>t.id).map(t=>chrome.tabs.sendMessage(t.id,{type:"policy_changed"})));
    return {ok:true};
  });
  if(message.type==="analyze"){
    if(!events.length)throw new Error("No local events to explain yet.");
    return callAPI("/analyze",{evidence:C.aiEvidence(events),cloud_opt_in:settings.cloudOptIn,language:"vi"});
  }
  if(message.type==="reputation"){
    if(message.lookupOptIn!==true)throw new Error("Confirm the URL lookup first.");
    const url=new URL(message.url);
    if(!["http:","https:"].includes(url.protocol) || url.username || url.password)throw new Error("Invalid URL");
    url.hash="";return callAPI("/reputation",{url:url.href,lookup_opt_in:true});
  }
  throw new Error("Unknown operation");
}
chrome.runtime.onMessage.addListener((message,sender,respond)=>{
  handle(message,sender).then(data=>respond({ok:true,data})).catch(error=>respond({ok:false,error:error.message}));return true;
});
/* Pop-unders. Chrome reports every tab a page opens, whether by window.open
 * from any frame, a scripted target=_blank link or a form, so a page cannot
 * route around this the way it can around the MAIN-world window.open hook. */
function firstURL(tabId){
  // A pop-under often opens about:blank and sets its address afterwards.
  return new Promise(resolve=>{
    const seen=e=>{if(e.tabId===tabId && e.frameId===0 && C.destination(e.url))done(e.url);};
    const done=url=>{clearTimeout(timer);chrome.webNavigation.onBeforeNavigate.removeListener(seen);resolve(url);};
    const timer=setTimeout(()=>done(""),4000);
    chrome.webNavigation.onBeforeNavigate.addListener(seen);
  });
}
async function closeUnsolicited(d,target){
  await ready;
  if(!settings.enabled || !settings.popupGuard)return;
  const source=(await chrome.tabs.get(d.sourceTabId).catch(()=>null))?.url || "";
  const url=await target;
  await new Promise(r=>setTimeout(r,250));  // the click's link_intent message may still be in flight
  if(!C.unsolicitedPopup(url,source,settings,linkIntents.get(d.sourceTabId),Date.now()))return;
  try{await chrome.tabs.remove(d.tabId);}catch{return;}
  await record({kind:"popup",domain:C.host(url),signals:["popup_without_link"],resource_type:"popup",
    enforcement:"interaction_prevented",evidence_quality:"chrome_tab_observed",tab_id:d.sourceTabId});
  chrome.tabs.sendMessage(d.sourceTabId,{type:"popup_closed"},{frameId:0}).catch(()=>{});
}
chrome.webNavigation.onCreatedNavigationTarget.addListener(d=>{
  closeUnsolicited(d,C.destination(d.url)?Promise.resolve(d.url):firstURL(d.tabId)).catch(()=>{});
});
chrome.tabs.onRemoved.addListener(id=>{
  pageRate.delete(id);quarantineRate.delete(id);identityNavigations.delete(id);linkIntents.delete(id);
  chrome.declarativeNetRequest.updateSessionRules({removeRuleIds:[ALLOW_ONCE+id]}).catch(()=>{});
  exclusive(async()=>{quarantines=Object.fromEntries(Object.entries(quarantines).filter(([,e])=>e.tab_id!==id));
    await chrome.storage.session.set({quarantines});}).catch(()=>{});
});
