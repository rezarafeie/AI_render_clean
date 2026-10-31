import {useEffect,useState} from 'react';
import {cancelRender,continueRender,delayRender} from 'remotion';

// Measure shaped Persian/English glyphs once after the local font is ready.
// No character-count approximations, per-frame layout reads or clipped copy.
export function useTextMetrics(prefix:string,final:string,features:string[],subtitle:string){
  const [handle]=useState(()=>delayRender('Measuring native text-column content'));
  const [metrics,setMetrics]=useState({prefix:0,final:0});
  const key=JSON.stringify([prefix,final,features,subtitle]);
  useEffect(()=>{
    let active=true;
    (async()=>{
      await document.fonts.load('500 72px EditorGPTVazir');
      await document.fonts.ready;
      const ctx=document.createElement('canvas').getContext('2d');
      if(!ctx)throw Error('Cannot measure native text');
      ctx.font='500 72px EditorGPTVazir';
      const p=ctx.measureText(prefix).width,f=ctx.measureText(final).width;
      const max=Math.max(f,...features.map(v=>ctx.measureText(v).width));
      ctx.font='500 48px EditorGPTVazir';
      if(p+max+24>660||ctx.measureText(subtitle).width>900)throw Error('Text exceeds pinned design: shorten the copy; automatic clipping is forbidden');
      if(active){setMetrics({prefix:p,final:f});continueRender(handle);}
    })().catch(e=>{if(active)cancelRender(e);});
    return()=>{active=false;continueRender(handle);};
  // key captures all copy; frame changes do not trigger measurement.
  },[key,handle]);
  return metrics;
}
