import React from 'react';
import {Video} from '@remotion/media';
import {CanvasImage, Easing, interpolate, staticFile, useCurrentFrame, useVideoConfig} from 'remotion';
import {Brand, C, Footer, font} from '../theme';

const tags = ['报告页码', '规范区块', '原始引文', '结构化值', '人工处置'];

export const Evidence: React.FC = () => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const switchAt = fps * 28;
  const clipOpacity = interpolate(frame, [switchAt - fps, switchAt], [1, 0], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  const figureOpacity = interpolate(frame, [switchAt - fps * 0.3, switchAt + fps * 0.8], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  return (
    <div style={{position: 'absolute', inset: 0, background: '#eef5f1', fontFamily: font, overflow: 'hidden'}}>
      <div style={{opacity: clipOpacity, position: 'absolute', inset: 0}}>
        <Video src={staticFile('dashboard_demo.webm')} muted trimBefore={45 * fps} style={{width: '100%', height: '100%', objectFit: 'cover', scale: 1.12, translate: '-35px -18px'}} />
        <div style={{position: 'absolute', inset: 0, background: 'linear-gradient(90deg,#071e19c7 0%,transparent 28%,transparent 82%,#071e1966 100%)'}} />
      </div>
      <Brand light={frame < switchAt} section="证据复核" />
      <div style={{opacity: clipOpacity, position: 'absolute', left: 78, top: 660, display: 'flex', flexDirection: 'column', gap: 12, zIndex: 9}}>
        {tags.map((tag, i) => {
          const delay = fps * (1.3 + i * 0.45);
          const opacity = interpolate(frame, [delay, delay + fps * 0.35], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
          return <div key={tag} style={{opacity, width: 205, padding: '13px 20px', borderRadius: 99, background: '#0b654bdc', color: C.white, fontSize: 21, fontWeight: 800, border: '1px solid #84d0af55'}}>✓ {tag}</div>;
        })}
      </div>
      <div style={{opacity: figureOpacity, position: 'absolute', left: 100, right: 100, top: 145, bottom: 110, display: 'grid', gridTemplateColumns: '0.86fr 1.14fr', gap: 40, alignItems: 'center'}}>
        <div><div style={{fontSize: 25, color: C.green2, letterSpacing: 4, fontWeight: 900}}>DETERMINISTIC EVIDENCE GATE</div><div style={{fontSize: 72, lineHeight: 1.08, fontWeight: 950, letterSpacing: -3, marginTop: 18}}>模型不能脱离原文<br/>自由作答</div><div style={{fontSize: 30, color: C.grey, lineHeight: 1.55, marginTop: 25}}>引文必须是原始解析区块的精确子串；证据不足时，系统保守输出 missing。</div></div>
        <div style={{background: 'white', borderRadius: 30, padding: 28, boxShadow: '0 25px 70px #174b371f'}}><CanvasImage src={staticFile('figures/fig_evidence_gate.png')} style={{width: '100%', height: '100%', objectFit: 'contain'}} /></div>
      </div>
      <Footer index={5} />
    </div>
  );
};
