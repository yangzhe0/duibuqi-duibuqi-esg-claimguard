# ESG 抽取结果质量诊断报告

本报告为自动质量诊断和抽样复核辅助，不等同于人工标注评价结论。

## 1. 数据来源

- 抽取结果：`outputs/formal_v2/llm_200/extraction_results.csv`
- 指标池：`outputs/formal_v2/indicator_pool_v2.csv`
- 结果总数：13000

## 2. 总体运行统计

- found：7777
- missing：5223
- error：0
- found 占比：0.5982（结构化抽取结果分布）
- E/S/G found 分布：{'E': 2331, 'S': 2574, 'G': 2872}
- 指标类型 found 分布：{'quantitative': 3217, 'boolean': 2244, 'qualitative': 2316}

## 3. 定量字段完整性

- quantitative found：3217
- value 缺失：0
- unit 缺失：3
- quantitative_incomplete：3
- postprocess_repaired：109
- 疑似比例误作次数：32
- 疑似金额误作数量/次数：1
- 零事件归一需复核：56
- 具体风险样本数：164
- caution_tag 样本数：4336
- risk_level 分布：{'high': 36, 'medium': 72, 'low': 56}

## 4. 证据可追溯性

- evidence_quote 空缺：0
- evidence_quote 过短：27
- page_no、block_id、block_type 已保留在结果和风险样本中，用于回看 MinerU block。

## 5. 指标层面异常

- found 率过高指标数：1
- found 率过低指标数：0
- found 率过高可能意味着指标边界过宽或关键词过泛；found 率过低可能意味着披露确实少、关键词召回不足或指标定义过窄。

## 6. 报告层面异常

- 每份报告 found 指标数摘要：{'min': 1, 'max': 56, 'mean': 39.0804, 'median': 42, 'p25': 34, 'p75': 47, 'lowest_reports': [{'report_id': '000922_佳电股份_2026_ESG报告', 'found_count': 1}, {'report_id': '09668_渤海银行_2025_ESG暨社会责任报告', 'found_count': 7}, {'report_id': '01950_帝王实业控股_2026_ESG报告', 'found_count': 7}, {'report_id': '603777_来伊份_2025_ESG报告', 'found_count': 9}, {'report_id': '02651_大众口腔_2025_ESG报告', 'found_count': 10}, {'report_id': '01216_中原银行_2025_ESG报告', 'found_count': 11}, {'report_id': '01432_中国圣牧_2025_ESG报告', 'found_count': 12}, {'report_id': '00966_中国太平_2025_ESG暨社会责任报告', 'found_count': 12}, {'report_id': '002887_绿茵生态_2025_ESG报告', 'found_count': 13}, {'report_id': '02768_国恩科技_2025_可持续发展报告', 'found_count': 14}], 'highest_reports': [{'report_id': '002326_永太科技_2025_ESG报告', 'found_count': 56}, {'report_id': '600259_中稀有色_2025_ESG报告', 'found_count': 56}, {'report_id': '600737_中粮糖业_2025_ESG报告', 'found_count': 56}, {'report_id': '000777_中核科技_2025_ESG暨社会责任报告', 'found_count': 54}, {'report_id': '301522_上大股份_2025_ESG报告', 'found_count': 54}, {'report_id': '600587_新华医疗_2025_ESG报告', 'found_count': 54}, {'report_id': '603013_亚普股份_2025_ESG报告', 'found_count': 54}, {'report_id': '601106_中国一重_2025_ESG报告', 'found_count': 53}, {'report_id': '601956_东贝集团_2025_ESG报告', 'found_count': 53}, {'report_id': '688728_格科微_2025_ESG报告', 'found_count': 53}]}

## 7. 高风险样本

