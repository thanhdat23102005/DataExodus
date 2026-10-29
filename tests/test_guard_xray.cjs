const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
let JSDOM;try{({JSDOM}=require('jsdom'));}catch{}
const root=path.join(__dirname,'../guard');
test('X-Ray outlines third-party pixels, hidden frames and invisible links, and toggles off',{skip:!JSDOM},()=>{
  const dom=new JSDOM(`<!doctype html><body>
    <img data-rect="1,1" src="https://px.tracker.example/p.gif">
    <img data-rect="0,0" style="display:none" src="https://stats.other.example/hit">
    <img data-rect="1,1" src="https://cdn.shop.example/spacer.gif">
    <img data-rect="300,200" src="https://images.cdn.example/hero.jpg">
    <iframe data-rect="0,0" style="visibility:hidden" src="https://ads.example/frame"></iframe>
    <a data-rect="240,60" style="opacity:0.01;z-index:1000;position:absolute" href="https://ads.example/click">x</a>
    <a data-rect="100,20" href="https://docs.example/">Docs</a>
    <script src="https://tags.tracker.example/t.js"></script></body>`,{url:'https://www.shop.example/',runScripts:'outside-only'});
  const w=dom.window;
  w.HTMLElement.prototype.getBoundingClientRect=function(){
    const [width,height]=(this.dataset.rect || '0,0').split(',').map(Number);return {left:10,top:10,width,height};
  };
  let listener;
  w.GuardCore=require('../guard/core.js');
  w.chrome={runtime:{id:'ext',onMessage:{addListener:fn=>listener=fn}}};
  w.eval(fs.readFileSync(path.join(root,'xray.js'),'utf8'));
  let reply;listener({type:'xray'},{id:'ext'},r=>reply=r);
  assert.equal(reply.on,true);
  assert.equal(reply.pixels,2);
  assert.equal(reply.hidden_frames,1);
  assert.equal(reply.overlays,1);
  assert.equal(reply.third_party_script_hosts,1);
  assert.ok(!reply.hosts.includes('cdn.shop.example'));
  assert.equal(w.document.documentElement.lastElementChild.shadowRoot,null);  // closed: the page cannot read it
  listener({type:'xray'},{id:'other-extension'},r=>reply='touched');
  assert.notEqual(reply,'touched');
  listener({type:'xray'},{id:'ext'},r=>reply=r);
  assert.deepEqual(JSON.parse(JSON.stringify(reply)),{on:false});
  dom.window.close();
});
