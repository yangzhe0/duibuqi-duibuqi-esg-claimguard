import React from 'react';
import {CanvasImage, Easing, interpolate, staticFile, useCurrentFrame, useVideoConfig} from 'remotion';
import {Background, Brand, C, Footer, Metric, SceneTitle} from '../theme';

const charts = [
  {src: 'figures/fig_scale_status.png', start: 0, label: '正式数据规模与结果状态'},
  {src: 'figures/fig_dimension_coverage.png', start: 10, label: 'E / S / G 披露覆盖分布'},
  {src: 'figures/fig_report_distribution.png', start: 20, label: '200 份报告的 found 分布'},
];

export const Results: React.FC = () => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  return (
    <Background>
      <Brand section="冻结正式结果" />
      <SceneTitle eyebrow="REPRODUCIBLE RESULTS" title="完整运行，不等于准确率" subtitle="规模、覆盖与工程状态可以复算；准确率必须由独立人工测试支持。" />
      <div style={{position: 'absolute', left: 90, top: 500, display: 'flex', flexDirection: 'column', gap: 14, zIndex: 8, scale: 0.82, transformOrigin: 'top left'}}>
        <Metric value="13,000" label="唯一 report × indicator 结果" delay={fps * 1.0} />
        <Metric value="7,688" label="found｜严格原串证据" delay={fps * 1.25} accent={C.green2} />
        <Metric value="5,312" label="missing｜证据不足候选" delay={fps * 1.5} accent={C.gold} />
      </div>
      {charts.map((chart) => {
        const local = frame - chart.start * fps;
        const opacity = interpolate(local, [0, fps * 0.7, fps * 8.8, fps * 10], [0, 1, 1, 0], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
        const translate = interpolate(local, [0, fps * 1.1], ['50px 0px', '0px 0px'], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing: Easing.bezier(0.16, 1, 0.3, 1)});
        return <div key={chart.src} style={{opacity, translate, position: 'absolute', right: 75, top: 420, width: 1040, height: 545, padding: 25, borderRadius: 32, background: 'white', boxShadow: '0 25px 70px #174b3724'}}><CanvasImage src={staticFile(chart.src)} style={{width: '100%', height: '92%', objectFit: 'contain'}} /><div style={{textAlign: 'center', fontSize: 22, color: C.grey, fontWeight: 700}}>{chart.label}</div></div>;
      })}
      <Footer index={6} />
    </Background>
  );
};
