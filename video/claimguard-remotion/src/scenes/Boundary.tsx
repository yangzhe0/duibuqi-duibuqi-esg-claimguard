import React from 'react';
import {Easing, interpolate, useCurrentFrame, useVideoConfig} from 'remotion';
import {Background, Brand, C, Footer, SceneTitle} from '../theme';

const comparisons = [
  ['关键词检索', '只匹配词', '语义理解 + 指标约束'],
  ['自由问答', '答案难追溯', '原串证据 + 页码区块'],
  ['普通 RAG', '来源粒度较粗', '数值与单位 lineage'],
];

export const Boundary: React.FC = () => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  return (
    <Background>
      <Brand section="创新与边界" />
      <SceneTitle eyebrow="AUDITABLE BY DESIGN" title="不抢结论，只把证据送到人手里" subtitle="系统负责缩小复核范围，最终判断仍由专业人员完成。" />
      <div style={{position: 'absolute', left: 85, right: 85, top: 500, display: 'grid', gridTemplateColumns: 'repeat(3,1fr)', gap: 26}}>
        {comparisons.map(([name, old, ours], i) => {
          const delay = fps * (1 + i * 0.45);
          const opacity = interpolate(frame, [delay, delay + fps * 0.5], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
          const translate = interpolate(frame, [delay, delay + fps * 0.7], ['0px 50px', '0px 0px'], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing: Easing.bezier(0.16, 1, 0.3, 1)});
          return <div key={name} style={{opacity, translate, borderRadius: 30, overflow: 'hidden', background: 'white', boxShadow: '0 20px 60px #184a3720'}}><div style={{padding: '24px 30px', fontSize: 28, fontWeight: 900, background: C.ink, color: 'white'}}>{name}</div><div style={{padding: '24px 30px', color: C.grey, fontSize: 23, borderBottom: '1px solid #e4ece8'}}>传统方式：{old}</div><div style={{padding: '28px 30px', color: C.green, fontSize: 26, lineHeight: 1.4, fontWeight: 900}}>ClaimGuard：{ours}</div></div>;
        })}
      </div>
      <div style={{position: 'absolute', left: 110, right: 110, bottom: 95, display: 'flex', justifyContent: 'center', gap: 24}}>{['不作企业评分','不替代人工审阅','不替代法定鉴证','不声明未经验证的准确率'].map((x) => <div key={x} style={{padding: '15px 24px', borderRadius: 99, border: `2px solid ${C.red}55`, color: C.red, fontSize: 21, fontWeight: 800}}>{x}</div>)}</div>
      <Footer index={8} />
    </Background>
  );
};
