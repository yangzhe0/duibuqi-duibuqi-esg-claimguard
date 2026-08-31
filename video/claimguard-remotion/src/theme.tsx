import React from 'react';
import {AbsoluteFill, Easing, interpolate, useCurrentFrame, useVideoConfig} from 'remotion';

export const C = {
  ink: '#102d25',
  green: '#0b6b4b',
  green2: '#34a979',
  mint: '#dff3e9',
  pale: '#f4f8f6',
  gold: '#f0b54d',
  red: '#c45550',
  white: '#ffffff',
  grey: '#64746e',
};

export const font = 'Noto Sans CJK SC, Noto Sans SC, Source Han Sans SC, sans-serif';

export const Background: React.FC<{children: React.ReactNode; dark?: boolean}> = ({children, dark}) => {
  const frame = useCurrentFrame();
  return (
    <AbsoluteFill
      style={{
        background: dark
          ? 'radial-gradient(circle at 78% 20%, #15845d 0%, #0b523d 32%, #092c24 76%)'
          : 'radial-gradient(circle at 82% 12%, #d9f1e6 0%, #f6faf8 38%, #edf5f1 100%)',
        color: dark ? C.white : C.ink,
        fontFamily: font,
        overflow: 'hidden',
      }}
    >
      <div style={{position: 'absolute', inset: -250, opacity: dark ? 0.13 : 0.24, rotate: `${frame * 0.015}deg`, background: 'repeating-radial-gradient(circle at center, transparent 0 90px, #5fb892 92px 94px)'}} />
      {children}
    </AbsoluteFill>
  );
};

export const Brand: React.FC<{light?: boolean; section?: string}> = ({light, section}) => (
  <div style={{position: 'absolute', left: 78, top: 48, display: 'flex', alignItems: 'center', gap: 18, zIndex: 20}}>
    <div style={{width: 18, height: 18, borderRadius: 6, background: C.green2, boxShadow: `0 0 0 7px ${light ? '#ffffff20' : '#0b6b4b18'}`}} />
    <div style={{fontSize: 22, fontWeight: 800, letterSpacing: 3, color: light ? C.white : C.ink}}>ESG CLAIMGUARD</div>
    {section ? <div style={{fontSize: 20, color: light ? '#cde7db' : C.grey}}>／ {section}</div> : null}
  </div>
);

export const SceneTitle: React.FC<{eyebrow: string; title: string; subtitle?: string; light?: boolean}> = ({eyebrow, title, subtitle, light}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const opacity = interpolate(frame, [0, fps * 0.65], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing: Easing.bezier(0.16, 1, 0.3, 1)});
  const translate = interpolate(frame, [0, fps * 0.8], ['0px 36px', '0px 0px'], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing: Easing.bezier(0.16, 1, 0.3, 1)});
  return (
    <div style={{opacity, translate, position: 'absolute', left: 90, top: 150, zIndex: 12, maxWidth: 1040}}>
      <div style={{fontSize: 24, fontWeight: 800, letterSpacing: 5, color: light ? '#76d0aa' : C.green2, marginBottom: 18}}>{eyebrow}</div>
      <div style={{fontSize: 80, lineHeight: 1.08, fontWeight: 900, letterSpacing: -3, color: light ? C.white : C.ink}}>{title}</div>
      {subtitle ? <div style={{marginTop: 22, fontSize: 32, lineHeight: 1.45, color: light ? '#d5e9e0' : C.grey}}>{subtitle}</div> : null}
    </div>
  );
};

export const Metric: React.FC<{value: string; label: string; delay?: number; accent?: string}> = ({value, label, delay = 0, accent = C.green}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const opacity = interpolate(frame, [delay, delay + fps * 0.55], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  const scale = interpolate(frame, [delay, delay + fps * 0.7], [0.84, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing: Easing.bezier(0.16, 1, 0.3, 1)});
  return (
    <div style={{opacity, scale, minWidth: 240, padding: '28px 34px', borderRadius: 26, background: '#ffffffef', boxShadow: '0 18px 50px #0b4a3520', border: '1px solid #cde6da'}}>
      <div style={{fontSize: 58, fontWeight: 900, color: accent, letterSpacing: -2}}>{value}</div>
      <div style={{fontSize: 23, color: C.grey, marginTop: 8}}>{label}</div>
    </div>
  );
};

export const Footer: React.FC<{index: number}> = ({index}) => (
  <div style={{position: 'absolute', left: 78, right: 78, bottom: 38, display: 'flex', justifyContent: 'space-between', alignItems: 'center', zIndex: 30, fontSize: 18, color: '#789087'}}>
    <span>队不起队不起 · 开放赛题—生成式大语言模型与智能体</span>
    <span>{String(index).padStart(2, '0')} / 09</span>
  </div>
);
