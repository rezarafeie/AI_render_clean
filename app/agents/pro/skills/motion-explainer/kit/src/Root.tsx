import React from 'react';
import {Composition} from 'remotion';
import {Main} from './Video';
import timing from './timing.json';
export const Root: React.FC = () => (
	<Composition id="Main" component={Main} durationInFrames={Math.round(timing.total * 30)} fps={30} width={1080} height={1920} />
);
