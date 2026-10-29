const test=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs'),path=require('node:path');
test('MAIN-world popup hook preserves primary click handler and legitimate link windows',()=>{
  const events={},documentEvents={},opened=[],reports=[];
  class CustomEvent {constructor(type,options={}){this.type=type;this.detail=options.detail;}}
  const window={open:(...args)=>{opened.push(args);return {};},addEventListener:(name,fn)=>events[name]=fn,
    dispatchEvent:e=>{if(e.type==='dataexodus:event')reports.push(JSON.parse(e.detail));events[e.type]?.(e);}};
  const context=vm.createContext({GuardCore:require('../guard/core.js'),window,CustomEvent,URL,Date,
    document:{addEventListener:(name,fn)=>documentEvents[name]=fn},location:{href:'https://shop.example/'}});
  vm.runInContext(fs.readFileSync(path.join(__dirname,'../guard/page.js'),'utf8'),context);
  window.dispatchEvent(new CustomEvent('dataexodus:policy',{detail:JSON.stringify({enabled:true,popupGuard:true})}));
  assert.equal(window.open('https://ads.example/'),null);
  assert.equal(opened.length,0);assert.equal(reports[0].signal,'popup_without_link');
  assert.ok(window.open('/docs'));assert.equal(opened.length,1);
  documentEvents.click({isTrusted:true,target:{closest:()=>({href:'https://docs.example/'})}});
  assert.ok(window.open('https://docs.example/'));assert.equal(opened.length,2);
  assert.doesNotThrow(()=>window.open('http://[invalid'));
});
