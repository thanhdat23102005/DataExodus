const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
let JSDOM;try{({JSDOM}=require('jsdom'));}catch{}
const root=path.join(__dirname,'../guard');
function open(url,reply){
  const dom=new JSDOM(fs.readFileSync(path.join(root,'quarantine.html'),'utf8'),{runScripts:'outside-only',url});
  const sent=[];let network=0;
  dom.window.fetch=()=>{network++;throw Error('Remote fetch forbidden');};
  dom.window.chrome={runtime:{sendMessage:async m=>{sent.push(m);return reply(m);}}};
  dom.window.eval(fs.readFileSync(path.join(root,'quarantine.js'),'utf8'));
  return {dom,doc:dom.window.document,sent,network:()=>network};
}
const plain=value=>JSON.parse(JSON.stringify(value));
const tick=()=>new Promise(resolve=>setImmediate(resolve));
test('quarantine renders only escaped srcdoc with empty sandbox and no remote URL',{skip:!JSDOM},async()=>{
  const {dom,doc,network}=open('https://extension-ui.invalid/',()=>({ok:true,data:{destination:{origin:'<img src="https://attacker.invalid/" onerror="alert(1)">',path_segments:1,query_fields:2,has_fragment:true},reason:'popup_without_link'}}));
  await tick();await tick();
  const frame=doc.getElementById('preview');
  assert.equal(frame.getAttribute('sandbox'),'');assert.equal(frame.hasAttribute('src'),false);
  assert.equal(frame.getAttribute('referrerpolicy'),'no-referrer');
  assert.match(frame.srcdoc,/&lt;img/);assert.ok(!frame.srcdoc.includes('<img'));
  assert.match(doc.querySelector('meta[http-equiv]').content,/connect-src 'none'/);
  assert.equal(doc.querySelector('img'),null);assert.equal(network(),0);
  dom.window.close();
});
test('a redirect hands the URL to the worker and removes it from the address bar',{skip:!JSDOM},async()=>{
  const ad='https://ad.doubleclick.net/clk;1?x=1';
  const {dom,sent}=open('chrome-extension://id/quarantine.html?reason=ad_click&network=Google%20Ads#'+ad,m=>({ok:true,
    data:m.type==='quarantine_adopt'?{id:'11111111-2222-3333-4444-555555555555'}:{reason:'ad_click',network:'Google Ads',verified:true,has_url:true,
      destination:{origin:'https://ad.doubleclick.net',path_segments:1,query_fields:1,has_fragment:false}}}));
  await tick();await tick();await tick();
  assert.deepEqual(plain(sent[0]),{type:'quarantine_adopt',reason:'ad_click',url:ad});
  assert.equal(dom.window.location.hash,'#11111111-2222-3333-4444-555555555555');
  assert.ok(!dom.window.location.href.includes('doubleclick'));
  assert.equal(sent[1].id,'11111111-2222-3333-4444-555555555555');
  assert.equal(dom.window.document.getElementById('sandboxPreview').hidden,false);
  assert.match(dom.window.document.getElementById('reason').textContent,/Google Ads/);
  dom.window.close();
});
test('sandbox result is rendered as text; only a base64 data screenshot; actions send ids, never URLs',{skip:!JSDOM},async()=>{
  const result={ok:true,clean_url:'https://shop.example/p',redirect_chain:['https://a.example/<script>x</script>'],trackers:[{domain:'t.example',owner:'<b>Owner</b>'}],
    request_count:4,title:'<img src=x onerror=alert(1)>',screenshot_jpeg_b64:'QUJD',refused_internal:['192.168.1.1']};
  const {dom,doc,sent}=open('chrome-extension://id/quarantine.html#11111111-2222-3333-4444-555555555555',m=>({ok:true,
    data:m.type==='sandbox_preview'?result:m.type==='quarantine_state'?{reason:'network_rule',verified:true,has_url:true,sandbox_configured:true}:{ok:true}}));
  await tick();await tick();
  doc.getElementById('sandboxPreview').click();await tick();await tick();
  assert.equal(doc.getElementById('sandbox').hidden,false);
  assert.equal(doc.querySelector('#chain script'),null);assert.match(doc.getElementById('chain').textContent,/<script>/);
  assert.equal(doc.querySelector('#trackers b'),null);
  assert.equal(doc.querySelectorAll('img').length,1);assert.equal(doc.querySelector('img').src,'data:image/jpeg;base64,QUJD');
  assert.match(doc.getElementById('detail').textContent,/1 refused/);
  doc.getElementById('openClean').click();await tick();
  assert.deepEqual(plain(sent.at(-1)),{type:'open_destination',id:'11111111-2222-3333-4444-555555555555',target:'clean'});
  assert.ok(sent.every(m=>!JSON.stringify(m).includes('shop.example')));
  dom.window.close();
});
test('the score and reasons are shown as text, and a dangerous result offers no clean link',{skip:!JSDOM},async()=>{
  const assessment={score:85,level:'danger',label:'Dangerous',note:'One anonymous visit.',
    reasons:[{code:'clipboard_write',points:40,text:'<img src=x onerror=alert(1)> clipboard'},{code:'download',points:35,text:'download'}]};
  const {dom,doc}=open('chrome-extension://id/quarantine.html#11111111-2222-3333-4444-555555555555',m=>({ok:true,
    data:m.type==='sandbox_preview'?{ok:true,clean_url:'https://x.example/',redirect_chain:[],trackers:[],request_count:1,assessment}
      :{reason:'ad_click',has_url:true,sandbox_configured:true}}));
  await tick();await tick();doc.getElementById('sandboxPreview').click();await tick();await tick();
  assert.equal(doc.getElementById('assessment').hidden,false);
  assert.equal(doc.getElementById('score').textContent,'Dangerous · score 85 / 100');
  assert.equal(doc.getElementById('score').className,'score danger');
  assert.equal(doc.querySelectorAll('#reasons li').length,2);
  assert.equal(doc.querySelector('#reasons img'),null);assert.match(doc.getElementById('reasons').textContent,/\+40  <img/);
  assert.equal(doc.getElementById('openClean').hidden,true);
  dom.window.close();
});
test('a screenshot that is not plain base64 is never turned into an image',{skip:!JSDOM},async()=>{
  const {dom,doc}=open('chrome-extension://id/quarantine.html#11111111-2222-3333-4444-555555555555',m=>({ok:true,
    data:m.type==='sandbox_preview'?{ok:true,clean_url:null,redirect_chain:[],trackers:[],request_count:0,screenshot_jpeg_b64:'x" onerror="alert(1)'}:{has_url:true}}));
  await tick();await tick();doc.getElementById('sandboxPreview').click();await tick();await tick();
  assert.equal(doc.querySelector('img'),null);
  assert.equal(doc.getElementById('openClean').hidden,true);
  dom.window.close();
});
test('MAIN-world popup reports never request quarantine; a clicked hidden overlay does, once',async()=>{
  const C=require('../guard/core.js'),winEvents={},docEvents={},calls=[];
  const element=()=>({style:{},attachShadow:()=>({append(){}}),append(){},remove(){}});
  const context=vm.createContext({GuardCore:C,Date,URL,setTimeout:()=>1,getComputedStyle:()=>({opacity:'0',zIndex:'999'}),CustomEvent:class{constructor(type,opt){this.type=type;this.detail=opt?.detail;}},
    location:{href:'https://shop.example/'},window:{addEventListener:(k,fn)=>winEvents[k]=fn,dispatchEvent(){}},
    document:{addEventListener:(k,fn)=>docEvents[k]=fn,createElement:element,body:{append(){}}},
    chrome:{runtime:{onMessage:{addListener(){}},sendMessage:async m=>{calls.push(m);return {ok:true,data:C.publicConfig({})};}}}});
  vm.runInContext(fs.readFileSync(path.join(root,'content.js'),'utf8'),context);
  await tick();
  const event={detail:JSON.stringify({signal:'popup_without_link',domain:'ads.example',url:'https://ads.example/private?token=secret'})};
  winEvents['dataexodus:event'](event);
  assert.equal(calls.filter(c=>c.type==='quarantine').length,0);
  docEvents.click({isTrusted:false,target:{closest:()=>null}});winEvents['dataexodus:event'](event);
  assert.equal(calls.filter(c=>c.type==='quarantine').length,0);
  // Even right after a real click: a popup nobody asked for is blocked and reported, not held for review.
  docEvents.click({isTrusted:true,target:{closest:()=>null}});winEvents['dataexodus:event'](event);
  assert.equal(calls.filter(c=>c.type==='quarantine').length,0);
  assert.equal(calls.filter(c=>c.type==='page_event' && c.signal==='popup_without_link').length,3);
  const overlay={href:'https://ads.example/landing',getBoundingClientRect:()=>({width:800,height:600})};
  const click={isTrusted:true,target:{closest:()=>overlay},preventDefault(){this.prevented=true;},stopImmediatePropagation(){}};
  docEvents.click(click);docEvents.click({...click});
  assert.equal(click.prevented,true);
  assert.equal(calls.filter(c=>c.type==='quarantine').length,2);
  assert.ok(calls.filter(c=>c.type==='quarantine').every(c=>c.gesture===true && c.signal==='transparent_overlay'));
  assert.equal(calls.filter(c=>c.type==='link_intent').length,0);
  // An ordinary visible link is remembered as the user's intent instead.
  getComputedStyleVisible(context);
  docEvents.click({isTrusted:true,target:{closest:()=>({href:'https://docs.example/a',getBoundingClientRect:()=>({width:80,height:20})})}});
  assert.deepEqual(calls.filter(c=>c.type==='link_intent').map(c=>c.href),['https://docs.example/a']);
});
function getComputedStyleVisible(context){context.getComputedStyle=()=>({opacity:'1',zIndex:'0'});}
