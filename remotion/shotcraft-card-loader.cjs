// Reviewed data binding only. The pinned upstream flip/lighting/reflection code stays intact.
module.exports=function(source){
  const {spec,width,height,frames}=this.getOptions();
  const plain=(s,n)=>typeof s==='string'&&s.trim()&&s.length<=n&&!/[<>\n\r]/.test(s);
  if(spec.resource_id!=='shotcraft:card-flip-reveal'||width!==1920||height!==1080||!['fa-IR','en-US'].includes(spec.locale))throw Error('Unsupported card-flip stage');
  for(const [key,n] of Object.entries({caption:48,kicker:24,front_label:12,before_label:12,after_label:12}))if(!plain(spec[key],n))throw Error('Invalid card-flip copy');
  if(!Array.isArray(spec.cards)||spec.cards.length!==3)throw Error('Exactly three cards required');
  for(const card of spec.cards){
    for(const [key,n] of Object.entries({name:20,description:48,unit:8,result_label:32,evidence:160}))if(!plain(card[key],n))throw Error('Invalid card content');
    if(!Array.isArray(card.front_lines)||card.front_lines.length!==3||card.front_lines.some(v=>!plain(v,24)))throw Error('Invalid card lines');
    if([card.before,card.after].some(v=>typeof v!=='number'||!Number.isFinite(v)||v<0||v>999.99))throw Error('Invalid explicit comparison');
  }
  // Read the densest front before beginning the original, unchanged 4+16f flip.
  const frontFrames=Math.max(60,...spec.cards.map(c=>Math.ceil([c.name,c.description,...c.front_lines].join(' ').trim().split(/\s+/).length/2.5*30)));
  const backFrames=Math.max(40,...spec.cards.map(c=>Math.ceil([c.name,c.result_label,spec.before_label,spec.after_label,c.unit].join(' ').trim().split(/\s+/).length/2.5*30)));
  if(!Number.isInteger(frames)||frames<frontFrames+50+backFrames||frames>360)throw Error('Card-flip requires front and result reading holds');
  const quote=v=>JSON.stringify(v).replaceAll('<','\\u003c').replaceAll('>','\\u003e').replaceAll('&','\\u0026');
  const once=(needle,value)=>{if(source.split(needle).length!==2)throw Error('Pinned card binding changed');source=source.replace(needle,()=>value);};
  const locale=spec.locale==='fa-IR'?'fa-IR':'en-US';
  const number=new Intl.NumberFormat(locale,{maximumFractionDigits:2});
  const features=spec.cards.map(c=>({name:c.name,desc:c.description,lines:c.front_lines,value:number.format(c.after),label:c.result_label,
    bars:[c.before/Math.max(c.before,c.after,1e-9),c.after/Math.max(c.before,c.after,1e-9)],unit:[c.before,c.after].map(v=>number.format(v)+' '+c.unit)}));
  const list=source.match(/const FEATURES = \[[\s\S]*?\];/);
  if(!list)throw Error('Pinned features changed');
  once(list[0],'const FEATURES = '+quote(features)+';');
  const front=source.match(/const FrontUI:[\s\S]*?\n};/);
  if(!front)throw Error('Pinned front changed');
  once(front[0],`const FrontUI: React.FC<{i:number;frame:number}> = ({i}) => (
    <div style={{fontFamily:'EditorGPTVazir',fontSize:32,lineHeight:1.7,color:L.ink,direction:${quote(locale==='fa-IR'?'rtl':'ltr')}}}>
      {FEATURES[i].lines.map((line,k)=><div key={k} style={{marginBottom:12}}>{line}</div>)}
    </div>
  );`);
  once('springAt, type }','springAt, type as upstreamType }');
  once("import { BRAND } from '../../_fixtures/Brand';",`const type: typeof upstreamType = (...args) => ({...upstreamType(...args),fontFamily:'EditorGPTVazir',letterSpacing:0,direction:${quote(locale==='fa-IR'?'rtl':'ltr')}});`);
  once('const FLIP0 = 22;','const FLIP0 = '+frontFrames+';');
  once('>Feature</div>','>{'+quote(spec.front_label)+'}</div>');
  once("(['Before', `With ${BRAND.short}`] as const)",'('+quote([spec.before_label,spec.after_label])+')');
  once('text={`${BRAND.name} · Launch results`}','text={'+quote(spec.kicker)+'}');
  once('text="Three features. Three outcomes."','text={'+quote(spec.caption)+'}');
  source=source.replaceAll('fontFamily: FONT.sans',"fontFamily: 'EditorGPTVazir'").replaceAll('fontFamily: FONT.mono',"fontFamily: 'EditorGPTVazir'");
  source=source.replaceAll("letterSpacing: '0.16em'",'letterSpacing: 0').replaceAll("letterSpacing: '0.14em'",'letterSpacing: 0').replaceAll("letterSpacing: '0.18em'",'letterSpacing: 0');
  once('...type(158, 800)', '...type(120, 800)');
  once("letterSpacing: '-0.06em', lineHeight: 0.9",'letterSpacing: 0, lineHeight: 1.2');
  once('...type(28, 450)','...type(32, 450)');
  return source+'\nexport default CardFlipReveal;';
};
