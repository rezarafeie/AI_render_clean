import React from 'react';
import {Composition} from 'remotion';
import {Edit} from './Edit';
import timing from './timing.json';
export const Root: React.FC = () => (
	<Composition id="Main" component={Edit} durationInFrames={Math.max(1, Math.round(timing.total * timing.fps))} fps={timing.fps} width={timing.width} height={timing.height} />
);
