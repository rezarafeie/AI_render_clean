import React from "react";
import { api } from "../api";
import { AuthenticatedMedia } from "../AuthenticatedMedia";
import { faNumber, formatDuration } from "../format";
import type { PreparedAsset } from "./model";

/** The files a step prepared, scene by scene: pictures, narration and clips, each one playable. */
export default function AssetList({ assets, projectId }: { assets: PreparedAsset[]; projectId?: string }) {
  if (!assets.length || !projectId) return null;
  const scenes = [...new Set(assets.map(asset => asset.scene))].sort((a, b) => a - b);
  return <section className="act-io act-assets"><h5>فایل‌های آماده</h5>
    {scenes.map(scene => <div key={scene} className="act-asset-row">
      <b>صحنهٔ {faNumber(scene)}</b>
      <div className="act-asset-files">
        {assets.filter(asset => asset.scene === scene).map(asset => {
          const src = api.studioJobFileUrl(projectId, asset.file);
          return <figure key={asset.file} className={`act-asset act-asset-${asset.kind}`}>
            {asset.kind === "image" ? <AuthenticatedMedia as="img" src={src} alt={asset.label} loading="lazy"/>
              : asset.kind === "audio" ? <AuthenticatedMedia as="audio" controls preload="none" src={src}/>
              : <AuthenticatedMedia as="video" controls muted playsInline preload="metadata" src={src}/>}
            <figcaption dir="auto">{asset.label}{typeof asset.duration_s === "number" ? ` · ${formatDuration(asset.duration_s * 1000, true)}` : ""}</figcaption>
          </figure>;
        })}
      </div>
    </div>)}
  </section>;
}

