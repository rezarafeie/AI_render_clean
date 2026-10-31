import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import {fileURLToPath} from 'node:url';

const here=path.dirname(fileURLToPath(import.meta.url));
const root=path.dirname(here), data=path.join(root,'creative/shotcraft_data');
const sources={
  'shotcraft:bezier-source-converge-merge':['demos/ui-entrance/bezier-source-converge-merge/BezierSourceConvergeMerge.tsx','shotcraft-content-loader.cjs'],
  'shotcraft:text-column-converge':['demos/typography/text-column-converge/TextColumnConverge.tsx','shotcraft-text-loader.cjs'],
  'shotcraft:card-flip-reveal':['demos/transition/card-flip-reveal/CardFlipReveal.tsx','shotcraft-card-loader.cjs'],
  'shotcraft:before-after-slider-scrub':['demos/data/before-after-slider-scrub/BeforeAfterSliderScrub.tsx','shotcraft-compare-loader.cjs'],
};

export function nativeShotcraftBundle(inputProps) {
  const {width,height,scenes}=inputProps;
  if(![[1080,1920],[1920,1080],[1080,1080]].some(([w,h])=>w===width&&h===height)||!Array.isArray(scenes)||scenes.length!==1) throw Error('Invalid native stage');
  if(!Number.isInteger(scenes[0].frames)||scenes[0].frames<120||scenes[0].frames>360) throw Error('Native duration requires 4–12 seconds');
  const spec=scenes[0].shotcraft;
  if(!spec||!Object.hasOwn(sources,spec.resource_id)) throw Error('Unsupported native resource');
  for(const filename of ['manifest.json','runtime_sha256.json']) {
    const manifest=JSON.parse(fs.readFileSync(path.join(data,filename),'utf8'));
    if(manifest.revision!=='5a2e98daade313c4f376120f38427eb19a108e8c') throw Error('Unreviewed Shotcraft revision');
    for(const [name,hash] of Object.entries(manifest.sha256)) {
      const file=path.resolve(data,name);
      if(!file.startsWith(data+path.sep)||crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex')!==hash) throw Error('Shotcraft source integrity failure');
    }
  }
  const [relativeSource,loader]=sources[spec.resource_id];
  const source=path.join(data,relativeSource);
  return {
    entryPoint:path.join(here,'src/shotcraft-native.tsx'),
    webpackOverride:config=>({...config,
      resolve:{...config.resolve,alias:{...config.resolve?.alias,'editor-shotcraft-source':source},modules:[path.join(here,'node_modules'),...(config.resolve?.modules||[])]},
      module:{...config.module,rules:[{test:/\.tsx$/,include:[source],enforce:'pre',use:[{
        loader:path.join(here,loader),options:{spec,width,height,frames:scenes[0].frames},
      }]},...(config.module?.rules||[])]},
    }),
  };
}
