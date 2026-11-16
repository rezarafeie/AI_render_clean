// One composition, "Main": the intro template named by content.json's `kind`, at the size and frame rate of timing.json.
import React from 'react';
import {registerRoot, Composition} from 'remotion';
import timing from './timing.json';
import content from './content.json';
import {Story} from './Story';
import {Reel} from './Reel';
import {Talk} from './Talk';
import {Film} from './Film';

const KINDS: Record<string, React.FC> = {story: Story, reel: Reel, presenter: Talk, film3d: Film};
const t = timing as {total: number; fps: number; width: number; height: number};
registerRoot(() => React.createElement(Composition, {id: 'Main', component: KINDS[(content as any).kind] ?? Story,
	durationInFrames: Math.max(1, Math.round(t.total * t.fps)), fps: t.fps, width: t.width, height: t.height}));
