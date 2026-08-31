# ESG ClaimGuard：面向可持续披露的证据约束式智能预审系统

## 摘要

针对 ESG 报告版面复杂、指标表达分散、生成式抽取难以审计的问题，本文提出 ESG ClaimGuard。方法以文档版面解析、指标候选召回、受约束大模型抽取和确定性证据门组成分层流水线，并将定量结果区分为直接读取、表达式推导和单位归一。系统在 200 份报告、10,528 页和 65 项指标上生成 13,000 条唯一结果，其中 found 7,688、missing 5,312、error 0。所有 found 均通过原始解析区块精确子串校验，3,214 条定量结果均具有值与单位来源。本文强调这些结果证明工程完整性和证据可追溯性，不等同于独立准确率；本作品不把未经独立人工评测的 Precision、Recall 或 F1 作为成果声明。

**关键词：** ESG；信息抽取；检索增强生成；证据追溯；人机协同

## 1 问题定义

给定报告集合 R 与指标集合 I，系统为每个二元组 (r, i) 输出 found 或 missing。found 必须携带页码、区块、原始引文及结构化值；missing 表示在当前解析和召回范围内没有满足证据合同的候选，不等价于事实上的未披露。证据门的纯文本约束为：evidence_quote q 必须是 canonical block b(r, p) 的连续精确子串，其中 p 是报告 r 的页码。

## 2 方法

流水线见图 1。MinerU 建立页级版面区块；候选召回限制模型上下文；Qwen3.6 输出受约束 JSON；确定性验证检查唯一键、状态、引文、页码、区块和定量来源。若数值为直接读取，记录 value_origin 和 unit_origin；若为推导值，同时保存 derivation_expression 与 derivation_inputs。任何强制字段失败均保守退化为 missing 或进入人工复核。

![图 1　ESG ClaimGuard 顺序流水线](latex/figures/fig_pipeline.png)

## 3 数据与实验协议

冻结队列由 `input_manifest.csv` 选取 200 份公开 ESG 类报告，共 10,528 页；项目目录中的其他 PDF 不属于该正式队列。指标池含环境 25、社会 20、治理 20 项，形成 13,000 个 report×indicator 任务。正式运行使用 MinerU2.5-Pro-2605-1.2B 和 Qwen3.6-27B Q4_K_M。本项目将 Qwen 官方仓库中的 Qwen3.6-27B 以 Q4_K_M 量化形态部署，仅使用文本输入和 8,192 token 运行上下文；模型身份与许可依据官方模型卡记录 [2]。209 条被重试熔断器保留的记录进入内部工程纠错，其中 193 条重新截取为严格可追溯 found，16 条保守改为 missing；该集合不作为独立测试集。

本文的验收范围是覆盖规模、证据合同、运行稳定性和时延。209 条工程复核记录仅用于修复与一致性检查，不作为独立人工测试集，因此不据此计算或宣称 Precision、Recall、F1。

## 4 结果

正式结果为 found 7,688、missing 5,312、error 0，唯一键 13,000/13,000。E/S/G 的 found 数分别为 2,363、2,550、2,775；报告级 found 数最小 0、中位数 42、最大 57。运行级生成调用为 10,015 次，总墙钟 27,928.801 秒；最终结果中 11,280 行保留正 `elapsed_seconds`，该行级样本的中位数为 2.765 秒、P95 为 3.683 秒。

图 2 将运行级生成调用数与有 `elapsed_seconds` 的结果行明确分开：直方图中的 11,280 个样本是有耗时记录的结果行，不是 10,015 次生成调用。两者来自不同统计层级，不能互换。

![图 2　运行级调用卡片与有耗时记录的结果行分布](latex/figures/fig_inference.png)

证据合同方面，{{found}} 条 found 全部满足原始精确子串与页码区块追溯，失败 {{evidence_failure_count}}。{{quantitative_found}} 条定量结果的 value origin 为直接读取 {{quantitative_direct}} 条、明确推导 {{quantitative_derived}} 条；unit origin 为原文单位 {{quantitative_unit_direct}} 条、单位归一或推断 {{quantitative_normalized_or_inferred_unit}} 条。这些计数由文档渲染器从正式 `validation.json` 注入，不在论文中固化旧值。上述“全部通过”仅表示内部字段和追溯合同完整，不能作为语义准确率。

![图 3　证据完成门、value origin 与 unit origin 分面](latex/figures/fig_evidence_gate.png)

## 5 讨论

系统的主要贡献是把生成式抽取限制在可复核证据链中。相比自由问答，评审者可以定位原文并复算推导值；相比关键词，系统能处理同义语义；相比普通 RAG，缺失与定量来源成为显式合同。局限包括 OCR 误差、跨页表格、隐含范围和行业口径差异，因此本作品将结论限定在工程完整性与证据可追溯性。

## 6 结论

ESG ClaimGuard 已完成文档解析、指标抽取、证据验证、人工处置和底稿交付的端到端实现。正式运行覆盖 200 份报告与 13,000 个 report×indicator 任务，验证结果表明系统能够稳定生成带页码、区块、原文和定量来源的结构化候选。

该系统的核心价值在于把生成式模型能力转化为可追溯、可复核、可处置的业务任务，并以确定性证据合同控制模型输出边界。其可信主张是工程完整性和证据可追溯性，而非未经验证的准确率领先，符合审计场景对证据和责任的要求。

综上，ESG ClaimGuard 已形成完整的可持续披露一致性预审系统，完成既定研究目标与工程交付。

## 参考文献

[1] Wang B. et al. MinerU: An Open-Source Solution for Precise Document Content Extraction. arXiv:2409.18839, 2024.  
[2] Qwen Team. Qwen3.6-27B Model Card. Hugging Face model repository, 2026. https://huggingface.co/Qwen/Qwen3.6-27B.  
[3] Yang A. et al. Qwen3 Technical Report. arXiv:2505.09388, 2025.  
[4] Gao Y. et al. Retrieval-Augmented Generation for Large Language Models: A Survey. arXiv:2312.10997, 2023.  
[5] Fan W. et al. A Survey on RAG Meeting LLMs. KDD, 2024.
