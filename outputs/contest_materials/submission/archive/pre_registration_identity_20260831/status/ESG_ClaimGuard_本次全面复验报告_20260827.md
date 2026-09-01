# ESG ClaimGuard 本次全面复验报告

> 复验日期：2026-08-27  
> 复验范围：官方提交规范与模板、项目文档、300 字介绍、技术论文、来源与许可台账、项目代码和冻结数据、实际工作台、现有视频及最终 ZIP。

## 1. 总结论

官方四项交付文件已完成 4/4，文件与内容硬约束全部通过，可进入平台上传终检。现有视频不需重新生成。

当前唯一不能从本地项目独立确认的是报名系统中的真实身份字段。最终材料目前使用“知证智核队”和“开放赛题组三”；实际队员姓名、学号、学校和指导教师信息在项目仓库中没有权威来源，因此本次没有擅自填写。

## 2. 已经 OK 的部分

| 检查项 | 结论 | 复验证据 |
|---|---|---|
| 参赛题目 | OK | 项目为 `ESG ClaimGuard｜可持续披露一致性预审系统`；已明确对应官方“开放赛题—赛题三：面向科学、工程和社会科学的‘AI+X’应用”，不属于地方或华为企业赛题。 |
| 文章主线 | OK | 现已形成“长 PDF 复核痛点 → 证据约束流水线 → 人工处置与底稿 → 冻结实测证据 → 能力边界”的完整闭环。 |
| 官方模板结构 | OK | 项目概况、项目规划、实施方案、计划与分工、参考资料等要求项齐全；项目 PDF 为 12 页 A4、可检索、无空白页、逐页无截断。 |
| 300 字介绍 | OK | 正文 176 个汉字，1 页 A4，与源文一致。 |
| 冻结数据 | OK | 200/200 份报告、10,528/10,528 页、13,000/13,000 唯一键，found 7,688、missing 5,312、error 0；21 项 validation 检查全通过。 |
| 证据与定量完整性 | OK | 7,688/7,688 条 found 可追溯至规范区块并通过逐字引文校验；3,214/3,214 条定量 found 具备值、单位和来源。 |
| 视频技术规格 | OK | 280 秒（4:40）、1920×1080、30 fps、H.264/yuv420p + AAC 48 kHz 双声道，24.666 MiB；全程解码无错。 |
| 视频内容 | OK | 已审查全片分镜、55 条字幕和每 20 秒抽帧；包含真实工作台录屏，统计口径与冻结数据一致，且明确“工程完整性不等于准确率”。 |
| 工程可运行性 | OK | Python 单元测试 68/68；生产 smoke 18/18；TypeScript 编译与 Vite 生产构建通过。 |
| 其他材料 ZIP | OK | 3.293 MiB，118 个入包项，CRC、内部 manifest、路径安全、敏感内容和 200 MiB 限制检查通过。 |

## 3. 本次发现并已修改的部分

1. 删除了项目文档封面上虚构的“队员：A、B、C”，并把正文的“成员 A/B/C”改为“角色 A/B/C”。现有 PDF 和视频中均没有伪造的真实队员姓名。
2. 补充官方赛题映射，明确项目对应开放赛题赛题三（AI+X），避免只写“组三”而不说明赛题内容。
3. 补齐文章的业务闭环、对比研究表、AI inference 运行指标、数据/行业知识/算法/硬件来源，并把 Natural-Gold 0/300 与工程完整性分开表述。
4. 把“原始 PDF 目录中恰有 200 份”改为“`input_manifest.csv` 选定正式 200 份”。当前 `data/raw_pdfs/` 实际有 210 份 PDF，多出的 10 份不属于正式 cohort，未删除原始文件。
5. 明确首轮自动交易所条款映射只对沪市报告启用，且条款命中不等于违规结论。
6. 修正第三方技术说明：项目 API 是 Python 标准库服务，不再误写为 FastAPI；网页上传改为“计算 SHA-256 并隔离登记”，不再声称已实现全局去重。
7. 修正 Qwen 参考文献标题，改为官方 `Qwen3.6-27B Model Card`，删除无官方依据的宣传性标题和模型描述。
8. 文档、ZIP 和视频构建器现已支持显式传入团队名、参赛组别和日期，避免之后只改文件名而没有改内容。

## 4. 仍需团队本人确认

