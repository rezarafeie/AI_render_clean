import {useEffect,useState} from 'react';
import {cancelRender,continueRender,delayRender} from 'remotion';

export function useCompareMetrics(caption:string,labels:string[]){
  const [handle]=useState(()=>delayRender('Checking comparison labels'));
  const key=JSON.stringify([caption,labels]);
  useEffect(()=>{
    let active=true;
    (async()=>{
      await document.fonts.load('700 64px EditorGPTVazir');await document.fonts.ready;
      const context=document.createElement('canvas').getContext('2d');
      if(!context)throw Error('Cannot measure comparison copy');
      context.font='700 64px EditorGPTVazir';
      if(context.measureText(caption).width>1640)throw Error('Comparison caption exceeds its reserved header');
      context.font='600 40px EditorGPTVazir';
      if(labels.some(label=>context.measureText(label).width>280))throw Error('Comparison label exceeds its reserved slot');
      if(active)continueRender(handle);
    })().catch(error=>{if(active)cancelRender(error)});
    return()=>{active=false;continueRender(handle)};
  },[key,handle]);
}
