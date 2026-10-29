// Optional: npm install jsdom, then NODE_PATH=/path/to/node_modules node --test tests/test_report_ui.cjs
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
let JSDOM;
try {({JSDOM}=require('jsdom'));} catch {}

test('audit report switches captures, filters findings and renders evidence',{skip:!JSDOM},()=>{
  const html=fs.readFileSync(path.join(__dirname,'../reports/demo/audit.html'),'utf8');
  const dom=new JSDOM(html,{runScripts:'dangerously',url:'https://local-report.invalid'});
  const {document,Event}=dom.window;
  assert.equal(document.querySelector('#mode').textContent,'SYNTHETIC DEMO');
  assert.equal(document.querySelector('#pii').textContent,'4');
  assert.equal(document.querySelectorAll('.finding').length,6);
  assert.match(document.querySelector('#comparison').textContent,/6/);
  const priority=document.querySelector('#severity');
  priority.value='urgent';priority.dispatchEvent(new Event('change'));
  assert.equal(document.querySelectorAll('.finding').length,4);
  const capture=document.querySelector('#capture');
  capture.value='current';capture.dispatchEvent(new Event('change'));
  assert.equal(document.querySelector('#pii').textContent,'0');
  assert.equal(document.querySelectorAll('.finding').length,0);
  assert.match(document.querySelector('#findings').textContent,/Check capture coverage/);
  dom.window.close();
});
