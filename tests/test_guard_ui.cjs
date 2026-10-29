const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
let JSDOM;try{({JSDOM}=require('jsdom'));}catch{}
const root=path.join(__dirname,'../guard');
test('popup distinguishes evidence and renders advisory output as text, never HTML',{skip:!JSDOM},async()=>{
  const settings=require('../guard/core.js').config();
  const events=[{kind:'identity_match',domain:'collector.example',signals:['identifier_hash'],enforcement:'observed_only',evidence_quality:'local_identifier_match'},
    {kind:'popup',domain:'ads.example',signals:['popup_without_link'],enforcement:'interaction_prevented',evidence_quality:'page_report_unverified'}];
  const dom=new JSDOM(fs.readFileSync(path.join(root,'popup.html'),'utf8'),{runScripts:'outside-only',url:'https://extension-ui.invalid'});
  dom.window.chrome={runtime:{sendMessage:async m=>({ok:true,data:m.type==='state'?{settings,events,startupError:''}:{source:'gemini',cloud_status:'completed',explanation:'<img src=x onerror=alert(1)>',next_step:'inspect_in_lab'}})}};
  dom.window.eval(fs.readFileSync(path.join(root,'popup.js'),'utf8'));
  await new Promise(resolve=>setImmediate(resolve));
  assert.equal(dom.window.document.getElementById('blocked').textContent,'0');
  assert.equal(dom.window.document.getElementById('observed').textContent,'1');
  assert.match(dom.window.document.getElementById('events').textContent,/unverified/);
  dom.window.document.getElementById('explain').click();await new Promise(resolve=>setImmediate(resolve));
  assert.equal(dom.window.document.querySelector('#advice img'),null);
  assert.match(dom.window.document.getElementById('advice').textContent,/<img/);
  dom.window.close();
});
test('options require URL disclosure consent before lookup and offer user blocking only for listed result',{skip:!JSDOM},async()=>{
  const C=require('../guard/core.js'),settings=C.config();let lookups=0;
  const dom=new JSDOM(fs.readFileSync(path.join(root,'options.html'),'utf8'),{runScripts:'outside-only',url:'https://extension-ui.invalid'});
  dom.window.GuardCore=C;dom.window.chrome={runtime:{sendMessage:async m=>{
    if(m.type==='reputation'){lookups++;return {ok:true,data:{status:'listed',threat_types:['SOCIAL_ENGINEERING']}};}
    return {ok:true,data:{settings,events:[],startupError:''}};
  }}};
  dom.window.eval(fs.readFileSync(path.join(root,'options.js'),'utf8'));
  await new Promise(resolve=>setImmediate(resolve));
  const doc=dom.window.document;
  doc.getElementById('lookupURL').value='https://test.example/path';
  doc.getElementById('lookup').click();await new Promise(resolve=>setImmediate(resolve));
  assert.equal(lookups,0);assert.match(doc.getElementById('status').textContent,/Confirm/);
  doc.getElementById('lookupConsent').checked=true;doc.getElementById('lookup').click();await new Promise(resolve=>setImmediate(resolve));
  assert.equal(lookups,1);assert.equal(doc.getElementById('blockDetected').hidden,false);
  assert.match(doc.getElementById('blockDetected').textContent,/test.example/);
  dom.window.close();
});
