import React from 'react';
import {Easing, interpolate, useCurrentFrame, useVideoConfig} from 'remotion';
import {Background, Brand, C, Footer, Metric, SceneTitle} from '../theme';

const checks = [
  ['主体', '这是谁的数据？'],
  ['期间', '对应哪一年度？'],
  ['单位', '吨、万元，还是比例？'],
  ['范围', '集团还是子公司？'],
];

export const Problem: React.FC = () => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  return (
    <Background>
      <Brand section="问题不是找数，而是核对语境" />
      <SceneTitle eyebrow="THE REVIEW BOTTLENECK" title="一个数字，四重约束" subtitle="正文、跨页表格、图表与附注共同决定它能不能被采用。" />
      <div style={{position: 'absolute', left: 90, right: 90, top: 505, display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 24}}>
        {checks.map(([name, desc], i) => {
          const delay = fps * (1.4 + i * 0.35);
          const opacity = interpolate(frame, [delay, delay + fps * 0.5], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
          const translate = interpolate(frame, [delay, delay + fps * 0.65], ['0px 55px', '0px 0px'], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing: Easing.bezier(0.16, 1, 0.3, 1)});
          return <div key={name} style={{opacity, translate, background: C.white, borderRadius: 28, padding: 32, minHeight: 190, boxShadow: '0 20px 60px #1b5a4219', borderTop: `7px solid ${[C.green,C.gold,C.green2,C.red][i]}`}}><div style={{fontSize: 40, fontWeight: 900}}>{name}</div><div style={{fontSize: 24, color: C.grey, marginTop: 22, lineHeight: 1.45}}>{desc}</div></div>;
        })}
      </div>
      <div style={{position: 'absolute', left: 120, right: 120, bottom: 90, display: 'flex', gap: 28, justifyContent: 'center'}}>
        <Metric value="200" label="冻结报告" delay={fps * 4.0} />
        <Metric value="10,528" label="解析页数" delay={fps * 4.25} />
        <Metric value="65" label="ESG 指标" delay={fps * 4.5} />
      </div>
      <Footer index={2} />
    </Background>
  );
};
