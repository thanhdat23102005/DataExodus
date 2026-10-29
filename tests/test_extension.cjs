// No npm dependencies: exercise the Chrome event handlers with API stubs.
const test = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');

function setup() {
  const events = {};
  const event = name => ({addListener:fn => {events[name]=fn;}});
  const posted=[];
  const context=vm.createContext({
    TextDecoder, setTimeout:()=>1, clearTimeout:()=>{}, URL,
    fetch:async (url,opts)=>{if(opts)posted.push(JSON.parse(opts.body));return {ok:true,json:async()=>({})};},
    chrome:{
      storage:{local:{get:(_keys,fn)=>fn({enabled:true})},onChanged:event('change')},
      webRequest:Object.fromEntries(['onBeforeRequest','onSendHeaders','onCompleted','onErrorOccurred','onBeforeRedirect'].map(name=>[name,event(name)])),
      alarms:{create:(_name,opts)=>assert.ok(opts.periodInMinutes>=0.5),onAlarm:event('alarm')},
      tabs:{get:async()=>({url:'https://example.com'}),query:async()=>[],onActivated:event('tab'),onUpdated:event('updated')},
      windows:{onRemoved:event('removed')}, action:{setBadgeText(){},setBadgeBackgroundColor(){},setTitle(){}},
    }
  });
  vm.runInContext(fs.readFileSync(path.join(__dirname,'../extension/background.js'),'utf8'),context);
  return {events,posted,context};
}

test('request phases merge by requestId despite differing timestamps',async()=>{
  const {events,posted,context}=setup();
  const base={requestId:'one',url:'https://telemetry.example.net/collect',timeStamp:1792627200000,type:'fetch',initiator:'https://shop.example.com'};
  events.onBeforeRequest({...base,requestBody:{formData:{email:['demo@example.com']}}});
  events.onSendHeaders({...base,timeStamp:base.timeStamp+5,requestHeaders:[{name:'Cookie',value:'test=1'}]});
  events.onCompleted({...base,timeStamp:base.timeStamp+40});
  await vm.runInContext('flush()',context);
  assert.equal(posted.length,1);
  assert.equal(posted[0].events.length,1);
  assert.equal(posted[0].events[0].ts,1792627200);
  assert.equal(posted[0].events[0].cookies,'test=1');
  assert.match(posted[0].events[0].body,/demo@example.com/);
});

test('pause discards unsent captured traffic',async()=>{
  const {events,posted,context}=setup();
  const base={requestId:'one',url:'https://example.net',timeStamp:1792627200000};
  events.onBeforeRequest(base);events.onCompleted(base);
  events.change({enabled:{newValue:false}});
  await vm.runInContext('flush()',context);
  assert.equal(posted.length,0);
});

test('agent requests are excluded from capture',async()=>{
  const {events,posted,context}=setup();
  const base={requestId:'one',url:'http://localhost:8000/ingest',timeStamp:1792627200000};
  events.onBeforeRequest(base);events.onCompleted(base);
  await vm.runInContext('flush()',context);
  assert.equal(posted.length,0);
});
