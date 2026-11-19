import React from "react";
import AudioPlayer from "./AudioPlayer";

/** The narration take of a step, playable right in its step (loaded only when a step has one). */
export default function NarrationAudio({ src, title = "نریشن" }: { src: string; title?: string }) {
  return <AudioPlayer src={src} title={title}/>;
}
