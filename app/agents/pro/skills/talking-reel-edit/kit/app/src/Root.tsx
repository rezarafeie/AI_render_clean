import React from 'react';
import {Composition} from 'remotion';
import {Edit} from './Edit';
import data from './data.json';
export const Root: React.FC = () => <Composition id="Edit" component={Edit} durationInFrames={Math.round(data.total * 30)} fps={30} width={1080} height={1920} />;
