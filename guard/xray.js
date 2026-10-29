/* X-Ray: when the Guard popup asks, outline third-party tracking pixels,
 * hidden frames and transparent link overlays on this page. A heuristic,
 * visual explanation of what the page contains, not evidence that anything
 * was sent. Isolated world and a closed shadow root: the page cannot read or
 * restyle the overlay. Top document only. */
(()=>{
  if(window.top!==window)return;
  const C=GuardCore;
  let layer=null;
  const LABELS={pixel:"PIXEL",hidden_frame:"HIDDEN FRAME",overlay:"INVISIBLE LINK"};
  function thirdPartyHost(value){
    try{
      const url=new URL(value,location.href);
      if(!["http:","https:"].includes(url.protocol))return "";
      return C.site(url.hostname)!==C.site(location.hostname)?url.hostname:"";
    }catch{return "";}
  }
  function scan(){
    const items=[],scripts=new Set();
    for(const el of document.querySelectorAll("img[src],iframe[src],a[href]")){
      const tag=el.tagName.toLowerCase(),host=thirdPartyHost(tag==="a"?el.href:el.src);
      if(!host)continue;
      const css=getComputedStyle(el),rect=el.getBoundingClientRect();
      const hidden=css.display==="none" || css.visibility==="hidden" || parseFloat(css.opacity)<0.05;
      const overlay=tag==="a" && C.transparentOverlay({opacity:parseFloat(css.opacity),width:rect.width,
        height:rect.height,zIndex:parseInt(css.zIndex)||0,external:true});
      const kind=C.xrayKind({tag,width:rect.width,height:rect.height,hidden,external:true,overlay});
      if(kind)items.push({kind,host,rect});
    }
    for(const s of document.querySelectorAll("script[src]")){const host=thirdPartyHost(s.src);if(host)scripts.add(host);}
    return {items,scripts:[...scripts]};
  }
  function draw({items,scripts}){
    layer=document.createElement("div");
    layer.style.cssText="position:absolute;left:0;top:0;width:0;height:0;z-index:2147483646;pointer-events:none";
    const shadow=layer.attachShadow({mode:"closed"}),style=document.createElement("style");
    style.textContent=".box{position:absolute;border:2px solid;border-radius:4px;box-sizing:border-box}"+
      ".box span{position:absolute;left:-2px;top:-19px;white-space:nowrap;color:#fff;padding:1px 6px;border-radius:3px;font:600 11px/1.4 system-ui}"+
      ".pixel{border-color:#d92d20}.pixel span{background:#d92d20}.hidden_frame{border-color:#b54708}.hidden_frame span{background:#b54708}"+
      ".overlay{border-color:#7a5af8;background:#7a5af822}.overlay span{background:#7a5af8}"+
      ".panel{position:fixed;right:16px;top:16px;max-width:340px;background:#102a30;color:#fff;padding:14px 16px;border-radius:12px;"+
      "font:13px/1.5 system-ui;box-shadow:0 8px 30px #0006}.panel b{font-size:14px}.panel small{color:#b8d0cc;display:block;margin-top:6px}";
    shadow.append(style);
    for(const item of items){
      if(!item.rect.width && !item.rect.height)continue;  // display:none: listed in the panel only
      const box=document.createElement("div"),label=document.createElement("span");
      box.className="box "+item.kind;
      box.style.cssText=`left:${item.rect.left+scrollX-2}px;top:${item.rect.top+scrollY-2}px;`+
        `width:${Math.max(item.rect.width+4,18)}px;height:${Math.max(item.rect.height+4,18)}px`;
      label.textContent=LABELS[item.kind]+" · "+item.host;box.append(label);shadow.append(box);
    }
    const count=k=>items.filter(i=>i.kind===k).length,panel=document.createElement("div");
    panel.className="panel";
    const title=document.createElement("b");title.textContent="DataExodus X-Ray";
    const lines=[`${count("pixel")} third-party pixel(s)`,`${count("hidden_frame")} hidden third-party frame(s)`,
      `${count("overlay")} invisible link overlay(s)`,`${scripts.length} third-party script host(s)`];
    panel.append(title);
    for(const text of lines){const div=document.createElement("div");div.textContent=text;panel.append(div);}
    const hosts=[...new Set([...items.map(i=>i.host),...scripts])].slice(0,10);
    if(hosts.length){const div=document.createElement("small");div.textContent="Hosts: "+hosts.join(", ");panel.append(div);}
    const note=document.createElement("small");
    note.textContent="Heuristic view of this page's markup. Use Guard evidence and receiver receipts to show what was actually sent.";
    panel.append(note);shadow.append(panel);
    document.documentElement.append(layer);
    return {on:true,pixels:count("pixel"),hidden_frames:count("hidden_frame"),overlays:count("overlay"),
      third_party_script_hosts:scripts.length,hosts};
  }
  chrome.runtime.onMessage.addListener((message,sender,respond)=>{
    if(message.type!=="xray" || sender.id!==chrome.runtime.id)return;
    const wasOn=!!layer;
    if(layer){layer.remove();layer=null;}
    respond(wasOn?{on:false}:draw(scan()));
  });
})();
