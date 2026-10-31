import React from 'react';
import {useCurrentFrame, delayRender, continueRender, cancelRender} from 'remotion';

// Only source-owned embedded textures are accepted. This is not a URL loader.
const decodedTextures = new Map<string, Promise<void>>();
export const FrameReady: React.FC<React.PropsWithChildren<{fontFamily?: string}>> = ({children, fontFamily}) => {
  const frame = useCurrentFrame();
  React.useLayoutEffect(() => {
    const handle = delayRender('Decode source textures and local fonts');
    let released = false;
    const release = () => {if (!released) {released = true; continueRender(handle);}};
    const textures: Promise<unknown>[] = [];
    for (const element of document.querySelectorAll('*')) {
      const background = getComputedStyle(element).backgroundImage;
      for (const match of background.matchAll(/url\((?:"([^"]+)"|'([^']+)'|([^)]*))\)/g)) {
        const source = match[1] || match[2] || match[3];
        if (!source.startsWith('data:image/')) {cancelRender(new Error('Unapproved source texture URL')); release(); return;}
        if (!decodedTextures.has(source)) {
          const image = new Image(); image.src = source;
          decodedTextures.set(source, image.decode());
        }
        textures.push(decodedTextures.get(source)!);
      }
    }
    if (fontFamily) textures.push(document.fonts.load('600 40px ' + fontFamily));
    Promise.all([document.fonts.ready, ...textures]).then(release, error => {
      if (!released) cancelRender(error instanceof Error ? error : new Error('Source resource decoding failed'));
      release();
    });
    return release;
  }, [frame, fontFamily]);
  return <>{children}</>;
};
