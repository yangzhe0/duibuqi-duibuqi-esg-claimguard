import React from 'react';
import {CanvasImage, Easing, interpolate, staticFile, useCurrentFrame, useVideoConfig} from 'remotion';
import {Background, Brand, C, Footer, SceneTitle} from '../theme';

const badges = [
  ['10,015', '生成调用'],
  ['0', '调用错误'],
  ['68 / 68', 'Python 测试'],
  ['18 / 18', '生产 Smoke'],
  ['SHA-256', '冻结文件校验'],
];

export const Engineering: React.FC = () => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  return (
    <Background dark>
      <Brand light section="工程验收" />
      <SceneTitle eyebrow="ENGINEERING ACCEPTANCE" title="从一次演示，到可复验链路" subtitle="单卡顺序部署，全量运行与冻结校验均保留证据。" light />
      <div style={{position: 'absolute', left: 90, top: 520, width: 920, height: 430, borderRadius: 30, padding: 22, background: '#ffffffef', boxShadow: '0 25px 75px #00181088'}}><CanvasImage src={staticFile('figures/fig_inference.png')} style={{width: '100%', height: '100%', objectFit: 'contain'}} /></div>
      <div style={{position: 'absolute', right: 90, top: 500, width: 710, display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20}}>
        {badges.map(([value, label], i) => {
          const delay = fps * (1.0 + i * 0.45);
          const opacity = interpolate(frame, [delay, delay + fps * 0.45], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
          const translate = interpolate(frame, [delay, delay + fps * 0.65], ['0px 32px', '0px 0px'], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing: Easing.bezier(0.16, 1, 0.3, 1)});
          return <div key={label} style={{opacity, translate, gridColumn: i === 4 ? '1 / 3' : undefined, padding: '24px 28px', borderRadius: 24, background: '#ffffff14', border: '1px solid #80cfac42'}}><div style={{fontSize: 42, fontWeight: 950, color: i === 1 ? '#74d3aa' : C.white}}>{value}</div><div style={{fontSize: 21, color: '#cde5da', marginTop: 7}}>{label}</div></div>;
        })}
      </div>
      <Footer index={7} />
    </Background>
  );
};
