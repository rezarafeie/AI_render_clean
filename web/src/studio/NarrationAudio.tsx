import React from "react";
import { AuthenticatedMedia } from "../AuthenticatedMedia";

/** The narration take of a step, playable from its log (loaded only when a step has one). */
export default function NarrationAudio({ src }: { src: string }) {
  return <AuthenticatedMedia as="audio" controls preload="none" src={src}/>;
}
