import React from 'react';
import {Easing, interpolate, useCurrentFrame, useVideoConfig} from 'remotion';
import {Background, Brand, C, Footer, SceneTitle} from '../theme';

const steps = [
  ['01', 'PDF', '冻结原始报告'],
  ['02', 'MinerU', '版面、表格与页码'],
  ['03', '候选召回', 'ESG-65 块级上下文'],
  ['04', 'Qwen3.6', '受约束结构化推理'],
  ['05', '证据门', '原串、单位与 lineage'],
  ['06', '人工处置', '确认、修正与导出'],
];

export const Pipeline: React.FC = () => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const progress = interpolate(frame, [fps * 1.8, fps * 7.2], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing: Easing.bezier(0.16, 1, 0.3, 1)});
  return (
    <Background dark>
      <Brand light section="证据约束流水线" />
      <SceneTitle eyebrow="EVIDENCE-FIRST PIPELINE" title="模型负责理解，规则负责守门" subtitle="任何 found 都必须绑定同报告、同页、同区块的 canonical 原文。" light />
      <div style={{position: 'absolute', left: 120, right: 120, top: 565, height: 8, borderRadius: 99, background: '#ffffff1f'}}><div style={{height: '100%', width: `${progress * 100}%`, borderRadius: 99, background: 'linear-gradient(90deg,#55d09c,#f0b54d)'}} /></div>
      <div style={{position: 'absolute', left: 80, right: 80, top: 500, display: 'grid', gridTemplateColumns: 'repeat(6,1fr)', gap: 18}}>
        {steps.map(([no, title, body], i) => {
          const delay = fps * (1.7 + i * 0.85);
          const opacity = interpolate(frame, [delay, delay + fps * 0.45], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
          const translate = interpolate(frame, [delay, delay + fps * 0.65], ['0px 42px', '0px 0px'], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing: Easing.bezier(0.16, 1, 0.3, 1)});
          return <div key={no} style={{opacity, translate, position: 'relative', zIndex: 4, marginTop: i % 2 ? 95 : 0, padding: '32px 24px', minHeight: 240, borderRadius: 28, background: '#ffffffef', color: C.ink, boxShadow: '0 20px 60px #001a1266'}}><div style={{fontSize: 20, color: C.green2, fontWeight: 900, letterSpacing: 2}}>{no}</div><div style={{fontSize: 32, fontWeight: 900, marginTop: 15}}>{title}</div><div style={{fontSize: 21, color: C.grey, lineHeight: 1.45, marginTop: 18}}>{body}</div></div>;
        })}
      </div>
      <Footer index={3} />
    </Background>
  );
};
