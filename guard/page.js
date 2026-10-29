/* Best-effort MAIN-world popup guard. The page can tamper with this hook.
 * Only Chrome DNR is a network enforcement boundary. No secrets enter MAIN.
 */
(()=>{
  "use strict";
  let policy=GuardCore.config({enabled:false}), linked="", linkTime=0;
  const originalOpen=window.open;
  window.addEventListener("dataexodus:policy",e=>{
    try{policy=GuardCore.config(JSON.parse(e.detail));}catch{}
  });
  document.addEventListener("click",e=>{
    if(!e.isTrusted)return;
    const anchor=e.target.closest?.("a[href]");
    linked=anchor?.href || "";linkTime=Date.now();
  },true);
  window.open=function(url,target,features){
    const linkedNow=Date.now()-linkTime<1000?linked:"";
    if(GuardCore.shouldBlockPopup(String(url ?? ""),location.href,policy,linkedNow)) {
      let domain="";try{domain=new URL(String(url),location.href).hostname;}catch{}
      window.dispatchEvent(new CustomEvent("dataexodus:event",{detail:JSON.stringify({
        signal:"popup_without_link",domain,url:String(url ?? "").slice(0,8192)})}));
      return null;
    }
    return originalOpen.call(window,url,target,features);
  };
  window.dispatchEvent(new CustomEvent("dataexodus:ready"));
})();
