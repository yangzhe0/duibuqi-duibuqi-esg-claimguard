import React from 'react';
import {Easing, interpolate, useCurrentFrame, useVideoConfig} from 'remotion';
import {Background, Brand, C, Footer} from '../theme';

export const Closing: React.FC = () => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const opacity = interpolate(frame, [0, fps * 1.2], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  const scale = interpolate(frame, [0, fps * 1.5], [0.84, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing: Easing.bezier(0.16, 1, 0.3, 1)});
  return (
    <Background dark>
      <Brand light />
      <div style={{opacity, scale, position: 'absolute', inset: 0, display: 'flex', flexDirection: 'column', justifyContent: 'center', alignItems: 'center', textAlign: 'center'}}>
        <div style={{fontSize: 28, color: '#76d0aa', fontWeight: 900, letterSpacing: 7}}>EVIDENCE BEFORE CLAIMS</div>
        <div style={{fontSize: 102, lineHeight: 1.08, fontWeight: 950, letterSpacing: -5, marginTop: 28}}>可回原文 · 可人工处置 · 可导出</div>
        <div style={{fontSize: 38, color: '#d7eae2', marginTop: 34}}>把有限的复核时间，集中在真正有证据的问题上</div>
        <div style={{display: 'flex', alignItems: 'center', gap: 18, marginTop: 70, padding: '20px 34px', borderRadius: 99, background: '#ffffff12', border: '1px solid #81cfac44'}}><div style={{width: 14, height: 14, borderRadius: '50%', background: C.green2}} /><span style={{fontSize: 26, fontWeight: 800}}>队不起队不起</span><span style={{fontSize: 24, color: '#bddbce'}}>第八届中国研究生人工智能创新大赛</span></div>
      </div>
      <Footer index={9} />
    </Background>
  );
};
