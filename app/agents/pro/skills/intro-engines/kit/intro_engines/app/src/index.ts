import {registerRoot, Composition} from 'remotion';
import React from 'react';
import {Reel, REEL_DUR} from './Reel';
import {Story, STORY_DUR} from './Story';
import {Talk, TALK_DUR} from './Talk';
import {Film, FILM_DUR} from './Film';
registerRoot(() => React.createElement(React.Fragment, null,
  React.createElement(Composition, {id: 'Reel', component: Reel, durationInFrames: REEL_DUR * 60, fps: 60, width: 1920, height: 1080}),
  React.createElement(Composition, {id: 'Story', component: Story, durationInFrames: STORY_DUR * 30, fps: 30, width: 1080, height: 1920}),
  React.createElement(Composition, {id: 'Talk', component: Talk, durationInFrames: TALK_DUR * 30, fps: 30, width: 1920, height: 1080}),
  React.createElement(Composition, {id: 'Film', component: Film, durationInFrames: FILM_DUR * 24, fps: 24, width: 1920, height: 1080}),
));
