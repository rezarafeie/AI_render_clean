import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import {bundle} from "@remotion/bundler";
import {renderMedia, selectComposition} from "@remotion/renderer";
import {nativeShotcraftBundle} from './shotcraft-native-config.mjs';

const [configFile, outputFile] = process.argv.slice(2);
if (!configFile || !outputFile) throw new Error("Usage: npm run render -- config.json output.mp4");
const inputProps = JSON.parse(fs.readFileSync(configFile, "utf8"));
const publicDir = fs.mkdtempSync(path.join(os.tmpdir(), "editorgpt-remotion-"));
const copyAsset = (value, label) => {
  if (!value) return null;
  const ext = path.extname(value) || ".bin";
  const name = `${label}-${Math.random().toString(16).slice(2)}${ext}`;
  fs.copyFileSync(value, path.join(publicDir, name));
  return name;
};
inputProps.scenes = inputProps.scenes.map((scene, index) => ({
  ...scene,
  asset: copyAsset(scene.asset, `visual-${index}`),
  narration: copyAsset(scene.narration, `voice-${index}`),
  supporting_assets: (scene.supporting_assets || []).map((asset, assetIndex) => copyAsset(asset, `support-${index}-${assetIndex}`)),
}));
inputProps.music = copyAsset(inputProps.music, "music");
inputProps.font = copyAsset(inputProps.font, "font");

let nativeBundleDir;
try {
  const native = inputProps.version === 3;
  const macChrome='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
  const browserExecutable=process.env.REMOTION_BROWSER_EXECUTABLE || (native&&process.platform==='darwin'&&fs.existsSync(macChrome)?macChrome:undefined);
  const nativeBrowserPolicy=native?{onBrowserDownload:()=>{throw Error('Install/configure the render browser before using native Shotcraft; runtime downloads are disabled.');}}:{};
  const nativeConfig = native ? nativeShotcraftBundle(inputProps) : null;
  if (native) nativeBundleDir = fs.mkdtempSync(path.join(os.tmpdir(), 'editorgpt-shotcraft-bundle-'));
  const serveUrl = await bundle({...(nativeConfig || {entryPoint:path.resolve("src/index.jsx")}), publicDir,
    ...(native ? {outDir:nativeBundleDir,enableCaching:false} : {})});
  const composition = await selectComposition({serveUrl, id: native ? 'NativeShotcraft' : inputProps.version === 2 ? "DirectedReel" : "ProductReel", inputProps,
    browserExecutable,...nativeBrowserPolicy});
  await renderMedia({
    composition, serveUrl, inputProps, outputLocation: outputFile,
    codec: "h264", crf: 18, pixelFormat: "yuv420p", audioCodec: "aac",
    browserExecutable,...nativeBrowserPolicy,
    ...(native?{gopSize:30,colorSpace:'bt709'}:{}),
    concurrency: Number(process.env.REMOTION_CONCURRENCY || 2),
    onProgress: ({progress}) => console.log(`REMOTION_PROGRESS ${Math.round(progress * 100)}`),
  });
} finally {
  fs.rmSync(publicDir, {recursive: true, force: true});
  if (nativeBundleDir) fs.rmSync(nativeBundleDir, {recursive: true, force: true});
}
