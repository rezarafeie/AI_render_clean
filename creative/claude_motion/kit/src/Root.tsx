import React from 'react';
import {Composition} from 'remotion';
import {Main} from './Video';
import timing from './timing.json';
export const Root: React.FC = () => (
	<Composition id="Main" component={Main} durationInFrames={Math.max(1, Math.round(timing.total * timing.fps))} fps={timing.fps} width={timing.width} height={timing.height} />
);
