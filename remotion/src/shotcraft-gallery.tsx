// Upstream demo compositions, not production content templates. Original pinned
// code executes unchanged. Keep this gallery entry separate from user jobs.
import React from 'react';
import {Composition, registerRoot, useCurrentFrame, delayRender, continueRender, cancelRender} from 'remotion';
import {CardStack, CARD_STACK_DURATION} from '../../creative/shotcraft_data/demos/ui-entrance/card-stack/CardStack';
import {TextColumnConverge, TEXT_COLUMN_CONVERGE_DURATION} from '../../creative/shotcraft_data/demos/typography/text-column-converge/TextColumnConverge';
import {TitleDemoteToLabel, TITLE_DEMOTE_TO_LABEL_DURATION} from '../../creative/shotcraft_data/demos/typography/title-demote-to-label/TitleDemoteToLabel';
import {BezierSourceConvergeMerge, BEZIER_SOURCE_CONVERGE_MERGE_DURATION} from '../../creative/shotcraft_data/demos/ui-entrance/bezier-source-converge-merge/BezierSourceConvergeMerge';
import {CardFlipReveal, CARD_FLIP_REVEAL_DURATION} from '../../creative/shotcraft_data/demos/transition/card-flip-reveal/CardFlipReveal';
import {CircleMatchIris, CIRCLE_MATCH_IRIS_DURATION} from '../../creative/shotcraft_data/demos/transition/circle-match-iris/CircleMatchIris';
import {BeforeAfterSliderScrub, BEFORE_AFTER_SLIDER_SCRUB_DURATION} from '../../creative/shotcraft_data/demos/data/before-after-slider-scrub/BeforeAfterSliderScrub';
import {AxisRescaleShockV2, AXIS_RESCALE_SHOCK_V2_DURATION} from '../../creative/shotcraft_data/demos/data/chart-live-moves/AxisRescaleShockV2';
import {OscilloscopeStreamV2, OSCILLOSCOPE_STREAM_V2_DURATION} from '../../creative/shotcraft_data/demos/data/chart-live-moves/OscilloscopeStreamV2';
import {UnitDotSwarmRegroupV2, UNIT_DOT_SWARM_REGROUP_V2_DURATION} from '../../creative/shotcraft_data/demos/data/chart-live-moves/UnitDotSwarmRegroupV2';

const entries = [
  ['card-stack', CardStack, CARD_STACK_DURATION],
  ['text-column-converge', TextColumnConverge, TEXT_COLUMN_CONVERGE_DURATION],
  ['title-demote-to-label', TitleDemoteToLabel, TITLE_DEMOTE_TO_LABEL_DURATION],
  ['bezier-source-converge-merge', BezierSourceConvergeMerge, BEZIER_SOURCE_CONVERGE_MERGE_DURATION],
  ['card-flip-reveal', CardFlipReveal, CARD_FLIP_REVEAL_DURATION],
  ['circle-match-iris', CircleMatchIris, CIRCLE_MATCH_IRIS_DURATION],
  ['before-after-slider-scrub', BeforeAfterSliderScrub, BEFORE_AFTER_SLIDER_SCRUB_DURATION],
  ['chart-axis-rescale', AxisRescaleShockV2, AXIS_RESCALE_SHOCK_V2_DURATION],
  ['chart-oscilloscope', OscilloscopeStreamV2, OSCILLOSCOPE_STREAM_V2_DURATION],
  ['chart-unit-regroup', UnitDotSwarmRegroupV2, UNIT_DOT_SWARM_REGROUP_V2_DURATION],
] as const;

// CSS background images are not Remotion <Img> nodes. Explicitly await their
// decoding before capturing each sampled frame; never use an arbitrary sleep.
const decodedTextures = new Map<string, Promise<void>>();
const FrameReady: React.FC<React.PropsWithChildren> = ({children}) => {
  const frame = useCurrentFrame();
  React.useLayoutEffect(() => {
    const handle = delayRender('Decode original demo textures and fonts');
    let released = false;
    const release = () => {if (!released) {released = true; continueRender(handle);}};
    const textures: Promise<void>[] = [];
    for (const element of document.querySelectorAll('*')) {
      const background = getComputedStyle(element).backgroundImage;
      for (const match of background.matchAll(/url\((?:"([^"]+)"|'([^']+)'|([^)]*))\)/g)) {
        const source = match[1] || match[2] || match[3];
        if (!source.startsWith('data:image/')) {cancelRender(new Error('Unapproved demo texture URL')); release(); return;}
        if (!decodedTextures.has(source)) {
          const image = new Image(); image.src = source;
          decodedTextures.set(source, image.decode());
        }
        textures.push(decodedTextures.get(source)!);
      }
    }
    Promise.all([document.fonts.ready, ...textures]).then(release, error => {
      if (!released) cancelRender(error instanceof Error ? error : new Error('Demo resource decoding failed'));
      release();
    });
    return release;
  }, [frame]);
  return <>{children}</>;
};

// Build wrappers once, not inside a rendering component.
const readyEntries = entries.map(([name, Component, duration]) => {
  const ReadyDemo: React.FC = () => <FrameReady><Component/></FrameReady>;
  return {name, ReadyDemo, duration};
});
registerRoot(() => <>{readyEntries.map(({name, ReadyDemo, duration}) =>
  <Composition key={name} id={'shotcraft-'+name} component={ReadyDemo} width={1920} height={1080} fps={30} durationInFrames={duration}/>)}</>);
