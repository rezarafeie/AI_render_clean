// Compile-time binding over a hash-verified, fixed source. No generated code,
// arbitrary module names, imports, URLs or shell commands are accepted.
module.exports = function(source) {
  const {spec, width, height, frames} = this.getOptions();
  if(spec.resource_id !== 'shotcraft:bezier-source-converge-merge') throw Error('Unsupported native Shotcraft source');
  if(typeof spec.caption !== 'string' || !spec.caption.trim() || spec.caption.length > 48) throw Error('Invalid caption');
  if(!/^#[0-9a-fA-F]{6}$/.test(spec.accent)) throw Error('Invalid accent');
  if(!Array.isArray(spec.source_icons) || spec.source_icons.length !== 4 || spec.source_icons.some(v=>!['shot','card','code','wave'].includes(v))) throw Error('Invalid source icons');
  const marks = {check:'M5 12l4 4L19 6',play:'M8 5l11 7-11 7z',spark:'M12 3l2.4 6.6L21 12l-6.6 2.4L12 21l-2.4-6.6L3 12l6.6-2.4z'};
  if(!Object.hasOwn(marks,spec.output_icon)) throw Error('Invalid output icon');
  if(!['fa-IR','en-US'].includes(spec.locale)) throw Error('Invalid locale');
  if(![1080,1920].includes(width) || ![1080,1920].includes(height)) throw Error('Invalid stage dimensions');
  const words=spec.caption.trim().split(/\s+/).length;
  if(words>8 || /[<>]/.test(spec.caption)) throw Error('Use bounded complete plain words');
  const hold=Math.max(1.2,words/2.5);
  if(!Number.isInteger(frames)||frames/30<Math.max(4,2.4+hold)||frames>360) throw Error('Caption needs a complete motion phase and reading hold');
  const quote = value => JSON.stringify(value).replaceAll('<','\\u003c').replaceAll('>','\\u003e').replaceAll('&','\\u0026');
  const once = (needle,value) => {
    if(source.split(needle).length !== 2) throw Error('Pinned source binding changed');
    source=source.replace(needle,()=>value);
  };
  once("const CAP_WORDS = 'From screenshot to showreel'.split(' ');", 'const CAP_WORDS = '+quote(spec.caption)+".trim().split(/\\s+/);");
  // Trim only the source's empty pre-roll. Start with visible source nodes;
  // preserve its convergence, erase, camera pan and explicit final reading hold.
  once('const t = useT();', 'const t = 0.2 + 0.8 * Math.min(1, useT() / '+((frames/30-hold)/(frames/30))+');');
  once("const SANS = FONT.sans;", "const SANS = 'EditorGPTVazir, Arial, sans-serif';");
  once("const ACCENT = '#5b63d3';", 'const ACCENT = '+quote(spec.accent)+';');
  const high='#'+[1,3,5].map(i=>Math.round(parseInt(spec.accent.slice(i,i+2),16)*.75+255*.25).toString(16).padStart(2,'0')).join('');
  once("const ACCENT_HI = '#7d84ea';", 'const ACCENT_HI = '+quote(high)+';');
  const original = source.match(/const SRCS = \[[\s\S]*?\];/);
  if(!original) throw Error('Pinned source list changed');
  once(original[0], 'const SRCS = '+quote(spec.source_icons.map((icon,i)=>({y:[36,92,148,204][i],icon,c:['#2a2c33','#4b4e57','#6d7079','#8f929c'][i]})))+';');
  once("import { ShotcraftMark } from '../../_fixtures/Brand';", '');
  once('<ShotcraftMark size={MARK_SIZE} tone="light" />', '<svg width={MARK_SIZE} height={MARK_SIZE} viewBox="0 0 24 24" fill="none" stroke={ACCENT} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d='+quote(marks[spec.output_icon])+'/></svg>');
  once('<DesignStage bg="transparent">', '<DesignStage bg="transparent" h={'+(480*height/width)+'}>');
  once('left: XC - 120,', 'left: XC - 180,');
  once('width: 240,', 'width: 360,');
  once("whiteSpace: 'nowrap',", "whiteSpace: 'normal', flexWrap: 'wrap', direction: "+quote(spec.locale==='fa-IR'?'rtl':'ltr')+', rowGap: 4,');
  once('font: `600 13px/1.25 ${SANS}`,', 'font: `600 18px/1.5 ${SANS}`,');
  once("letterSpacing: (-0.012 - 0.02 * (1 - q)).toFixed(4) + 'em',", 'letterSpacing: 0,');
  once('marginRight: i === CAP_WORDS.length - 1 ? 0 : 4,', 'marginInlineEnd: i === CAP_WORDS.length - 1 ? 0 : 4,');
  return source+'\nexport default BezierSourceConvergeMerge;';
};
