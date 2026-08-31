export const FPS = 30;
export const TRANSITION_FRAMES = 18;

export const scenes = {
  opening: 22,
  problem: 30,
  pipeline: 34,
  dashboard: 54,
  evidence: 42,
  results: 32,
  engineering: 28,
  boundary: 22,
  closing: 16,
} as const;

export const totalFrames = Object.values(scenes).reduce((a, b) => a + b, 0) * FPS - 8 * TRANSITION_FRAMES;
