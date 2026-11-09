import React from "react";
import { api } from "../api";
import { AuthenticatedMedia } from "../AuthenticatedMedia";
import { Icon } from "../components/Icon";
import { faNumber, formatDuration } from "../format";
import type { PreparedAsset } from "./model";

/** A clip as a still thumbnail (its first frames) that plays in place when clicked. */
function ClipThumb({ src, label }: { src: string; label: string }) {
  const video = React.useRef<HTMLVideoElement>(null);
  const [playing, setPlaying] = React.useState(false);
  const toggle = () => {
    const element = video.current;
    if (!element) return;
    if (element.paused) { void element.play(); } else { element.pause(); }
  };
  return <button type="button" className="act-thumb act-clip" aria-label={label} onClick={toggle}>
    <AuthenticatedMedia as="video" ref={video} muted playsInline preload="metadata" src={src}
      onLoadedMetadata={(event: React.SyntheticEvent<HTMLVideoElement>) => { if (!playing) event.currentTarget.currentTime = 0.6; }}
      onPlay={() => setPlaying(true)} onPause={() => setPlaying(false)} onEnded={() => setPlaying(false)}/>
    {playing ? null : <span className="act-play" aria-hidden="true"><Icon name="play" size={16}/></span>}
  </button>;
}

/** The files a step prepared, scene by scene: small thumbnails of pictures and clips (a clip plays when clicked) and a slim narration player. */
export default function AssetList({ assets, projectId }: { assets: PreparedAsset[]; projectId: string }) {
  const scenes = [...new Set(assets.map(asset => asset.scene))].sort((a, b) => a - b);
  return <section className="act-io act-assets"><h5>فایل‌های آماده</h5>
    {scenes.map(scene => {
      const mine = assets.filter(asset => asset.scene === scene);
      const visuals = mine.filter(asset => asset.kind !== "audio");
      const voices = mine.filter(asset => asset.kind === "audio");
      return <div key={scene} className="act-asset-row">
        <b>{mine[0]?.group || `صحنهٔ ${faNumber(scene)}`}</b>
        <div className="act-thumbs">
          {visuals.map(asset => {
            const src = api.studioJobFileUrl(projectId, asset.src);
            const caption = asset.label + (typeof asset.duration_s === "number" ? ` · ${formatDuration(asset.duration_s * 1000, true)}` : "");
            return <figure key={asset.src} className="act-asset">
              {asset.kind === "image"
                ? <span className="act-thumb"><AuthenticatedMedia as="img" src={src} alt={asset.label} loading="lazy"/></span>
                : <ClipThumb src={src} label={caption}/>}
              <figcaption dir="auto">{caption}</figcaption>
            </figure>;
          })}
        </div>
        {voices.map(asset => <div key={asset.src} className="act-voice">
          <AuthenticatedMedia as="audio" controls preload="none" src={api.studioJobFileUrl(projectId, asset.src)}/>
          {asset.text ? <small dir="auto">{asset.text}</small> : null}
        </div>)}
      </div>;
    })}
  </section>;
}
