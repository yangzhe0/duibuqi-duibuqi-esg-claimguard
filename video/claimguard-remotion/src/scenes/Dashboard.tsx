import React from 'react';
import {Video} from '@remotion/media';
import {Easing, interpolate, staticFile, useCurrentFrame, useVideoConfig} from 'remotion';
import {Brand, C, Footer, font} from '../theme';

const callouts = [
  {at: 2, title: '系统总览', body: '报告、指标、状态一屏掌握'},
  {at: 20, title: '披露预审', body: '从候选队列进入证据复核'},
  {at: 38, title: '原文定位', body: '页码、引文与结构化值并排核对'},
];

export const Dashboard: React.FC = () => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const sec = frame / fps;
  const scale = sec < 16 ? interpolate(sec, [0, 16], [1.02, 1.12]) : sec < 34 ? interpolate(sec, [16, 34], [1.08, 1.16]) : interpolate(sec, [34, 54], [1.04, 1.13]);
  const x = sec < 18 ? '0px' : sec < 36 ? '-25px' : '18px';
  const y = sec < 18 ? '-8px' : sec < 36 ? '-22px' : '-18px';
  return (
    <div style={{position: 'absolute', inset: 0, background: '#071d18', overflow: 'hidden', fontFamily: font}}>
      <Video src={staticFile('dashboard_demo.webm')} muted style={{width: '100%', height: '100%', objectFit: 'cover', scale, translate: `${x} ${y}`}} />
      <div style={{position: 'absolute', inset: 0, boxShadow: 'inset 0 0 180px #03120e99', pointerEvents: 'none'}} />
      <div style={{position: 'absolute', inset: 0, background: 'linear-gradient(90deg,#061d19b8 0%,transparent 30%,transparent 78%,#061d1955 100%)'}} />
      <Brand light section="真实工作台" />
      {callouts.map((item, i) => {
        const local = frame - item.at * fps;
        const opacity = interpolate(local, [0, fps * 0.6, fps * 11, fps * 12], [0, 1, 1, 0], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
        const translate = interpolate(local, [0, fps * 0.7], ['-42px 0px', '0px 0px'], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing: Easing.bezier(0.16, 1, 0.3, 1)});
        return <div key={item.title} style={{opacity, translate, position: 'absolute', left: 82, top: 690, width: 520, padding: '28px 34px', borderRadius: 26, background: '#082f25e8', color: C.white, border: '1px solid #75c9a36b', boxShadow: '0 24px 70px #00140dbb'}}><div style={{fontSize: 36, fontWeight: 900}}>{item.title}</div><div style={{fontSize: 24, color: '#cce7db', marginTop: 12}}>{item.body}</div><div style={{width: 90, height: 5, borderRadius: 10, background: [C.green2,C.gold,'#58a9d8'][i], marginTop: 22}} /></div>;
      })}
      <div style={{position: 'absolute', right: 75, top: 70, padding: '14px 20px', borderRadius: 99, background: '#0a6d4ee8', color: 'white', fontSize: 20, fontWeight: 800}}>READ-ONLY DEMO</div>
      <Footer index={4} />
    </div>
  );
};
