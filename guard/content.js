/* Isolated-world bridge. Page reports are untrusted and never install rules. */
(()=>{
  let policy=GuardCore.config({enabled:false});
  function notify(){window.dispatchEvent(new CustomEvent("dataexodus:policy",{detail:JSON.stringify(GuardCore.publicConfig(policy))}));}
  async function refresh(){
    try{const r=await chrome.runtime.sendMessage({type:"public_config"});if(r.ok){policy=GuardCore.config(r.data);notify();}}catch{}
  }
  window.addEventListener("dataexodus:ready",notify);
  chrome.runtime.onMessage.addListener(m=>{if(m.type==="policy_changed")refresh();else if(m.type==="popup_closed")toast();});
  let lastMessage=0,gestureUntil=0,gestureUsed=false;
  function toast(){
    if(Date.now()-lastMessage<1500)return;lastMessage=Date.now();
    const host=document.createElement("div");
    host.style.cssText="position:fixed;bottom:20px;right:20px;z-index:2147483647";
    const shadow=host.attachShadow({mode:"closed"});
    const box=document.createElement("div");box.textContent="DataExodus: blocked a suspicious popup / overlay. Review or allow this site in extension Settings.";
    box.style.cssText="font:14px/1.5 system-ui;background:#112e37;color:#fff;padding:16px;border-radius:12px;max-width:310px;box-shadow:0 8px 30px #0005";
    shadow.append(box);(document.body || document.documentElement).append(host);
    setTimeout(()=>host.remove(),7000);
  }
  function intent(href,menu){
    if(GuardCore.destination(href))chrome.runtime.sendMessage({type:"link_intent",href,menu}).catch(()=>{});
  }
  function report(signal,domain,url){
    chrome.runtime.sendMessage({type:"page_event",signal,domain}).catch(()=>{});
    // A hidden overlay sat over something the user meant to click, so the
    // destination is held for review. A popup nobody asked for is just blocked.
    if(signal==="transparent_overlay" && policy.quarantineAds && Date.now()<gestureUntil && !gestureUsed && GuardCore.destination(url,location.href)){
      gestureUsed=true;
      chrome.runtime.sendMessage({type:"quarantine",signal,url,gesture:true}).catch(()=>{});
    }
    toast();
  }
  window.addEventListener("dataexodus:event",e=>{
    if(!policy.enabled || !policy.popupGuard)return;
    try{const m=JSON.parse(e.detail);if(m.signal==="popup_without_link")report(m.signal,GuardCore.domain(m.domain),m.url);}catch{}
  });
  function inspectClick(e){
    if(!e.isTrusted)return;
    gestureUntil=Date.now()+700;gestureUsed=false;
    if(!policy.enabled || !policy.popupGuard || GuardCore.allowed(location.href,policy))return;
    const a=e.target.closest?.("a[href]");if(!a)return;
    let dest;try{dest=new URL(a.href,location.href);}catch{return;}
    if(!["http:","https:"].includes(dest.protocol))return;
    const css=getComputedStyle(a),rect=a.getBoundingClientRect();
    const suspicious=GuardCore.transparentOverlay({opacity:parseFloat(css.opacity),width:rect.width,height:rect.height,
      zIndex:parseInt(css.zIndex)||0,external:dest.origin!==location.origin});
    // A visible link to a listed domain or ad redirector is left to Chrome's
    // navigation rule, which routes it to quarantine with browser-verified
    // evidence. A hidden overlay is stopped here either way.
    const routedByChrome=policy.quarantineAds;
    if(suspicious || (GuardCore.blocked(dest.href,policy) && !routedByChrome)) {
      e.preventDefault();e.stopImmediatePropagation();
      report(suspicious?"transparent_overlay":"popup_without_link",dest.hostname,dest.href);
    }else intent(dest.href,false);
  }
  document.addEventListener("click",inspectClick,true);
  document.addEventListener("auxclick",inspectClick,true);
  document.addEventListener("contextmenu",e=>{
    const a=e.isTrusted && e.target.closest?.("a[href]");if(a)intent(a.href,true);
  },true);
  document.addEventListener("submit",e=>{if(e.isTrusted && e.target.action)intent(e.target.action,false);},true);
  refresh();
})();
