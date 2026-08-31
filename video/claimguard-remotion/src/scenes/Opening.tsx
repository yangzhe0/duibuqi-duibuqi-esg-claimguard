import React from 'react';
import {CanvasImage, Easing, interpolate, staticFile, useCurrentFrame, useVideoConfig} from 'remotion';
import {Background, Brand, C, Footer} from '../theme';

const pages = ['project/page-03.png', 'project/page-05.png', 'figures/fig_dimension_coverage.png', 'project/page-08.png', 'figures/fig_evidence_gate.png'];

export const Opening: React.FC = () => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const titleOpacity = interpolate(frame, [fps * 2.2, fps * 3.4], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  const titleScale = interpolate(frame, [fps * 2.2, fps * 4], [0.88, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing: Easing.bezier(0.16, 1, 0.3, 1)});
  return (
    <Background dark>
      <Brand light section="可持续披露一致性预审" />
      {pages.map((src, i) => {
        const x = 70 + i * 365;
        const y = 690 + (i % 2) * 85 - (frame * (0.45 + i * 0.035)) % 640;
        const rotate = -7 + i * 3.2;
        return (
          <div key={src} style={{position: 'absolute', left: x, top: y, width: 330, height: 430, rotate: `${rotate}deg`, borderRadius: 18, overflow: 'hidden', boxShadow: '0 30px 70px #001b1388', border: '2px solid #ffffff28', opacity: 0.72}}>
            <CanvasImage src={staticFile(src)} style={{width: '100%', height: '100%', objectFit: 'cover'}} />
          </div>
        );
      })}
      <div style={{position: 'absolute', inset: 0, background: 'linear-gradient(90deg,#082b24e8 0%,#082b2498 52%,#082b2422 100%)'}} />
      <div style={{opacity: titleOpacity, scale: titleScale, position: 'absolute', left: 100, top: 250, zIndex: 10}}>
        <div style={{fontSize: 30, fontWeight: 700, color: '#77d4ad', letterSpacing: 6}}>从一万页报告，到一条可信证据</div>
        <div style={{fontSize: 116, lineHeight: 1.02, fontWeight: 950, letterSpacing: -6, marginTop: 20}}>ESG ClaimGuard</div>
        <div style={{fontSize: 42, marginTop: 30, color: '#dceee7'}}>让每个披露结论，都能回到原文</div>
      </div>
      <div style={{position: 'absolute', right: 110, top: 260, width: 250, height: 250, borderRadius: '50%', border: '2px solid #6dd1a655', scale: 1 + Math.sin(frame / 24) * 0.04}} />
      <Footer index={1} />
    </Background>
  );
};
