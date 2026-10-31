// Bind two real, backend-owned states into the pinned slider, without fake degradation.
module.exports=function(source){
  const {spec,width,height,frames}=this.getOptions();
  const plain=(s,n)=>typeof s==='string'&&s.trim()&&s.length<=n&&!/[<>\n\r]/.test(s);
  if(spec.resource_id!=='shotcraft:before-after-slider-scrub'||width!==1920||height!==1080||!Number.isInteger(frames)||frames<150||frames>360)throw Error('Unsupported comparison stage/hold');
  if(!['fa-IR','en-US'].includes(spec.locale)||!plain(spec.caption,48)||!plain(spec.before_label,12)||!plain(spec.after_label,12)||!plain(spec.comparison_basis,160))throw Error('Invalid comparison copy');
  if(![spec.before_asset,spec.after_asset].every(v=>/^assets\/compare-[0-9a-f]{64}\.png$/.test(v))||spec.before_asset===spec.after_asset)throw Error('Two explicit local comparison states required');
  const quote=v=>JSON.stringify(v).replaceAll('<','\\u003c').replaceAll('>','\\u003e').replaceAll('&','\\u0026');
  const once=(needle,value)=>{if(source.split(needle).length!==2)throw Error('Pinned comparison binding changed');source=source.replace(needle,()=>value);};
  once("import { AbsoluteFill, useCurrentFrame } from 'remotion';","import { AbsoluteFill, useCurrentFrame, Img, staticFile, getInputProps, delayRender, continueRender, cancelRender } from 'remotion';");
  once('G, FakeDashboard','G');
  const picture='<FakeDashboard variant="A" />';
  if(source.split(picture).length!==3)throw Error('Pinned two-state source changed');
  source=source.replace(picture,'<Picture index={0} />').replace(picture,'<Picture index={1} />');
  once(", filter: 'blur(1.6px) saturate(0.18) contrast(0.72) brightness(1.04)'",'');
  const fog=source.match(/      <div style=\{\{ position: 'absolute', inset: 0, background: 'linear-gradient\(180deg, rgba\(214,212,206,0.30\), rgba\(196,194,188,0.38\)\)' \}\} \/>/);
  if(!fog)throw Error('Pinned demo fog changed');
  once(fog[0],'');
  once('<Tag label="Before" x={1372} muted />','<Tag label={'+quote(spec.before_label)+'} x={1500} muted />');
  once('<Tag label="After" x={646} accent />','<Tag label={'+quote(spec.after_label)+'} x={240} accent />');
  once('      top: 15,','      top: 980,');
  once('      height: 42,','      height: 64,');
  once('      borderRadius: 21,','      borderRadius: 32,');
  once('      fontFamily: FONT.sans,',"      fontFamily: 'EditorGPTVazir', direction:"+quote(spec.locale==='fa-IR'?'rtl':'ltr')+',');
  once('      fontSize: 20,','      fontSize: 40,');
  once('      letterSpacing: tracking(20, false),','      letterSpacing: 0,');
  once('      <Grain opacity={0.04} />',`      <div style={{position:'absolute',left:96,right:96,top:20,fontFamily:'EditorGPTVazir',fontSize:64,fontWeight:700,lineHeight:1.3,textAlign:'center',direction:${quote(spec.locale==='fa-IR'?'rtl':'ltr')},color:G.ink1}}>{${quote(spec.caption)}}</div>`);
  once('  const frame = useCurrentFrame();',`  const frame = useCurrentFrame();
  useCompareMetrics(${quote(spec.caption)},${quote([spec.before_label,spec.after_label])});`);
  const helper=`
const Picture: React.FC<{index:number}> = ({index}) => {
 const files=getInputProps<{scenes:{supporting_assets:string[]}[]}>().scenes[0].supporting_assets;
 if(!Array.isArray(files)||files.length!==2||!files.every(v=>/^support-0-[01]-[a-f0-9]+\\.png$/.test(v)))throw Error('Missing owned comparison states');
 return <Img src={staticFile(files[index])} style={{position:'absolute',left:0,top:120,width:1920,height:840,objectFit:'contain'}}/>;
};
`;
  const hook=require('node:path').join(__dirname,'src/shotcraft/useCompareMetrics');
  return 'import {useCompareMetrics} from '+quote(hook)+';\n'+source+helper+'\nexport default BeforeAfterSliderScrub;';
};
