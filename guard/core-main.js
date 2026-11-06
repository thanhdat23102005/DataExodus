/* Pure policy helpers, shared by the extension and dependency-free tests.
 * core-main.js is a byte-identical copy loaded into the MAIN world: Chrome
 * injects a given file only once per frame, so listing core.js in both
 * content_scripts entries left the second world without GuardCore.
 * tests/test_guard_manifest.py enforces that the two stay identical. */
(function (root) {
  "use strict";
  const STARTER = ["doubleclick.net", "googlesyndication.com", "googleadservices.com"];
  const DEFAULTS = {enabled:true, popupGuard:true, labMode:false, preventCollection:true, learnCollection:true,
    quarantineAds:true, blockedDomains:STARTER,
    allowSites:[], testEmail:"", apiToken:""};
  const LAB = [{domain:"127.0.0.2",category:"lab_collector"},{domain:"127.0.0.3",category:"lab_popup"}];
  // Ad-click redirectors: a top-level navigation matching one of these is a
  // click on an ad, routed to quarantine before the ad network is contacted.
  // RE2 syntax (DNR). Kept identical to protection/sandbox.py
  // AD_CLICK_PATTERNS; tests/test_guard_manifest.py checks.
  const AD_CLICK = {
    "Google Ads": "^https?://([a-z0-9-]+\\.)*(googleadservices\\.com|doubleclick\\.net|googlesyndication\\.com)/",
    "Google Search ad": "^https?://(www\\.)?google\\.[a-z.]+/aclk\\?",
    "Microsoft Ads": "^https?://(www\\.)?bing\\.com/aclick\\?",
    "Amazon Ads": "^https?://([a-z0-9-]+\\.)*amazon-adsystem\\.com/",
    "Taboola": "^https?://trc\\.taboola\\.com/",
    "Outbrain": "^https?://paid\\.outbrain\\.com/",
    "Criteo": "^https?://([a-z0-9-]+\\.)*criteo\\.(com|net)/",
    "Xandr": "^https?://([a-z0-9-]+\\.)*adnxs\\.com/",
  };
  const LAB_AD_CLICK = "^http://127\\.0\\.0\\.3(:[0-9]+)?/aclk";
  // Click-ID / campaign parameters, removed before a destination is opened.
  // Same list as protection/sandbox.py TRACKING_PARAMS.
  const TRACKING_PARAMS = new Set(["gclid","gclsrc","dclid","gbraid","wbraid","fbclid","msclkid","ttclid",
    "twclid","li_fat_id","mc_eid","_hsenc","_hsmi","yclid","igshid","epik","s_cid"]);
  // Two-label public suffixes that matter for this AU study; enough to tell
  // first from third party without shipping the Public Suffix List.
  const TWO_LABEL = new Set(["com.au","net.au","org.au","edu.au","gov.au","asn.au","id.au",
    "nsw.gov.au","vic.gov.au","qld.gov.au","wa.gov.au","sa.gov.au","tas.gov.au","act.gov.au","nt.gov.au",
    "co.uk","org.uk","ac.uk","gov.uk","co.nz","govt.nz","co.jp","com.br","com.sg","com.vn","co.in"]);
  // Rule id ranges. Learned session rules start at 40001; allow-once at 1000000.
  const NAV_RULE = 1001, AD_RULE = 1101, IDENTITY_RULE = 2001;
  function domain(value) {
    const raw = String(value || "").trim().toLowerCase();
    if (!raw || raw.length > 253 || /[\s/:@?#*]/.test(raw)) return "";
    try {
      const host = new URL("https://" + raw).hostname.replace(/\.$/, "");
      return host.split(".").every(p=>/^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$/.test(p)) ? host : "";
    } catch { return ""; }
  }
  const normalize = values => [...new Set((Array.isArray(values) ? values : [])
    .map(domain).filter(Boolean))].slice(0,500);
  const matches = (host, item) => host === item || host.endsWith("." + item);
  function config(raw={}) {
    return {...DEFAULTS, ...raw,
      enabled:raw.enabled !== false, popupGuard:raw.popupGuard !== false,
      preventCollection:raw.preventCollection !== false, learnCollection:raw.learnCollection !== false,
      quarantineAds:raw.quarantineAds !== false,
      labMode:raw.labMode === true,
      blockedDomains:normalize(raw.blockedDomains ?? STARTER), allowSites:normalize(raw.allowSites),
      testEmail:String(raw.testEmail || "").trim().slice(0,254), apiToken:String(raw.apiToken || "").slice(0,200)};
  }
  function publicConfig(raw) {
    const s=config(raw);
    return {enabled:s.enabled,popupGuard:s.popupGuard,labMode:s.labMode,quarantineAds:s.quarantineAds,
      blockedDomains:s.blockedDomains,allowSites:s.allowSites};
  }
  function host(url) {try{return new URL(url).hostname.toLowerCase();}catch{return "";}}
  function allowed(url,s) {return s.allowSites.some(d=>matches(host(url),d));}
  function targets(s) {
    return [...s.blockedDomains.map(d=>({domain:d,category:STARTER.includes(d)?"tracker_rule":"user_rule"})),
      ...(s.labMode ? LAB : [])];
  }
  function blocked(url,s) {
    const h=host(url);
    return targets(s).some(t=>matches(h,t.domain));
  }
  function site(hostname) {
    const h=String(hostname || "").toLowerCase().replace(/\.$/,"");
    if(/^[0-9.]+$/.test(h) || h.includes(":"))return h;  // IP literal: the address is the site
    const parts=h.split(".");
    for(const n of [3,2])
      if(parts.length>n && TWO_LABEL.has(parts.slice(-n).join(".")))return parts.slice(-(n+1)).join(".");
    return parts.slice(-2).join(".");
  }
  /* true / false, or null when there is no initiating page (typed URL,
   * bookmark, extension). */
  function thirdParty(url,initiator) {
    const target=host(url), source=host(initiator || "");
    if(!target || !source)return null;
    return site(target)!==site(source);
  }
  function adClick(url,s) {
    const value=String(url || "");
    if(s && s.labMode && new RegExp(LAB_AD_CLICK).test(value))return "Lab ad";
    return Object.keys(AD_CLICK).find(name=>new RegExp(AD_CLICK[name],"i").test(value)) || null;
  }
  /* Signals for a top-level navigation caught by the combined NAV_RULE. */
  function navigationSignals(url,s) {
    const h=host(url), t=targets(s).find(t=>matches(h,t.domain));
    return [t && t.category==="tracker_rule"?"tracker_rule":"user_rule"];
  }
  /* DNR rules. `quarantineURL` is chrome.runtime.getURL("quarantine.html"):
   * with it, a quarantined navigation carries its URL in the fragment of the
   * extension page (never sent over the network) so the user can preview it
   * in the sandbox; without it the page opens with no destination details.
   * `category`/`signals` are stripped before install. */
  function rules(raw,tokens=[],quarantineURL="") {
    const s=config(raw);
    if(!s.enabled)return [];
    const out=[], to=(reason,extra="")=>quarantineURL?
      {type:"redirect",redirect:{regexSubstitution:`${quarantineURL}?reason=${reason}${extra}`}}:
      {type:"redirect",redirect:{extensionPath:"/quarantine.html"}};
    const list=targets(s);
    list.forEach((t,i)=>out.push({id:i+1,priority:10,action:{type:"block"},
      condition:{requestDomains:[t.domain],excludedResourceTypes:["main_frame"],excludedInitiatorDomains:s.allowSites},
      category:t.category,signals:[t.category==="tracker_rule"?"tracker_rule":"user_rule"]}));
    // One rule covers top-level navigation to every listed domain (Chrome
    // rejects an empty requestDomains list).
    if(list.length)out.push({id:NAV_RULE,priority:10,action:s.quarantineAds?to("network_rule","#\\0"):{type:"block"},
      condition:{regexFilter:"^https?://.*",requestDomains:list.map(t=>t.domain),resourceTypes:["main_frame"],
        excludedInitiatorDomains:s.allowSites},category:"navigation_rule",signals:["user_rule"]});
    if(s.quarantineAds) {
      const ads=[...Object.entries(AD_CLICK),...(s.labMode?[["Lab ad",LAB_AD_CLICK]]:[])];
      ads.forEach(([name,regex],i)=>out.push({id:AD_RULE+i,priority:15,
        action:to("ad_click","&network="+encodeURIComponent(name)+"#\\0"),
        condition:{regexFilter:regex+".*",resourceTypes:["main_frame"],excludedInitiatorDomains:s.allowSites},
        category:"ad_click",signals:["ad_click"]}));
    }
    if(s.preventCollection) {
      const patterns=new Map();
      for(const token of tokens)for(const value of [token.value,encodeURIComponent(token.value)]) {
        if(value && /^[\x20-\x7e]+$/.test(value))patterns.set(value,token.kind);
      }
      let i=0;
      for(const [value,kind] of patterns) {
        // A plain substring filter: a case-insensitive SHA-512 regex exceeds
        // Chrome's 2 KB regex memory limit and the whole rule set is refused.
        // Only an email containing urlFilter's own operators needs a regex.
        const match=/[*|^]/.test(value)?{regexFilter:value.replace(/[.*+?^${}()|[\]\\]/g,"\\$&")}:{urlFilter:value};
        const common={...match,domainType:"thirdParty",excludedInitiatorDomains:s.allowSites};
        out.push({id:IDENTITY_RULE+i*2,priority:30,action:{type:"block"},
          condition:{...common,excludedResourceTypes:["main_frame"]},category:"identity_url",signals:[kind]});
        // The navigation's URL holds the identifier, so it is not carried
        // into the quarantine page.
        out.push({id:IDENTITY_RULE+i*2+1,priority:30,
          action:{type:"redirect",redirect:{extensionPath:quarantineURL?"/quarantine.html?reason=identity_url":"/quarantine.html"}},
          condition:{...common,resourceTypes:["main_frame"]},category:"identity_url",signals:[kind]});
        i++;
      }
    }
    return out;
  }
  function learnedRules(raw,entries=[]) {
    const s=config(raw);
    if(!s.enabled || !s.preventCollection || !s.learnCollection)return [];
    return entries.slice(0,100).map((entry,i)=>({id:40001+i,priority:20,action:{type:"block"},
      condition:{requestDomains:[domain(entry.target)],initiatorDomains:[domain(entry.source)],domainType:"thirdParty",
        excludedResourceTypes:["main_frame"],excludedInitiatorDomains:s.allowSites},category:"learned_collection",
      signals:entry.signals.filter(s=>["identifier_raw","identifier_hash"].includes(s))}));
  }
  function destination(value,base) {
    if(typeof value!=="string" || value.length>8192 || /[\x00-\x1f]/.test(value))return null;
    try {
      const url=new URL(value,base);
      if(!["http:","https:"].includes(url.protocol) || url.username || url.password)return null;
      // Shown to the user: the origin and counts, never paths, query keys/values or fragments.
      return {origin:url.origin,domain:url.hostname,path_segments:url.pathname.split('/').filter(Boolean).length,
        query_fields:[...url.searchParams].length,has_fragment:!!url.hash};
    } catch {return null;}
  }
  function cleanURL(value) {
    try {
      const url=new URL(value);
      for(const key of [...url.searchParams.keys()])
        if(TRACKING_PARAMS.has(key.toLowerCase()) || key.toLowerCase().startsWith("utm_"))url.searchParams.delete(key);
      url.hash="";
      return url.href;
    } catch {return null;}
  }
  /* Many ad-click links carry the advertiser's page in a parameter. Opening
   * that directly skips the ad network's click log entirely. */
  function adDestination(value) {
    let url;try{url=new URL(value);}catch{return null;}
    for(const key of ["adurl","url","dest","destination"]) {
      const target=url.searchParams.get(key);
      if(target && destination(target) && host(target)!==url.hostname)return cleanURL(target);
    }
    return null;
  }
  function shouldBlockPopup(target,source,s,linkedDestination="") {
    if(!s.enabled || !s.popupGuard || allowed(source,s))return false;
    let dest;
    try {dest=new URL(target || "about:blank",source);} catch {return true;}
    if(!["http:","https:"].includes(dest.protocol))return false;
    if(blocked(dest.href,s))return true;
    if(dest.origin===new URL(source).origin)return false;
    // A direct trusted anchor preserves ordinary external documentation links.
    return dest.href !== linkedDestination;
  }
  function transparentOverlay({opacity,width,height,zIndex,external}) {
    return external && opacity <= 0.1 && width >= 120 && height >= 50 && zIndex >= 100;
  }
  /* A new tab a page opened (seen by Chrome, however the page opened it) is
   * unsolicited when it leaves the page's site and no link the user clicked,
   * or right-clicked for "Open link in new tab", leads to that site. */
  function unsolicitedPopup(target,source,s,intents=[],now=Date.now()) {
    if(!s.enabled || !s.popupGuard || allowed(source,s) || !destination(target) || !destination(source))return false;
    const to=site(host(target));
    if(to===site(host(source)))return false;
    return !intents.some(i=>now-i.time<i.ttl && (i.href===target || site(host(i.href))===to));
  }
  /* X-Ray: classify one element from its measured facts. Heuristic labels
   * for a visual inspection, not evidence that anything was collected. */
  function xrayKind({tag,width,height,hidden,external,overlay}) {
    if(overlay)return "overlay";
    if(!external)return null;
    const tiny=width<=3 && height<=3;
    if(tag==="img" && (tiny || hidden))return "pixel";
    if(tag==="iframe" && (tiny || hidden))return "hidden_frame";
    return null;
  }
  function detect(text,tokens) {
    let value=String(text || "").slice(0,131072);
    try{value+="\n"+decodeURIComponent(value.replace(/\+/g,"%20"));}catch{}
    const low=value.toLowerCase();
    return [...new Set(tokens.filter(t=>t.value && low.includes(t.value)).map(t=>t.kind))];
  }
  async function identityTokens(email,cryptoAPI) {
    if(!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email))return [];
    const variants=[...new Set([email,email.toLowerCase()])];
    const tokens=[];
    for(const variant of variants) {
      tokens.push({value:variant.toLowerCase(),kind:"identifier_raw"});
      for(const algorithm of ["SHA-1","SHA-256","SHA-512"]) {
        const bytes=await cryptoAPI.subtle.digest(algorithm,new TextEncoder().encode(variant));
        tokens.push({value:Array.from(new Uint8Array(bytes),v=>v.toString(16).padStart(2,"0")).join(""),kind:"identifier_hash"});
      }
    }
    return tokens;
  }
  function signalSummary(events) {
    const signals=new Set(["tracker_rule","popup_without_link","transparent_overlay","identifier_raw","identifier_hash","known_threat","user_rule","ad_click"]);
    return events.slice(0,20).map(e=>({
      signals:(e.signals || []).filter(s=>signals.has(s)).slice(0,8),
      resource_type:["navigation","script","image","request","popup","other"].includes(e.resource_type)?e.resource_type:"other",
      enforcement:["network_blocked","interaction_prevented","observed_only","navigation_quarantined"].includes(e.enforcement)?e.enforcement:"observed_only",
      third_party:typeof e.third_party === "boolean"?e.third_party:null,
    }));
  }
  root.GuardCore={DEFAULTS,AD_CLICK,NAV_RULE,AD_RULE,IDENTITY_RULE,config,publicConfig,domain,host,matches,allowed,blocked,
    site,thirdParty,adClick,navigationSignals,rules,learnedRules,destination,cleanURL,adDestination,
    shouldBlockPopup,transparentOverlay,unsolicitedPopup,xrayKind,detect,identityTokens,signalSummary};
  if(typeof module!=="undefined")module.exports=root.GuardCore;
})(typeof globalThis!=="undefined"?globalThis:this);