- `600278_东方创业_2025_ESG报告` / `董事会多元化` / value_unit_missing：quantitative found result lacks value or unit；value=7:2 unit=；证据：董事会成员男女比例为 7 : 2
- `600278_东方创业_2025_ESG报告` / `独立董事占比` / value_unit_missing：quantitative found result lacks value or unit；value=6:3 unit=；证据：非独立董事和独立董事比例为 6 : 3
- `600783_鲁信创投_2025_ESG报告` / `独立董事占比` / value_unit_missing：quantitative found result lacks value or unit；value=2 unit=；证据：独立董事2位 非独立董事1位 独董担任主任委员
- `000503_国新健康_2025_ESG报告` / `董事会人数` / possible_rate_as_count：count-like indicator contains percent/rate expression；value=9 unit=人；证据：公司董事会由9名董事构成。其中，非独立董事6名，独立董事3名；女性董事3名，占比33%。
- `000557_西部创业_2025_可持续发展报告` / `客户投诉` / possible_rate_as_count：count-like indicator contains percent/rate expression；value=100% unit=%；证据：客户投诉处理率 | 100%
- `000810_创维数字_2025_ESG报告` / `客户投诉` / possible_rate_as_count：count-like indicator contains percent/rate expression；value=100 unit=%；证据：客户投诉问题整改完成率 | | % | 100
- `002011_盾安环境_2025_ESG报告` / `董事会人数` / possible_rate_as_count：count-like indicator contains percent/rate expression；value=9 unit=人；证据：截至本报告期末，公司董事会由9名董事组成，其中独立董事3名、女性占董事会成员比例超过20%。
- `002533_金杯电工_2025_ESG报告` / `客户投诉` / possible_rate_as_count：count-like indicator contains percent/rate expression；value=100% unit=%；证据：2025年,公司未发生产品不良召回事件,客诉处理率100%。
- `002649_博彦科技_2025_ESG报告` / `董事会人数` / possible_rate_as_count：count-like indicator contains percent/rate expression；value=7 unit=人；证据：截至2025年底，公司董事会由7名成员组成，其中女性董事1名、占比14.29%，独立董事3名、占比42.86%。
- `300035_中科电气_2025_ESG报告` / `董事会人数` / possible_rate_as_count：count-like indicator contains percent/rate expression；value=9 unit=人；证据：2025年，董事会共有 9 名董事，其中独立董事 3 名，女性董事 3 名，占比均达 33%。
- `300149_睿智医药_2025_ESG报告` / `客户投诉` / possible_rate_as_count：count-like indicator contains percent/rate expression；value=100% unit=%；证据：投诉处理率 | 100% | 未被投诉 | 达成
- `300212_易华录_2025_ESG报告` / `董事会人数` / possible_rate_as_count：count-like indicator contains percent/rate expression；value=9 unit=名；证据：截至报告期末，公司董事会成员9名，其中女性董事1名，独立董事3名，独立董事占比为33.33%。
- `300468_四方精创_2025_ESG报告` / `客户投诉` / possible_rate_as_count：count-like indicator contains percent/rate expression；value=100 unit=%；证据：客户投诉及时处理率 | % | 100
- `301073_君亭酒店_2025_ESG报告` / `客户投诉` / possible_rate_as_count：count-like indicator contains percent/rate expression；value=90 unit=次；证据：2025年，本集团及各运营点共受理客户投诉90次，投诉解决率达100%。
- `301308_江波龙_2025_ESG报告` / `董事会人数` / possible_rate_as_count：count-like indicator contains percent/rate expression；value=9 unit=名；证据：江波龙董事会由9名董事组成，其中独立董事人数为4人，占比超40%，符合相关法律法规及《公司章程》的规定。
- `301599_理奇智能_2025_ESG报告` / `客户投诉` / possible_rate_as_count：count-like indicator contains percent/rate expression；value=0.338 unit=%；证据：质量投诉发生率 | $\leqslant 0.6\%$ | 0.338%
- `600009_上海机场_2025_ESG报告` / `董事会人数` / possible_rate_as_count：count-like indicator contains percent/rate expression；value=7 unit=人；证据：公司董事会成员共7人，其中外部董事6人、占比86%，女性董事占比14%
- `600009_上海机场_2025_ESG报告` / `客户投诉` / possible_rate_as_count：count-like indicator contains percent/rate expression；value=100 unit=%；证据：2025年,上海机场客户投诉处理率100%
- `600475_华光环能_2025_ESG报告` / `董事会人数` / possible_rate_as_count：count-like indicator contains percent/rate expression；value=9 unit=名；证据：公司董事会由 9 名董事组成，其中女性董事 3 名，女性董事占比 33.33%。
- `600587_新华医疗_2025_ESG报告` / `董事会人数` / possible_rate_as_count：count-like indicator contains percent/rate expression；value=11 unit=人；证据：董事会由11名成员组成,其中女性董事1名,女性董事占比9.09%。
- `600587_新华医疗_2025_ESG报告` / `客户投诉` / possible_rate_as_count：count-like indicator contains percent/rate expression；value=100% unit=%；证据：客户投诉回应率和解决率均达
- `600737_中粮糖业_2025_ESG报告` / `客户投诉` / possible_rate_as_count：count-like indicator contains percent/rate expression；value=71 unit=次；证据：客户投诉次数为 71 次，较去年下降 24.5%；客户投诉处理率 100%
- `600779_水井坊_2025_ESG报告` / `客户投诉` / possible_rate_as_count：count-like indicator contains percent/rate expression；value=100% unit=%；证据：2025 年，公司通过专项机制确保所有被正式受理的客户投诉实现 100% 的闭环处理。
- `600850_电科数字_2025_ESG报告` / `董事会人数` / possible_rate_as_count：count-like indicator contains percent/rate expression；value=9 unit=人；证据：董事会成员共9人，其中独立董事3人，占比33.33%。
- `600874_创业环保_2025_可持续发展报告` / `董事会人数` / possible_rate_as_count：count-like indicator contains percent/rate expression；value=9 unit=名；证据：董事会由9 名董事组成，其中女性董事占比 22.22%
- `600963_岳阳林纸_2025_ESG报告` / `董事会人数` / possible_rate_as_count：count-like indicator contains percent/rate expression；value=7 unit=人；证据：报告期末，公司董事会共有董事7人，其中女性董事4人，占比 57%，体现了董事会成员的性别多元化；同时，董事会成员涵盖了不同年龄段和工作经验的成员，有助干在决策中获得多元化的经验和意见。
- `601577_长沙银行_2025_可持续发展报告` / `董事会人数` / possible_rate_as_count：count-like indicator contains percent/rate expression；value=10 unit=人；证据：在任独立董事4人，占比40%，符合本行《公司章程》规定的“独立董事人数原则上不低于董事会成员总数三分之一”的要求。
- `603291_联合水务_2025_ESG报告` / `董事会人数` / possible_rate_as_count：count-like indicator contains percent/rate expression；value=9 unit=人；证据：报告期内，公司董事会成员共9人，其中3名为独立董事，独立董事占比达33.33%。
- `603291_联合水务_2025_ESG报告` / `客户投诉` / possible_rate_as_count：count-like indicator contains percent/rate expression；value=100 unit=%；证据：客户投诉处理率 | % | 100 | 100 | 100
- `603333_尚纬股份_2025_ESG报告` / `董事会人数` / possible_rate_as_count：count-like indicator contains percent/rate expression；value=9 unit=名；证据：董事9名 | 其中独立董事3名占比33.33% 其中非独立董事6名占比66.67% | 其中女性董事5名占比55.56% 召开股东会会议3次 | 召开董事会会议8次

## 8. 结论

这些指标用于质量控制、风险定位和抽样复核入口。没有人工真值集时，不能将 found/missing/error 或本报告中的风险统计解释为人工标注评价结论。
