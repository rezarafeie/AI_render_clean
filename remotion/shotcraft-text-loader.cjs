// Bind bounded copy into the pinned original motion, never model-authored code.
module.exports=function(source){
  const {spec,width,height,frames}=this.getOptions();
  if(spec.resource_id!=='shotcraft:text-column-converge'||width!==1920||height!==1080)throw Error('Unsupported text-column stage');
  const plain=(s,max)=>typeof s==='string'&&s.trim()&&s.length<=max&&!/[<>\n\r]/.test(s);
  if(!plain(spec.caption,24)||!plain(spec.prefix,12)||!plain(spec.subtitle,48)||!['fa-IR','en-US'].includes(spec.locale))throw Error('Invalid text-column content');
  if(!Array.isArray(spec.features)||spec.features.length<2||spec.features.length>6||spec.features.some(v=>!plain(v,24)||v.trim().split(/\s+/).length>3)||new Set(spec.features).size!==spec.features.length)throw Error('Invalid feature list');
  const quote=v=>JSON.stringify(v).replaceAll('<','\\u003c').replaceAll('>','\\u003e').replaceAll('&','\\u0026');
  const durations=spec.features.map((v,i)=>Math.ceil(Math.max(.6,v.trim().split(/\s+/).length/2.5)*30)+[0,3,1,2,0,3][i]);
  const min=durations.reduce((a,b)=>a+b,0)+10+36+18+4+Math.max(36,Math.ceil(spec.subtitle.trim().split(/\s+/).length/2.5*30));
  if(!Number.isInteger(frames)||frames<Math.max(120,min)||frames>360)throw Error('Text-column requires reading hold');
  const once=(needle,value)=>{if(source.split(needle).length!==2)throw Error('Pinned text binding changed');source=source.replace(needle,()=>value);};
  once("const BRAND_WORD = 'video-shotcraft';",'const BRAND_WORD = '+quote(spec.caption)+';');
  const list=source.match(/const STEPS: \{ word: string; dur: number \}\[\] = \[[\s\S]*?\];/);
  if(!list)throw Error('Pinned steps changed');
  once(list[0],'const STEPS: {word:string;dur:number}[] = '+quote([...spec.features.map((word,i)=>({word,dur:durations[i]})),{word:spec.caption,dur:999}])+';');
  once('const START = 8;','const START = 0;');
  once('const LSP = 3;','const LSP = 0;');
  // Adapt the demo's small specification typography to readable user copy.
  once('const FS = 42;','const FS = 72;');
  source=source.replaceAll('top: 519','top: 486');
  once('  const f = useCurrentFrame();',`  const f = useCurrentFrame();
  const metrics=useTextMetrics(${quote(spec.prefix)},${quote(spec.caption)},${quote(spec.features)},${quote(spec.subtitle)});
  const LINE_W=metrics.prefix+metrics.final+24;
  const MERGED_LEFT=960-LINE_W/2;
  const MERGED_RIGHT=960+LINE_W/2;`);
  once('fontFamily: FONT.mono,',"fontFamily: 'EditorGPTVazir', direction: "+quote(spec.locale==='fa-IR'?'rtl':'ltr')+',');
  once('lineHeight: 1,','lineHeight: 1.5,');
  once('              NEW\n','              {'+quote(spec.prefix)+'}\n');
  once('            CRAFT THE SHOT.\n','            {'+quote(spec.subtitle)+'}\n');
  if(spec.locale==='fa-IR'){
    once('left: newLeft, top: 486,','right: newLeft, top: 486,');
    once('right: 1920 - wordRight, top: 486,','left: 1920 - wordRight, top: 486,');
    once('left: MERGED_LEFT, top: 486 + FS + 14,','right: MERGED_LEFT, top: 486 + FS + 14,');
  }
  once("fontStyle: 'italic',","fontStyle: 'normal', fontSize: 48,");
  const hook=require('node:path').join(__dirname,'src/shotcraft/useTextMetrics');
  return 'import {useTextMetrics} from '+quote(hook)+';\n'+source+'\nexport default TextColumnConverge;';
};
