// Fixed composition over the pinned original source. The compile-time loader
// binds validated content; upstream motion and geometry are not model-generated.
import React from 'react';
import {Composition, getInputProps, registerRoot, staticFile} from 'remotion';
import {FrameReady} from './shotcraft/FrameReady';
// @ts-expect-error Fixed webpack alias selects only a hash-verified local source.
import NativeComponent from 'editor-shotcraft-source';

type NativeProps = {width: number; height: number; font: string; scenes: {frames: number}[]};
const NativeScene: React.FC = () => {
  const {font} = getInputProps<NativeProps>();
  if (!/^[a-zA-Z0-9.-]+$/.test(font)) throw new Error('Invalid local font reference');
  const fontUrl = staticFile(font);
  return <>
    <style>{`@font-face{font-family:EditorGPTVazir;src:url(${JSON.stringify(fontUrl)});font-weight:400 900}`}</style>
    <FrameReady fontFamily="EditorGPTVazir"><NativeComponent/></FrameReady>
  </>;
};
const NativeRoot: React.FC = () => {
  const props = getInputProps<NativeProps>();
  return <Composition id="NativeShotcraft" component={NativeScene} width={props.width} height={props.height}
    fps={30} durationInFrames={props.scenes[0].frames}/>;
};
registerRoot(NativeRoot);
