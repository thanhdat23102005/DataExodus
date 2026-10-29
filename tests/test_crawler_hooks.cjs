const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');

test('crawler init script executes hooks before page scripts',()=>{
  const source=fs.readFileSync(path.join(__dirname,'../crawler/crawl.py'),'utf8');
  const script=source.match(/script = """([\s\S]*?)"""/)[1];
  function HTMLCanvasElement(){}
  function CanvasRenderingContext2D(){}
  function WebGLRenderingContext(){}
  function AudioContext(){}
  HTMLCanvasElement.prototype.toDataURL=()=> 'data:image/png;base64,';
  CanvasRenderingContext2D.prototype.getImageData=()=>({});
  CanvasRenderingContext2D.prototype.measureText=()=>({width:10});
  WebGLRenderingContext.prototype.getParameter=()=> 'vendor';
  AudioContext.prototype.createAnalyser=()=>({});
  const window={};
  vm.runInNewContext(script,{window,HTMLCanvasElement,CanvasRenderingContext2D,WebGLRenderingContext,AudioContext});
  new HTMLCanvasElement().toDataURL();
  new CanvasRenderingContext2D().measureText('example');
  new WebGLRenderingContext().getParameter(37445);
  new AudioContext().createAnalyser();
  assert.deepEqual(Array.from(window.__fp_events,e=>e.type),['canvas','fonts','webgl','audio']);
});
