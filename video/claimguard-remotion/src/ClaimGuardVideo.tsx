import React from 'react';
import {TransitionSeries, linearTiming} from '@remotion/transitions';
import {fade} from '@remotion/transitions/fade';
import {wipe} from '@remotion/transitions/wipe';
import {Opening} from './scenes/Opening';
import {Problem} from './scenes/Problem';
import {Pipeline} from './scenes/Pipeline';
import {Dashboard} from './scenes/Dashboard';
import {Evidence} from './scenes/Evidence';
import {Results} from './scenes/Results';
import {Engineering} from './scenes/Engineering';
import {Boundary} from './scenes/Boundary';
import {Closing} from './scenes/Closing';
import {FPS, scenes, TRANSITION_FRAMES} from './timing';

const d = (seconds: number) => seconds * FPS;
const transition = linearTiming({durationInFrames: TRANSITION_FRAMES});

export const ClaimGuardVideo: React.FC = () => (
  <TransitionSeries>
    <TransitionSeries.Sequence durationInFrames={d(scenes.opening)}><Opening /></TransitionSeries.Sequence>
    <TransitionSeries.Transition presentation={fade()} timing={transition} />
    <TransitionSeries.Sequence durationInFrames={d(scenes.problem)}><Problem /></TransitionSeries.Sequence>
    <TransitionSeries.Transition presentation={wipe({direction: 'from-left'})} timing={transition} />
    <TransitionSeries.Sequence durationInFrames={d(scenes.pipeline)}><Pipeline /></TransitionSeries.Sequence>
    <TransitionSeries.Transition presentation={fade()} timing={transition} />
    <TransitionSeries.Sequence durationInFrames={d(scenes.dashboard)}><Dashboard /></TransitionSeries.Sequence>
    <TransitionSeries.Transition presentation={wipe({direction: 'from-bottom-left'})} timing={transition} />
    <TransitionSeries.Sequence durationInFrames={d(scenes.evidence)}><Evidence /></TransitionSeries.Sequence>
    <TransitionSeries.Transition presentation={fade()} timing={transition} />
    <TransitionSeries.Sequence durationInFrames={d(scenes.results)}><Results /></TransitionSeries.Sequence>
    <TransitionSeries.Transition presentation={wipe({direction: 'from-right'})} timing={transition} />
    <TransitionSeries.Sequence durationInFrames={d(scenes.engineering)}><Engineering /></TransitionSeries.Sequence>
    <TransitionSeries.Transition presentation={fade()} timing={transition} />
    <TransitionSeries.Sequence durationInFrames={d(scenes.boundary)}><Boundary /></TransitionSeries.Sequence>
    <TransitionSeries.Transition presentation={fade()} timing={transition} />
    <TransitionSeries.Sequence durationInFrames={d(scenes.closing)}><Closing /></TransitionSeries.Sequence>
  </TransitionSeries>
);
