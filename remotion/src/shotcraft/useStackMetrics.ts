import {useEffect,useState} from 'react';
import {cancelRender,continueRender,delayRender} from 'remotion';

type Copy={caption:string;kicker:string;subtitle:string;cards:{title:string;meta:string}[]};
export function useStackMetrics(spec:Copy){
 const [handle]=useState(()=>delayRender('Checking collection text'));
 const key=JSON.stringify(spec);
 useEffect(()=>{
  let active=true;
  (async()=>{
   await Promise.all(['700 88px','400 40px','650 36px','400 36px'].map(font=>document.fonts.load(font+' EditorGPTVazir')));
   await document.fonts.ready;
   const ctx=document.createElement('canvas').getContext('2d');if(!ctx)throw Error('Cannot measure collection text');
   const check=(text:string,font:string,width:number)=>{ctx.font=font+' EditorGPTVazir';if(ctx.measureText(text).width>width)throw Error('Collection text exceeds its reserved slot')};
   check(spec.caption,'700 88px',1640);check(spec.kicker,'400 40px',900);check(spec.subtitle,'400 40px',1640);
   for(const card of spec.cards){check(card.title,'650 36px',264);check(card.meta,'400 36px',264)}
   if(active)continueRender(handle);
  })().catch(error=>{if(active)cancelRender(error)});
  return()=>{active=false;continueRender(handle)};
 },[key,handle]);
}
