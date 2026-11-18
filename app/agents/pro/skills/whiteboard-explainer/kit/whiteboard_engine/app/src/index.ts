import {registerRoot, Composition} from 'remotion';
import React from 'react';
import {WB, DURATION} from './WB';
registerRoot(() => React.createElement(Composition, {id: 'WB', component: WB, durationInFrames: DURATION, fps: 30, width: 1080, height: 1920}));
