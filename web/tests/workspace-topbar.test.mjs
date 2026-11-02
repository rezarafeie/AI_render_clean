import test from 'node:test';
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {build} from 'esbuild';
import {JSDOM} from 'jsdom';
const require=createRequire(new URL('../package.json',import.meta.url));
const React=require('react'),{createRoot}=require('react-dom/client'),{flushSync}=require('react-dom');
const compiled=await build({stdin:{contents:'export {Workspace} from "./studio/Workspace"; export {ShellContext} from "./components/ShellContext";',resolveDir:new URL('../src/',import.meta.url).pathname,loader:'tsx'},bundle:true,write:false,format:'cjs',platform:'node',external:['react'],plugins:[{
  name:'boundaries',setup(b){
    b.onResolve({filter:/react-router-dom|\/(api|ui|model|plan|useFullscreen|AuthenticatedMedia|Activity|RenderProgress|MotionScenes|LocalizeEdit|PlanReview|TimelineView|CreativeResources|MotionGraphic)$/},a=>({path:a.path,namespace:'test'}));
    b.onLoad({filter:/.*/,namespace:'test'},a=>({contents:a.path.endsWith('/api')?'export const api={studioOutputs:async()=>[],studioOutputUrl:()=>"/output"};'
      :a.path==='react-router-dom'?'import React from "react";export const NavLink=p=>React.createElement("a",{href:p.to},p.children);'
      :a.path.endsWith('/model')?'export const renderView=()=>({phase:"idle"});'
      :a.path.endsWith('/plan')?'export const planPhase=()=>"none";export const currentVersion=()=>null;'
      :a.path.endsWith('/ui')?'export const friendlyError=e=>String(e);'
      :a.path.endsWith('/useFullscreen')?'export const useFullscreen=()=>({active:false,toggle:async()=>{}});'
      :'export const AuthenticatedMedia=()=>null,ThinkingRow=()=>null,RenderProgress=()=>null,MotionScenes=()=>null,LocalizeEdit=()=>null,PlanReview=()=>null,TimelineView=()=>null,CreativeResources=()=>null,MotionPanel=()=>null;'}));
  }
}]});
const settle=()=>new Promise(r=>setTimeout(r,20));
const project={id:'p',engine:'motion',external_ref:'owned',title:'Project title',status:'awaiting_input',state:{},current_version:1};
test('Preview and Edit share top-bar fullscreen and dot status, without duplicated title/status rows',async()=>{
  const dom=new JSDOM('<div id="root"></div>',{url:'http://localhost/'}),old={window:globalThis.window,document:globalThis.document};
  Object.assign(globalThis,{window:dom.window,document:dom.window.document});
  const mod={exports:{}};new Function('require','module','exports',compiled.outputFiles[0].text)(require,mod,mod.exports);
  const root=createRoot(document.getElementById('root'));let action;
  const shell={openNav:()=>{},setTitle:()=>{},setAction:a=>{action=a;}};
  const props={conversation:null,project,projects:[project],onSelectProject:()=>{},tab:'preview',onTab:()=>{},onCancel:()=>{},onSaved:()=>{},showTabs:false,topbarControls:true};
  const draw=()=>flushSync(()=>root.render(React.createElement(mod.exports.ShellContext.Provider,{value:shell},React.createElement(mod.exports.Workspace,props))));
  try{
    for(const tab of ['preview','edit']){
      props.tab=tab;draw();await settle();
      assert.equal(document.querySelector('.ws-head').hidden,true);
      assert.equal(document.querySelectorAll('.ws-titlebar').length,0);
      assert.equal(action.status.tone,'warning');assert.equal(action.active,false);
      assert.equal(document.querySelector('.project-status-dot').textContent,'');
      assert.match(document.querySelector('.project-status-dot').getAttribute('aria-label'),/Waiting for you/);
    }
    flushSync(()=>action.onClick());await settle();assert.equal(action.active,true);
    assert.equal(document.querySelector('.workspace').getAttribute('data-max'),'true');
    assert.equal(!!document.querySelector('.ws-edit-exit'),true);
    flushSync(()=>action.onClick());await settle();assert.equal(action.active,false);
    props.project={...project,status:'error'};draw();await settle();assert.equal(action.status.tone,'error');
    props.projects=[project,{...project,id:'other',title:'Other project'}];draw();await settle();
    assert.equal(document.querySelector('.ws-project-picker select').options.length,2);
    props.topbarControls=false;props.showTabs=true;draw();await settle();
    assert.equal(action,null);assert.equal(document.querySelector('.ws-head').hidden,false);
    assert.equal(document.querySelectorAll('[role=tab]').length,2);
  }finally{flushSync(()=>root.unmount());dom.window.close();Object.assign(globalThis,old);}
});
