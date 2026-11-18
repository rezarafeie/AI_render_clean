import {registerRoot, Composition} from 'remotion';
import React from 'react';
import {Vox} from './Vox';
import data from './data.json';
registerRoot(() => React.createElement(Composition, {id: 'Vox', component: Vox, durationInFrames: Math.round(data.total * 30), fps: 30, width: 1080, height: 1920}));
