// Fixed bindings into the original nine-card physical animation.
module.exports=function(source){
 const {spec,width,height,frames}=this.getOptions();
 const plain=(v,n)=>typeof v==='string'&&v.trim()&&v.length<=n&&!/[<>\n\r]/.test(v);
 if(spec.resource_id!=='shotcraft:card-stack'||width!==1920||height!==1080||!Number.isInteger(frames)||frames<180||frames>360)throw Error('Unsupported collection stage');
 if(!['fa-IR','en-US'].includes(spec.locale)||!plain(spec.caption,48)||!plain(spec.kicker,24)||!plain(spec.subtitle,64))throw Error('Invalid collection copy');
 if(!Array.isArray(spec.cards)||spec.cards.length!==9||new Set(spec.cards.map(c=>c.asset)).size!==9||spec.cards.some(c=>!plain(c.title,12)||!plain(c.meta,16)||!/^assets\/compare-[0-9a-f]{64}\.png$/.test(c.asset)))throw Error('Nine distinct owned images required');
 const quote=v=>JSON.stringify(v).replaceAll('<','\\u003c').replaceAll('>','\\u003e').replaceAll('&','\\u0026');
 const once=(a,b)=>{if(source.split(a).length!==2)throw Error('Pinned collection source changed');source=source.replace(a,()=>b)};
 once("import { AbsoluteFill, useCurrentFrame } from 'remotion';","import { AbsoluteFill, useCurrentFrame, Img, staticFile, getInputProps } from 'remotion';");
 once("import { BRAND, MARK_PATHS, ShotcraftMark } from '../../_fixtures/Brand';",'');
 const start=source.indexOf('type Kind = '),end=source.indexOf('\nconst rand = ');
 if(start<0||end<start)throw Error('Pinned collection data changed');
 source=source.slice(0,start)+'const CARDS = '+quote(spec.cards)+';\n'+source.slice(end);
 once('  const f = useCurrentFrame();',`  const f = useCurrentFrame();\n  useStackMetrics(${quote(spec)});`);
 once("opacity: ramp(f, 0, 12, EASE.out)","opacity: 1");
 once('<ShotcraftMark size={30} tone="light" />','');
 once("fontFamily: FONT.mono, fontSize: 22, letterSpacing: '0.1em'","fontFamily: 'EditorGPTVazir', fontSize: 40, letterSpacing: 0");
 once('{`${BRAND.name} · shot recipes`}','{'+quote(spec.kicker)+'}');
 once('...type(88, 700)',"...type(88, 700), fontFamily:'EditorGPTVazir', direction:"+quote(spec.locale==='fa-IR'?'rtl':'ltr'));
 once('text="Start from a shot recipe."','text={'+quote(spec.caption)+'}');
 once('...type(34, 450)',"...type(40, 450), fontFamily:'EditorGPTVazir', direction:"+quote(spec.locale==='fa-IR'?'rtl':'ltr'));
 once('Nine shot recipes. Every one ready to render.','{'+quote(spec.subtitle)+'}');
 const face=source.indexOf('const CardFace:');
 if(face<0||source.indexOf('const CardFace:',face+1)>=0)throw Error('Pinned card face changed');
 // Discard ALL fictional covers, stats, avatar circles and duration claims.
 source=source.slice(0,face)+`
const CardFace: React.FC<{c:(typeof CARDS)[number];i:number}> = ({c,i}) => {
 const files=getInputProps<{scenes:{supporting_assets:string[]}[]}>().scenes[0].supporting_assets;
 if(!Array.isArray(files)||files.length!==9||!files.every((v,k)=>new RegExp('^support-0-'+k+'-[a-f0-9]+\\\\.png$').test(v)))throw Error('Missing owned collection images');
 return <div style={{position:'absolute',inset:0,direction:${quote(spec.locale==='fa-IR'?'rtl':'ltr')},fontFamily:'EditorGPTVazir'}}>
  <div style={{position:'absolute',left:12,right:12,top:12,height:COVER_H,borderRadius:14,overflow:'hidden',background:L.bg[1]}}>
   <Img src={staticFile(files[i])} style={{width:'100%',height:'100%',objectFit:'contain'}}/>
  </div>
  <div style={{position:'absolute',left:28,right:28,top:COVER_H+32,textAlign:'start'}}>
   <div style={{fontSize:36,lineHeight:1.5,color:L.ink2,whiteSpace:'nowrap'}}>{c.meta}</div>
   <div style={{fontSize:36,fontWeight:650,lineHeight:1.5,color:L.ink,marginTop:12,whiteSpace:'nowrap'}}>{c.title}</div>
  </div>
 </div>;
};
`;
 const hook=require('node:path').join(__dirname,'src/shotcraft/useStackMetrics');
 return 'import {useStackMetrics} from '+quote(hook)+';\n'+source+'\nexport default CardStack;';
};
