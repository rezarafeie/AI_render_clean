import React from 'react';
import {Composition} from 'remotion';
import {Premium} from './Premium';
import timing from './timing.json';
export const Root: React.FC = () => (
	<Composition id="Main" component={Premium} durationInFrames={Math.max(1, Math.round(timing.total * timing.fps))} fps={timing.fps} width={timing.width} height={timing.height} />
);
