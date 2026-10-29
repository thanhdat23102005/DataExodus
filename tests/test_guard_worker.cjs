const test=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs'),path=require('node:path');
const {webcrypto}=require('node:crypto');
const Q='chrome-extension://test-extension/quarantine.html';
function setup({failRules=false,initialSettings,initialLearned=[],apiResult}={}) {
  const listeners={}, stored={settings:initialSettings}, session={learned:initialLearned},calls=[],ruleUpdates=[],sessionUpdates=[],created=[],removed=[],updated=[];
  const navigating=[],sent=[],tabUrls={4:'https://shop.example/manga/1'};
  let dynamic=[],sessionRules=[],failNextSession=false,rejectRegex=false;
  const event=name=>({addListener:fn=>listeners[name]=fn,removeListener(){}});
  const C=require('../guard/core.js');
  const context=vm.createContext({GuardCore:C,importScripts(){},crypto:webcrypto,TextEncoder,TextDecoder,URL,AbortSignal,
    console,Date,Map,Promise,setTimeout,clearTimeout,
    fetch:async(url,options)=>{calls.push({url,payload:JSON.parse(options.body)});
      return {ok:true,json:async()=>(apiResult || {source:'local',advisory_only:true})};},
    chrome:{runtime:{id:'test-extension',getURL:p=>'chrome-extension://test-extension/'+p,onMessage:event('message')},
      storage:{local:{get:async()=>stored,set:async data=>Object.assign(stored,data),setAccessLevel:async()=>{}},
        session:{get:async()=>session,set:async data=>Object.assign(session,data),setAccessLevel:async()=>{}}},
      declarativeNetRequest:{getDynamicRules:async()=>dynamic,isRegexSupported:async()=>({isSupported:!rejectRegex}),
        updateDynamicRules:async x=>{if(failRules)throw Error('DNR failed');ruleUpdates.push(x);dynamic=dynamic.filter(r=>!(x.removeRuleIds || []).includes(r.id)).concat(x.addRules || []);},
        getSessionRules:async()=>sessionRules,updateSessionRules:async x=>{if(failNextSession){failNextSession=false;throw Error('Session update failed');}sessionUpdates.push(x);sessionRules=sessionRules.filter(r=>!(x.removeRuleIds || []).includes(r.id)).concat(x.addRules || []);},onRuleMatchedDebug:event('rule')},
      webRequest:{onBeforeRequest:event('request')},
      webNavigation:{onCreatedNavigationTarget:event('popupTab'),onBeforeNavigate:{addListener:fn=>(navigating[navigating.length]=fn),removeListener(fn){const i=navigating.indexOf(fn);if(i>=0)navigating.splice(i,1);}}},
      tabs:{query:async()=>[],sendMessage:async(id,m,o)=>sent.push({id,m,o}),onRemoved:event('tabRemoved'),get:async id=>tabUrls[id]?{id,url:tabUrls[id]}:Promise.reject(Error('No tab')),
        onUpdated:event('tabUpdated'),update:async(id,details)=>updated.push({id,...details}),
        create:async details=>{const tab={...details,id:100+created.length};created.push(tab);return tab;},remove:async id=>removed.push(id)}}});
  vm.runInContext(fs.readFileSync(path.join(__dirname,'../guard/background.js'),'utf8'),context);
  const ui={id:'test-extension',url:'chrome-extension://test-extension/options.html'};
  const page={id:'test-extension',url:'https://shop.example/',tab:{id:4}};
  const quarantineTab=(tabId,hash='')=>({id:'test-extension',url:Q+hash,frameId:0,tab:{id:tabId}});
  async function message(m,sender=ui) {return new Promise(resolve=>listeners.message(m,sender,resolve));}
  return {context,stored,session,calls,ruleUpdates,sessionUpdates,created,removed,updated,listeners,message,ui,page,quarantineTab,navigating,sent,tabUrls,
    sessionRules:()=>sessionRules,failSessionOnce:()=>{failNextSession=true;},rejectRegex:()=>{rejectRegex=true;}};
}
test('worker applies DNR without service; pause removes rules; page cannot change settings',async()=>{
  const s=setup();const state=(await s.message({type:'state'})).data;
  assert.equal(state.settings.enabled,true);assert.ok(s.ruleUpdates[0].addRules.length>0);
  const rejected=await s.message({type:'save',settings:{enabled:false}},s.page);
  assert.equal(rejected.ok,false);
  assert.equal((await s.message({type:'save',settings:{...state.settings,enabled:false}})).ok,true);
  assert.equal(s.ruleUpdates.at(-1).addRules.length,0);
  assert.equal(s.calls.length,0);
});
test('installed rules carry the real quarantine URL and never the helper fields',async()=>{
  const s=setup();await s.message({type:'state'});
  const rules=s.ruleUpdates[0].addRules;
  assert.ok(rules.some(r=>r.action.redirect?.regexSubstitution?.startsWith(Q+'?reason=')));
  assert.ok(rules.every(r=>!('category' in r) && !('signals' in r)));
});
test('options page opened in a tab is still trusted extension UI; web pages are not',async()=>{
  const s=setup();
  const optionsTab={id:'test-extension',url:'chrome-extension://test-extension/options.html',tab:{id:9},frameId:0};
  assert.equal((await s.message({type:'state'},optionsTab)).ok,true);
  assert.equal((await s.message({type:'state'},s.page)).ok,false);
});
test('rule failures are visible and never reported as applied',async()=>{
  const s=setup({failRules:true});
  assert.match((await s.message({type:'state'})).data.startupError,/failed/);
  assert.equal((await s.message({type:'save',settings:{enabled:false}})).ok,false);
});
test('only network debug matches count as Chrome evidence; local identity observation stays separate',async()=>{
  const s=setup();
  await s.message({type:'save',settings:{testEmail:'student.demo@example.com',apiToken:'private-token-value',labMode:true}});
  await s.listeners.rule({rule:{ruleId:1},request:{url:'https://doubleclick.net/p?private=secret',type:'image',tabId:4}});
  await s.listeners.request({url:'https://collector.example/?email=student.demo%40example.com',type:'image',tabId:4});
  const events=(await s.message({type:'state'})).data.events;
  assert.equal(events.length,2);
  assert.equal(events[0].enforcement,'observed_only');assert.equal(events[1].enforcement,'network_blocked');
  assert.ok(!JSON.stringify(events).includes('student.demo'));
  assert.ok(!JSON.stringify(events).includes('private=secret'));
  const policy=(await s.message({type:'public_config'},s.page)).data;
  assert.equal('apiToken' in policy,false);assert.equal('testEmail' in policy,false);
  await s.message({type:'analyze'});
  const sent=s.calls[0].payload;
  assert.equal(sent.cloud_opt_in,false);
  assert.ok(!JSON.stringify(sent).includes('collector.example'));
  assert.ok(!JSON.stringify(sent).includes('student.demo'));
});
test('untrusted page reports cannot supply a threat verdict or become network evidence',async()=>{
  const s=setup();await s.message({type:'state'});
  await s.message({type:'page_event',signal:'known_threat',domain:'example.com'},s.page);
  assert.equal((await s.message({type:'state'})).data.events.length,0);
  await s.message({type:'page_event',signal:'popup_without_link',domain:'example.com'},s.page);
  const e=(await s.message({type:'state'})).data.events[0];
  assert.equal(e.evidence_quality,'page_report_unverified');
  assert.equal(e.enforcement,'interaction_prevented');
});
test('URL identifier protection is installed before a page observation occurs',async()=>{
  const s=setup({initialSettings:{testEmail:'student.demo@example.com'}});
  await s.message({type:'state'});
  const rules=s.ruleUpdates[0].addRules;
  assert.ok(rules.some(r=>r.action.type==='block' && r.condition.urlFilter && 'https://new-collector.example/collect?email=student.demo%40example.com'.includes(r.condition.urlFilter)));
  assert.ok(rules.filter(r=>r.priority===30).every(r=>r.condition.domainType==='thirdParty'));
  assert.equal(s.calls.length,0);
});
test('POST observation installs a scoped follow-up rule; same-host and unknown source cannot create one',async()=>{
  const s=setup({initialSettings:{testEmail:'student.demo@example.com'}});
  const body={formData:{email:['student.demo@example.com']}};
  await s.listeners.request({url:'https://collector.example/collect',initiator:'https://shop.example',type:'xmlhttprequest',tabId:4,requestBody:body});
  const state=(await s.message({type:'state'})).data;
  assert.equal(state.events[0].enforcement,'observed_only');
  assert.equal(state.events[0].third_party,true);
  assert.equal(state.learnedRulesCount,1);
  const rule=s.sessionUpdates.at(-1).addRules[0];
  assert.deepEqual(Array.from(rule.condition.requestDomains),['collector.example']);
  assert.deepEqual(Array.from(rule.condition.initiatorDomains),['shop.example']);
  assert.equal(rule.condition.domainType,'thirdParty');
  assert.ok(rule.condition.excludedResourceTypes.includes('main_frame'));
  await s.listeners.request({url:'https://shop.example/login',initiator:'https://shop.example',tabId:4,requestBody:body});
  await s.listeners.request({url:'https://different.example/collect',tabId:4,requestBody:body});
  assert.equal((await s.message({type:'state'})).data.learnedRulesCount,1);
  await s.message({type:'reset_learning'});
  assert.equal((await s.message({type:'state'})).data.learnedRulesCount,0);
});
test('learning respects site exceptions and policy changes clear session rules',async()=>{
  const s=setup({initialSettings:{testEmail:'student.demo@example.com',allowSites:['shop.example']}});
  await s.listeners.request({url:'https://collector.example/collect',initiator:'https://shop.example',tabId:4,requestBody:{formData:{email:['student.demo@example.com']}}});
  assert.equal((await s.message({type:'state'})).data.learnedRulesCount,0);
  const config=(await s.message({type:'state'})).data.settings;
  assert.equal((await s.message({type:'save',settings:{...config,enabled:false}})).ok,true);
  assert.equal(s.sessionUpdates.at(-1).addRules.length,0);
});
test('gesture quarantine opens an opaque local URL; the page view never includes the held URL',async()=>{
  const s=setup();
  const result=await s.message({type:'quarantine',url:'https://ads.example/private/path?email=private%40example.com#token',signal:'popup_without_link',gesture:true},s.page);
  assert.equal(result.data.opened,true);
  assert.match(s.created[0].url,/^chrome-extension:\/\/test-extension\/quarantine.html#[a-f0-9-]{36}$/);
  assert.equal(s.created[0].openerTabId,4);
  const record=Object.values(s.session.quarantines)[0];
  assert.equal(record.destination.origin,'https://ads.example');
  assert.equal(record.tab_id,100);
  const sender=s.quarantineTab(100,'#'+record.id);
  const view=(await s.message({type:'quarantine_state',id:record.id},sender)).data;
  assert.equal(view.destination.origin,'https://ads.example');
  assert.equal(view.has_url,true);
  assert.ok(!JSON.stringify(view).includes('private'));
  // Events, the evidence store, never carry it either.
  assert.ok(!JSON.stringify(s.stored).includes('private'));
  assert.equal((await s.message({type:'state'},sender)).ok,false);
  assert.equal((await s.message({type:'quarantine_state',id:record.id},s.quarantineTab(101))).data,null);
  assert.equal((await s.message({type:'quarantine_state'},{...sender,frameId:1})).ok,false);
  await s.message({type:'close_quarantine'},sender);assert.deepEqual(s.removed,[100]);
  assert.equal(s.calls.length,0);
});
test('untrusted reports without a user gesture, non-http targets and paused policy cannot open quarantine',async()=>{
  const s=setup();
  const m={type:'quarantine',url:'https://ads.example/',signal:'popup_without_link'};
  assert.equal((await s.message(m,s.page)).data.opened,false);
  assert.equal((await s.message({...m,url:'javascript:alert(1)',gesture:true},s.page)).data.opened,false);
  const config=(await s.message({type:'state'})).data.settings;
  await s.message({type:'save',settings:{...config,enabled:false}});
  assert.equal((await s.message({...m,gesture:true},s.page)).data.opened,false);
  assert.equal(s.created.length,0);
});
test('a redirected ad click is adopted and verified against policy, not taken from the page',async()=>{
  const s=setup();await s.message({type:'state'});
  const ad='https://www.googleadservices.com/pagead/aclk?sa=L&adurl='+encodeURIComponent('https://shop.example/p?gclid=x');
  await s.listeners.rule({rule:{ruleId:1101},request:{url:ad,type:'main_frame',tabId:7}});
  const event=(await s.message({type:'state'})).data.events[0];
  assert.equal(event.enforcement,'navigation_quarantined');assert.deepEqual(event.signals,['ad_click']);
  const sender=s.quarantineTab(7,'?reason=ad_click&network=Google%20Ads#'+ad);
  const {id}=(await s.message({type:'quarantine_adopt',reason:'ad_click',url:ad},sender)).data;
  const view=(await s.message({type:'quarantine_state',id},sender)).data;
  assert.equal(view.reason,'ad_click');assert.equal(view.network,'Google Ads');assert.equal(view.verified,true);
  assert.equal(view.direct_available,true);
  // A page that opens quarantine.html itself cannot claim a rule sent it.
  const forged=(await s.message({type:'quarantine_adopt',reason:'ad_click',url:'https://harmless.example/'},s.quarantineTab(8))).data;
  const forgedView=(await s.message({type:'quarantine_state',id:forged.id},s.quarantineTab(8))).data;
  assert.equal(forgedView.reason,'opened_directly');assert.equal(forgedView.verified,false);
  // Web pages cannot adopt or read quarantine records.
  assert.equal((await s.message({type:'quarantine_adopt',url:ad},s.page)).ok,false);
});
test('identity navigation is verified only by a matching Chrome rule and keeps no URL',async()=>{
  const s=setup({initialSettings:{testEmail:'student.demo@example.com'}});await s.message({type:'state'});
  const rules=s.context.GuardCore.rules({testEmail:'student.demo@example.com'},
    await s.context.GuardCore.identityTokens('student.demo@example.com',webcrypto),Q);
  const nav=rules.find(r=>r.category==='identity_url' && r.condition.resourceTypes?.[0]==='main_frame');
  await s.listeners.rule({rule:{ruleId:nav.id},request:{url:'https://c.example/?e=student.demo%40example.com',type:'main_frame',tabId:5}});
  const {id}=(await s.message({type:'quarantine_adopt',reason:'identity_url'},s.quarantineTab(5))).data;
  const view=(await s.message({type:'quarantine_state',id},s.quarantineTab(5))).data;
  assert.equal(view.reason,'identity_url');assert.equal(view.verified,true);assert.equal(view.has_url,false);
  assert.ok(!JSON.stringify(s.session).includes('student.demo'));
  const other=(await s.message({type:'quarantine_adopt',reason:'identity_url'},s.quarantineTab(6))).data;
  assert.equal((await s.message({type:'quarantine_state',id:other.id},s.quarantineTab(6))).data.verified,false);
  assert.equal((await s.message({type:'sandbox_preview',id},s.quarantineTab(5))).ok,false);
});
test('sandbox preview sends only the held URL, needs the token, and enables the clean destination',async()=>{
  const apiResult={ok:true,clean_url:'https://shop.example/p',redirect_chain:[],trackers:[],request_count:3};
  const s=setup({apiResult});await s.message({type:'state'});
  const ad='https://ad.doubleclick.net/clk;1?x=1';
  const sender=s.quarantineTab(7);
  const {id}=(await s.message({type:'quarantine_adopt',reason:'network_rule',url:ad},sender)).data;
  assert.match((await s.message({type:'sandbox_preview',id},sender)).error,/token/);
  await s.message({type:'save',settings:{...(await s.message({type:'state'})).data.settings,apiToken:'a-local-token-of-24-characters'}});
  const {id:id2}=(await s.message({type:'quarantine_adopt',reason:'network_rule',url:ad},sender)).data;
  const result=await s.message({type:'sandbox_preview',id:id2,url:'https://evil.example/'},sender);
  assert.equal(result.ok,true);
  assert.equal(s.calls.at(-1).url,'http://127.0.0.1:8010/sandbox/preview');
  assert.deepEqual(s.calls.at(-1).payload,{url:ad});
  assert.equal((await s.message({type:'quarantine_state',id:id2},sender)).data.clean_available,true);
  assert.equal((await s.message({type:'open_destination',id:id2,target:'clean'},sender)).ok,true);
  assert.deepEqual(s.updated.at(-1),{id:7,url:'https://shop.example/p'});
  const allow=s.sessionRules().find(r=>r.id===1000007);
  assert.equal(allow.action.type,'allow');assert.deepEqual(Array.from(allow.condition.tabIds),[7]);
  assert.ok(allow.priority>30);
  assert.equal((await s.message({type:'open_destination',id:id2,target:'elsewhere'},sender)).ok,false);
});
test('open original anyway uses the held URL only for that tab',async()=>{
  const s=setup();await s.message({type:'state'});
  const ad='https://ad.doubleclick.net/clk;1?x=1',sender=s.quarantineTab(7);
  const {id}=(await s.message({type:'quarantine_adopt',reason:'network_rule',url:ad},sender)).data;
  assert.equal((await s.message({type:'open_destination',id,target:'original'},s.quarantineTab(8))).ok,false);
  assert.equal((await s.message({type:'open_destination',id,target:'original'},sender)).ok,true);
  assert.deepEqual(s.updated.at(-1),{id:7,url:ad});
});
test('session update failure rolls back dynamic rules and leaves prior settings intact',async()=>{
  const s=setup();const old=(await s.message({type:'state'})).data.settings;
  s.failSessionOnce();const result=await s.message({type:'save',settings:{...old,enabled:false}});
  assert.equal(result.ok,false);
  assert.equal((await s.message({type:'state'})).data.settings.enabled,true);
  assert.ok(s.ruleUpdates.at(-1).addRules.length>0);
});
test('unsupported identity regex rejects save without silently losing existing protection',async()=>{
  const s=setup();await s.message({type:'state'});s.rejectRegex();
  const result=await s.message({type:'save',settings:{testEmail:'student.demo@example.com'}});
  assert.equal(result.ok,false);
  assert.equal((await s.message({type:'state'})).data.settings.testEmail,'');
  assert.equal(s.ruleUpdates.length,1);
});
test('worker restart restores session-scoped learned policy without reconstructing identifiers from page data',async()=>{
  const s=setup({initialSettings:{testEmail:'student.demo@example.com'},initialLearned:[{source:'shop.example',target:'collector.example',signals:['identifier_hash']}]});
  assert.equal((await s.message({type:'state'})).data.learnedRulesCount,1);
  assert.equal(s.sessionUpdates[0].addRules[0].condition.initiatorDomains[0],'shop.example');
  assert.equal(s.calls.length,0);
});
const settle=()=>new Promise(r=>setTimeout(r,400));
test('a pop-under tab is closed and recorded as browser-observed, without a quarantine tab or its URL',async()=>{
  const s=setup();await s.message({type:'state'});
  s.listeners.popupTab({sourceTabId:4,sourceFrameId:0,tabId:30,url:'https://casino.example/join?ref=secret'});await settle();
  assert.deepEqual(s.removed,[30]);assert.equal(s.created.length,0);
  const e=(await s.message({type:'state'})).data.events[0];
  assert.equal(e.kind,'popup');assert.equal(e.domain,'casino.example');assert.deepEqual(Array.from(e.signals),['popup_without_link']);
  assert.equal(e.evidence_quality,'chrome_tab_observed');assert.equal(e.enforcement,'interaction_prevented');
  assert.ok(!JSON.stringify(s.stored).includes('secret'));
  assert.equal(s.sent.at(-1).m.type,'popup_closed');assert.equal(s.sent.at(-1).o.frameId,0);
});
test('a pop-under that opens about:blank is judged by the address it navigates to',async()=>{
  const s=setup();await s.message({type:'state'});
  s.listeners.popupTab({sourceTabId:4,sourceFrameId:0,tabId:31,url:'about:blank'});
  s.navigating.forEach(fn=>fn({tabId:31,frameId:0,url:'https://ads.example/landing'}));await settle();
  assert.deepEqual(s.removed,[31]);assert.equal(s.navigating.length,0);
});
test('tabs the user asked for stay open: clicked or right-clicked links, same site, allowed sites, paused guard',async()=>{
  const s=setup();await s.message({type:'state'});
  await s.message({type:'link_intent',href:'https://docs.example/guide'},s.page);
  s.listeners.popupTab({sourceTabId:4,tabId:40,url:'https://docs.example/guide'});
  await s.message({type:'link_intent',href:'https://news.example/a',menu:true},s.page);
  s.listeners.popupTab({sourceTabId:4,tabId:41,url:'https://www.news.example/a?ref=menu'});
  s.listeners.popupTab({sourceTabId:4,tabId:42,url:'https://cdn.shop.example/reader'});
  s.listeners.popupTab({sourceTabId:9,tabId:43,url:'https://ads.example/'});  // source tab gone: unknown site
  await settle();assert.deepEqual(s.removed,[]);
  assert.equal((await s.message({type:'link_intent',href:'javascript:alert(1)'},s.page)).data.ok,false);
  const config=(await s.message({type:'state'})).data.settings;
  await s.message({type:'save',settings:{...config,allowSites:['shop.example']}});
  s.listeners.popupTab({sourceTabId:4,tabId:44,url:'https://ads.example/'});
  await s.message({type:'save',settings:{...config,popupGuard:false}});
  s.listeners.popupTab({sourceTabId:4,tabId:45,url:'https://ads.example/'});
  await settle();assert.deepEqual(s.removed,[]);
});

