import {useEffect,useState} from 'react';
import {cancelRender,continueRender,delayRender} from 'remotion';

type Card={name:string;desc:string;lines:string[];value:string;label:string;unit:string[]};
// Reject oversized shaped text instead of silently clipping or shrinking it.
export function useCardMetrics(caption:string,kicker:string,labels:string[],cards:Card[]){
  const [handle]=useState(()=>delayRender('Checking native card text geometry'));
  const key=JSON.stringify([caption,kicker,labels,cards]);
  useEffect(()=>{
    let active=true;
    (async()=>{
      await document.fonts.load('500 84px EditorGPTVazir');
      await document.fonts.ready;
      const ctx=document.createElement('canvas').getContext('2d');
      if(!ctx)throw Error('Cannot measure card text');
      const fits=(text:string,size:number,width:number,weight:number)=>{
        ctx.font=`${weight} ${size}px EditorGPTVazir`;
        if(ctx.measureText(text).width>width)throw Error('Card copy exceeds its measured slot: shorten it; clipping is forbidden');
      };
      fits(caption,84,1480,760);fits(kicker,40,1480,700);
      labels.forEach(v=>fits(v,40,150,700));
      cards.forEach(c=>{
        fits(c.name,52,400,750);fits(c.desc,40,400,450);
        c.lines.forEach(v=>fits(v,40,400,400));
        fits(c.value,120,370,800);fits(c.label,40,400,550);
        c.unit.forEach(v=>fits(v,40,200,600));
      });
      if(active)continueRender(handle);
    })().catch(e=>{if(active)cancelRender(e);});
    return()=>{active=false;continueRender(handle);};
  },[key,handle]);
}
