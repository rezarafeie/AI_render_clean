// Isolated original-code visual audit. Not a second production render service.
import fs from 'node:fs';
import path from 'node:path';
import http from 'node:http';
import crypto from 'node:crypto';
import {createRequire} from 'node:module';
import {fileURLToPath} from 'node:url';
const root=path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const {chromium}=createRequire(path.join(root,'web/package.json'))('playwright');
const vendor=path.join(root,'creative/lemo_data');
const manifest=JSON.parse(fs.readFileSync(path.join(vendor,'manifest.json'),'utf8'));
for(const [name,hash] of Object.entries(manifest.sha256)) {
  const source=path.resolve(vendor,name);
  if(!source.startsWith(vendor+path.sep)||crypto.createHash('sha256').update(fs.readFileSync(source)).digest('hex')!==hash) throw Error('Lemo source integrity mismatch');
}
const sourceRoot=path.join(vendor,'swiss-motion');
const preview=`<!doctype html><html><head><link rel="stylesheet" href="/fonts/fonts.css"><style>body{margin:0}canvas{display:block}</style></head><body><canvas id="c" width="1920" height="1080"></canvas><script type="module">
import {renderFilm,setScore,setLines,setWords,measureNumeral} from '/film.js';
const g=document.querySelector('canvas').getContext('2d');
await Promise.all(['300','400','500','600','700','800','900'].map(w=>document.fonts.load(w+' 40px Archivo')).concat([document.fonts.load('40px Fraktur'),document.fonts.load('40px DMSerif')]));
setScore(await (await fetch('/score.json')).json());setLines([],{});setWords({});measureNumeral(g);
window.draw=t=>renderFilm(g,t,{nosub:true});window.READY=true;
</script></body></html>`;
const server=http.createServer((req,res)=>{
  try {
    const requested=decodeURIComponent(new URL(req.url,'http://localhost').pathname);
    if(requested==='/'){res.setHeader('Content-Type','text/html');res.end(preview);return;}
    const file=path.resolve(sourceRoot,'.'+requested);
    if(!file.startsWith(sourceRoot+path.sep)||!fs.statSync(file).isFile()){res.writeHead(404).end();return;}
    res.setHeader('Content-Type',({'.js':'text/javascript','.json':'application/json','.css':'text/css','.ttf':'font/ttf'})[path.extname(file)]||'application/octet-stream');
    res.end(fs.readFileSync(file));
  } catch {res.writeHead(404).end();}
});
await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
let browser;
try {
  browser=await chromium.launch({channel:'chrome',headless:true});
  const page=await browser.newPage({viewport:{width:1920,height:1080}}),errors=[];
  page.on('pageerror',error=>errors.push(error.message));
  await page.goto('http://127.0.0.1:'+server.address().port+'/');
  await page.waitForFunction(()=>window.READY===true);
  const output=path.join(root,'web/public/creative-previews');
  let first;
  for(const time of [12,27,32,12]) {
    await page.evaluate(t=>window.draw(t),time);
    const frame=await page.locator('canvas').screenshot();
    const hash=crypto.createHash('sha256').update(frame).digest('hex');
    if(time===12&&first&&hash!==first) throw Error('Lemo backward seek changed pixels');
    if(time===12) first=hash;
    fs.writeFileSync(path.join(output,'lemo-swiss-motion-'+time+'.png'),frame);
  }
  if(errors.length) throw Error('Original demo runtime error');
  const item={id:'lemo:swiss-motion',name:'lemo-swiss-motion',poster:'/creative-previews/lemo-swiss-motion-27.png',status:'upstream-demo-checked',
    format:'horizontal',demonstration_only:true,production_template_ready:false,source_revision:manifest.revision,backward_seek_verified:true,
    use:'Original Swiss Canvas code, original licensed fonts, no narration. Demo storyline is fixed; user-content parameterization and portrait integration are not completed.'};
  fs.writeFileSync(path.join(output,'lemo.json'),JSON.stringify({schema_version:1,items:{[item.id]:item}},null,2));
  console.log(JSON.stringify({id:item.id,status:item.status,backward_seek_verified:true}));
} finally {
  if(browser) await browser.close();
  await new Promise(resolve=>server.close(resolve));
}
