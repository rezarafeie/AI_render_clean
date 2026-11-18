import {registerRoot} from 'remotion';
import React from 'react';
import {Composition} from 'remotion';
import {Reel} from './Reel';
import data from './data.json';
const Root: React.FC = () => React.createElement(Composition, {id: 'Reel', component: Reel, durationInFrames: Math.round(data.total * 30), fps: 30, width: 1080, height: 1920});
registerRoot(Root);
