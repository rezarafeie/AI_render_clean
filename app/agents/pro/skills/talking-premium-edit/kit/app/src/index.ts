import {registerRoot, Composition} from 'remotion';
import React from 'react';
import {V3} from './V3';
import data from './data.json';
registerRoot(() => React.createElement(Composition, {id: 'V3', component: V3, durationInFrames: Math.round(data.total * 30), fps: 30, width: 1080, height: 1920}));