| 字段 | 当前值 | 处理建议 |
|---|---|---|
| 团队名 | 知证智核队 | 必须与报名平台逐字一致。 |
| 参赛组别显示 | 开放赛题组三 | 内容已被官方赛题三支持；但“开放赛题组三”是否为报名平台的精确显示字符，仍需与平台核对。 |
| 实际队员信息 | 未写入提交 PDF/视频 | 官方项目文档模板未要求队员名单，因此不是当前硬性缺失。若学校或平台额外要求，应在平台填真实姓名/学号/单位，不应再使用 A/B/C。 |
| 提交日期 | 2026 年 8 月 22 日 | 如需以实际终稿日期为准，使用下方参数重新生成 PDF 和 ZIP；视频中未显示日期。 |
| 独立准确率 | Natural-Gold 0/300 | 不影响当前四件套的形式完整性，但仍不能宣称 Precision、Recall 或 F1；后续需两名独立标注员和第三人仲裁。 |

## 5. 是否需要重新生成视频

当前结论：**不需要**。视频本身合格，且不包含虚构队员姓名。

只有下列任一情况成立时才应重生：

- 报名平台中的团队名不是“知证智核队”；
- 平台要求视频必须显示另一个组别字符；
- 团队决定在片头或片尾增加真实队员姓名。

## 6. 如需新建/重建，使用的参数

### 6.1 PDF 文档

```bash
/opt/miniconda3/bin/conda run -n paperagent python scripts/render_submission_documents.py \
  --output-dir outputs/contest_materials/submission/supporting \
  --final \
  --team '真实团队名' \
  --competition-group '开放赛题组三' \
  --submission-date '2026年8月22日'
```

生成规格：A4 竖版；介绍 1 页；项目文档按官方模板章节生成。

### 6.2 视频（只在身份字段需变更时执行）

```bash
/opt/miniconda3/bin/conda run -n paperagent python scripts/build_captioned_project_video.py \
  --team '真实团队名' \
  --competition-group '开放赛题组三' \
  --dashboard-clip outputs/contest_materials/submission/drafts/dashboard_demo.webm \
  --output 'outputs/contest_materials/submission/final/真实团队名_ESG ClaimGuard_项目视频.mp4'
```

推荐且已验证的视频参数：1920×1080、30 fps、280 秒、H.264 `libx264`、`yuv420p`、`preset=veryfast`、`CRF=22`、AAC 96 kbps、48 kHz 双声道、`+faststart`、烧录字幕。要求保持小于 300 秒和 200 MiB。更改团队名/组别时必须完整重生，不能仅对旧视频重烧字幕，因为身份已嵌入画面和语音。

### 6.3 其他材料 ZIP

```bash
/opt/miniconda3/bin/conda run -n paperagent python scripts/build_contest_submission.py \
  --team '真实团队名' \
  --competition-group '开放赛题组三' \
  --submission-date '2026年8月22日'
```

### 6.4 最终验收

```bash
/opt/miniconda3/bin/conda run -n paperagent python scripts/validate_final_submission.py --refresh-official-hashes
```

## 7. 当前正式四件套

| 文件 | 大小 | SHA-256 |
|---|---:|---|
| `知证智核队_ESG ClaimGuard_参赛作品简介.pdf` | 70,809 B | `48ed1b6fb28d6392009de83b587e35d514ccf493eca4654ea59d2d7e2e9ee65e` |
| `知证智核队_ESG ClaimGuard_项目文档.pdf` | 1,051,856 B | `721048f1007515d09fda1b217d6b800fa6251fd1763859169ab38d5f44e63180` |
| `知证智核队_ESG ClaimGuard_项目视频.mp4` | 25,864,087 B | `ba0dbdbcc5d08eabb1c1575dc02818de9ced437d7d94d48a5b7a087b15d362df` |
| `知证智核队_ESG ClaimGuard_其他.zip` | 3,452,989 B | `a0618037228f6ddf0eb3f63b9b7519d40e48f31adb13cdd61a07866fb59d74a5` |

四个哈希与 `outputs/contest_materials/submission/OFFICIAL_SHA256SUMS.txt` 一致。

## 8. 最终上传前的人工动作

1. 在报名平台上逐字核对团队名和组别。
2. 如字段一致，不要重新生成视频；直接上传当前四件套。
3. 上传后在平台内分别预览 PDF、试播视频、下载回传 ZIP，再核对文件大小或 SHA-256。

