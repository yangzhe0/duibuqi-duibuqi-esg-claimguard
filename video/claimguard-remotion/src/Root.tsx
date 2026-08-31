import React from 'react';
import {Composition} from 'remotion';
import {ClaimGuardVideo} from './ClaimGuardVideo';
import {FPS, totalFrames} from './timing';

export const Root: React.FC = () => (
  <Composition
    id="ClaimGuardSilent"
    component={ClaimGuardVideo}
    durationInFrames={totalFrames}
    fps={FPS}
    width={1920}
    height={1080}
  />
);
