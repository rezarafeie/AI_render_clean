// Existing Remotion renderer/bundler, no new runtime or user-controlled imports.
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import os from 'node:os';
import {fileURLToPath} from 'node:url';
import {bundle} from '@remotion/bundler';
import {getCompositions, renderStill} from '@remotion/renderer';

const here=path.dirname(fileURLToPath(import.meta.url)),root=path.dirname(here);
const data=path.join(root,'creative/shotcraft_data');
for(const filename of ['manifest.json','runtime_sha256.json']) {
  const manifest=JSON.parse(fs.readFileSync(path.join(data,filename),'utf8'));
  if(manifest.revision!=='5a2e98daade313c4f376120f38427eb19a108e8c') throw Error('Unreviewed Shotcraft revision');
  for(const [name,hash] of Object.entries(manifest.sha256)) {
    const file=path.resolve(data,name);
    if(!file.startsWith(data+path.sep)) throw Error('Source path escape');
    if(crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex')!==hash) throw Error('Source integrity failed: '+name);
  }
}
const output=path.join(root,'web/public/creative-previews');
fs.mkdirSync(output,{recursive:true});
const nodeModules=path.join(here,'node_modules');
const serveUrl=await bundle({entryPoint:path.join(here,'src/shotcraft-gallery.tsx'),
  webpackOverride:config=>({...config,resolve:{...config.resolve,modules:[nodeModules,...(config.resolve?.modules||[])]}})});
const browserExecutable=process.env.REMOTION_BROWSER_EXECUTABLE||'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
const compositions=await getCompositions(serveUrl,{browserExecutable});
const only=process.argv[2];
if(only&&!compositions.some(c=>c.id===only)) throw Error('Unknown gallery composition');
const items=only?JSON.parse(fs.readFileSync(path.join(output,'shotcraft.json'),'utf8')).items:{};
for(const composition of compositions.filter(c=>!only||c.id===only)) {
  const name=composition.id;
  try {
    const sample=Math.floor(composition.durationInFrames/2);
    let repeated,firstBuffer;
    for(const frame of [sample,0,composition.durationInFrames-2,sample]) {
      const {buffer}=await renderStill({serveUrl,composition,frame,output:null,browserExecutable,imageFormat:'png'});
      if(!buffer) throw Error('Missing rendered frame');
      const hash=crypto.createHash('sha256').update(buffer).digest('hex');
      if(frame===sample&&repeated&&hash!==repeated) {
        const evidence=fs.mkdtempSync(path.join(os.tmpdir(),'shotcraft-determinism-'));
        fs.writeFileSync(path.join(evidence,'first.png'),firstBuffer);
        fs.writeFileSync(path.join(evidence,'repeated.png'),buffer);
        console.log(JSON.stringify({id:name,evidence}));
        throw Error('Repeated frame is not deterministic');
      }
      if(frame===sample) {repeated=hash;firstBuffer=buffer;}
      if(frame===composition.durationInFrames-2) fs.writeFileSync(path.join(output,name+'.png'),buffer);
    }
    items[name]={id:name,name,status:'upstream-demo-checked',poster:'/creative-previews/'+name+'.png',
      format:'horizontal',demonstration_only:true,production_template_ready:false,
      repeated_frame_verified:true,sampled_frames:[0,sample,composition.durationInFrames-2],
      source_revision:'5a2e98daade313c4f376120f38427eb19a108e8c',
      use:'Original upstream demo; demo branding/copy and synthetic data are not user content. Typed content binding and portrait adaptation remain required.'};
    console.log(JSON.stringify({id:name,status:'upstream-demo-checked'}));
  } catch(error) {
    items[name]={id:name,name,status:'failed',poster:null,error:error.name};
    console.log(JSON.stringify({id:name,status:'failed',error:error.message}));
  }
  fs.writeFileSync(path.join(output,'shotcraft.json'),JSON.stringify({schema_version:1,items},null,2));
}
if(Object.values(items).some(item=>item.status==='failed')) process.exitCode=1;
