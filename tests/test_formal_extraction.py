import csv
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class FormalExtractionTests(unittest.TestCase):
    def test_joined_evidence_quote_is_repaired_to_verbatim_source_excerpt(self):
        from src.esg_demo.formal_extraction import Indicator, _normalize_result

        source = "成立 EHSQ 委员会，设置环保与碳排放专业组，制定节能降碳管理规定，推动节能降碳项目。"
        candidate = {
            "text": source,
            "page_no": 13,
            "block_id": "r1:p13:b3",
            "block_type": "paragraph",
        }
        raw = json.dumps(
            {
                "status": "found",
                "value": "true",
                "evidence_quote": "成立 EHSQ 委员会，设置环保与碳排放专业组...推动节能降碳项目",
                "page_no": 13,
                "block_id": "r1:p13:b3",
                "block_type": "paragraph",
                "llm_confidence": 1,
                "llm_reason": "证据明确",
            },
            ensure_ascii=False,
        )
        result = _normalize_result(
            "r1",
            Indicator("e_carbon_management", "碳排放管理措施", "E", "boolean", (), (), True),
            raw,
            1,
            0.1,
            [candidate],
        )
        self.assertEqual(result["status"], "found")
        self.assertIn(result["evidence_quote"], source)
        self.assertNotIn("...", result["evidence_quote"])
        self.assertEqual(result["repair_method"], "exact_source_excerpt_reconciliation")

    def test_output_circuit_breaker_checkpoints_unique_keys(self):
        from src.esg_demo.formal_extraction import LLMOutputCircuitBreaker, run_sample

        class InvalidEvidenceClient:
            def generate(self, prompt: str) -> str:
                return json.dumps(
                    {
                        "status": "found",
                        "value": "true",
                        "evidence_quote": "候选证据中不存在的文字",
                        "page_no": 99,
                        "block_id": "bad",
                        "block_type": "paragraph",
                    },
                    ensure_ascii=False,
                )

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report_id = "000001_熔断测试_2025_ESG报告"
            report_dir = root / "parsed" / report_id
            report_dir.mkdir(parents=True)
            report_path = report_dir / f"{report_id}_content_list_v2.json"
            report_path.write_text(
                json.dumps([[{"type": "paragraph", "content": {"content": "测试指标候选证据"}}]], ensure_ascii=False),
                encoding="utf-8",
            )
            pool = root / "pool.csv"
            self._write_csv(
                pool,
                [
                    {
                        "indicator_id": f"test_{index}",
                        "indicator_name": f"测试指标{index}",
                        "dimension": "G",
                        "indicator_type": "boolean",
                        "keywords": "测试指标|候选证据",
                        "common_units": "",
                    }
                    for index in range(10)
                ],
            )
            out = root / "out"
            with self.assertRaises(LLMOutputCircuitBreaker):
                run_sample(
                    project_root=root,
                    indicator_pool_path=pool,
                    out_dir=out,
                    report_limit=1,
                    model="qwen3:30b",
                    ollama_url="http://unused",
                    max_blocks_per_indicator=1,
                    client=InvalidEvidenceClient(),
                    report_paths=[report_path],
                )
            with (out / "extraction_results.csv").open(encoding="utf-8-sig", newline="") as stream:
                rows = list(csv.DictReader(stream))
            keys = [(row["report_id"], row["indicator_id"]) for row in rows]
            self.assertEqual(len(rows), 10)
            self.assertEqual(len(set(keys)), 10)

    def test_current_formal_pool_is_submission_ready(self):
        base = Path(__file__).resolve().parents[1] / "outputs/final_results"
        pool_path = base / "indicator_pool.csv"
        self.assertTrue(pool_path.is_file())

        with pool_path.open(encoding="utf-8-sig", newline="") as fh:
            rows = list(csv.DictReader(fh))

        self.assertEqual(len(rows), 65)
        self.assertEqual({row["dimension"] for row in rows}, {"E", "S", "G"})
        self.assertEqual({row["indicator_type"] for row in rows}, {"boolean", "qualitative", "quantitative"})
        self.assertEqual(sum(1 for row in rows if row["dimension"] == "E"), 25)
        self.assertEqual(sum(1 for row in rows if row["dimension"] == "S"), 20)
        self.assertEqual(sum(1 for row in rows if row["dimension"] == "G"), 20)

    def test_formal_sample_runner_writes_required_schema_with_fake_llm(self):
        from src.esg_demo.formal_extraction import run_sample

        class FakeClient:
            def generate(self, prompt: str) -> str:
                return json.dumps(
                    {
                        "status": "found",
                        "value": "20",
                        "unit": "吨二氧化碳当量",
                        "qualitative_text": "",
                        "evidence_quote": "温室气体排放总量 20 吨二氧化碳当量",
                        "page_no": 1,
                        "block_id": "000001_测试公司_2025_ESG报告:p1:b0",
                        "block_type": "table",
                        "llm_confidence": 0.9,
                        "llm_reason": "证据直接包含指标、数值和单位。",
                    },
                    ensure_ascii=False,
                )

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report_dir = root / "outputs/final_results/parsed/000001_测试公司_2025_ESG报告"
            report_dir.mkdir(parents=True)
            (report_dir / "000001_测试公司_2025_ESG报告_content_list_v2.json").write_text(
                json.dumps(
                    [
                        [
                            {
                                "type": "table",
                                "bbox": [0, 0, 10, 10],
                                "content": {
                                    "html": "<table><tr><td>温室气体排放总量</td><td>20</td><td>吨二氧化碳当量</td></tr></table>"
                                },
                            }
                        ]
                    ],
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            pool_dir = root / "outputs/formal"
            pool_dir.mkdir(parents=True)
            self._write_csv(
                pool_dir / "indicator_pool_v2.csv",
                [
                    {
                        "indicator_id": "e_ghg_total",
                        "indicator_name": "温室气体排放总量",
                        "dimension": "E",
                        "indicator_type": "quantitative",
                        "keywords": "温室气体排放总量|吨二氧化碳当量",
                        "common_units": "吨二氧化碳当量",
                    }
                ],
            )

            summary = run_sample(
                project_root=root,
                indicator_pool_path=pool_dir / "indicator_pool_v2.csv",
                out_dir=pool_dir / "llm_50",
                report_limit=1,
                model="qwen3:30b",
                ollama_url="http://127.0.0.1:11434/api/generate",
                max_blocks_per_indicator=3,
                client=FakeClient(),
            )

            self.assertEqual(summary["reports"], 1)
            self.assertEqual(summary["indicators"], 1)
            results_path = pool_dir / "llm_50/extraction_results.csv"
            self.assertTrue(results_path.is_file())
            with results_path.open(encoding="utf-8-sig") as fh:
                rows = list(csv.DictReader(fh))
            self.assertEqual(rows[0]["status"], "found")
            self.assertIn("evidence_quote", rows[0])
            self.assertIn("llm_confidence", rows[0])
            self.assertIn("source_candidate_count", rows[0])
            self.assertIn("elapsed_seconds", rows[0])
            self.assertIn("postprocess_repaired", rows[0])
            self.assertIn("quantitative_incomplete", rows[0])
            self.assertIn("repair_method", rows[0])
            self.assertTrue((pool_dir / "llm_50/llm_50_diagnostics.md").is_file())
            self.assertTrue((pool_dir / "llm_50/sample_review.csv").is_file())
            self.assertTrue((pool_dir / "llm_50/error_analysis.csv").is_file())
            self.assertTrue((pool_dir / "llm_50/error_analysis.md").is_file())
            with (pool_dir / "llm_50/sample_review.csv").open(encoding="utf-8-sig") as fh:
                review_fields = list(csv.DictReader(fh).fieldnames or [])
            self.assertIn("manual_label", review_fields)
            self.assertIn("manual_notes", review_fields)
            with (pool_dir / "llm_50/llm_errors.csv").open(encoding="utf-8-sig") as fh:
                error_fields = list(csv.DictReader(fh).fieldnames or [])
            self.assertIn("raw_response", error_fields)

    def test_formal_parser_handles_fenced_json_and_repairs_quantitative_unit(self):
        from src.esg_demo.formal_extraction import _normalize_result
        from src.esg_demo.indicators import Indicator

        indicator = Indicator(
            "s_employee_total",
            "员工总数",
            "S",
            "quantitative",
            ("员工总数",),
            ("人", "名"),
        )
        raw = """模型说明：
```json
{
  "status": "found",
  "value": "2755",
  "unit": "",
  "qualitative_text": "",
  "evidence_quote": "截至2025年12月31日，本公司报告范围的员工总数为2,755名。",
  "page_no": 21,
  "block_id": "b1",
  "block_type": "table",
  "llm_confidence": 0.9,
  "llm_reason": "证据包含员工总数。"
}
```
结束"""

        row = _normalize_result("r1", indicator, raw, 2, 0.1)

        self.assertEqual(row["status"], "found")
        self.assertEqual(row["value"], "2755")
        self.assertEqual(row["unit"], "名")
        self.assertEqual(row["postprocess_repaired"], "true")
        self.assertEqual(row["quantitative_incomplete"], "false")
        self.assertEqual(row["repair_method"], "regex_unit_from_evidence")

    def test_formal_quantitative_found_without_number_is_downgraded_to_missing(self):
        from src.esg_demo.formal_extraction import _normalize_result
        from src.esg_demo.indicators import Indicator

        indicator = Indicator("e_cod", "化学需氧量排放量", "E", "quantitative", ("COD",), ("吨", "千克"))
        raw = json.dumps(
            {
                "status": "found",
                "value": "COD",
                "unit": "",
                "evidence_quote": "确保COD、氨氮等主要污染物稳定达标排放",
                "page_no": 23,
                "block_id": "b2",
                "block_type": "paragraph",
                "llm_confidence": 0.6,
                "llm_reason": "证据提到COD。",
            },
            ensure_ascii=False,
        )

        row = _normalize_result("r1", indicator, raw, 1, 0.1)

        self.assertEqual(row["status"], "missing")
        self.assertEqual(row["postprocess_repaired"], "false")
        self.assertEqual(row["quantitative_incomplete"], "false")
        self.assertEqual(row["repair_method"], "conservative_missing")

    def test_zero_event_normalization_repairs_known_count_indicator(self):
        from src.esg_demo.formal_extraction import _normalize_result
        from src.esg_demo.indicators import Indicator

        indicator = Indicator("s_work_injury", "工伤事故", "S", "quantitative", ("工伤事故",), ("起", "人", "小时"))
        raw = json.dumps(
            {
                "status": "found",
                "value": "",
                "unit": "",
                "evidence_quote": "报告期内，公司未发生工伤事故。",
                "page_no": 9,
                "block_id": "b3",
                "block_type": "paragraph",
                "llm_confidence": 0.8,
                "llm_reason": "明确提及未发生工伤事故",
            },
            ensure_ascii=False,
        )

        row = _normalize_result("r1", indicator, raw, 1, 0.1)

        self.assertEqual(row["value"], "0")
        self.assertEqual(row["unit"], "起")
        self.assertEqual(row["postprocess_repaired"], "true")
        self.assertEqual(row["quantitative_incomplete"], "false")
        self.assertEqual(row["repair_method"], "zero_event_normalization")

    def test_zero_event_unknown_unit_does_not_fabricate_unit(self):
        from src.esg_demo.formal_extraction import _normalize_result
        from src.esg_demo.indicators import Indicator

        indicator = Indicator("custom_count", "自定义次数", "S", "quantitative", ("自定义次数",), ())
        raw = json.dumps(
            {
                "status": "found",
                "value": "",
                "unit": "",
                "evidence_quote": "报告期内没有发生相关事件。",
                "page_no": 1,
                "block_id": "b4",
                "block_type": "paragraph",
            },
            ensure_ascii=False,
        )

        row = _normalize_result("r1", indicator, raw, 1, 0.1)

        self.assertEqual(row["value"], "")
        self.assertEqual(row["unit"], "")
        self.assertEqual(row["status"], "missing")
        self.assertEqual(row["postprocess_repaired"], "false")
        self.assertEqual(row["quantitative_incomplete"], "false")
        self.assertEqual(row["repair_method"], "conservative_missing")

    def test_zero_event_phrase_does_not_override_complete_quantitative_result(self):
        from src.esg_demo.formal_extraction import _normalize_result
        from src.esg_demo.indicators import Indicator

        indicator = Indicator("e_fuel_consumption", "燃料消耗量", "E", "quantitative", ("燃料",), ("吨",))
        raw = json.dumps(
            {
                "status": "found",
                "value": "54.98",
                "unit": "吨",
                "evidence_quote": "汽油 | 柴油 | 发生因环境相关问题引发的行政处罚事项 54.98吨 | 88.20吨 | 0起",
                "page_no": 7,
                "block_id": "b5",
                "block_type": "table",
            },
            ensure_ascii=False,
        )

        row = _normalize_result("r1", indicator, raw, 1, 0.1)

        self.assertEqual(row["value"], "54.98")
        self.assertEqual(row["unit"], "吨")
        self.assertEqual(row["postprocess_repaired"], "false")
        self.assertEqual(row["quantitative_incomplete"], "false")
        self.assertEqual(row["repair_method"], "none")

    def test_customer_complaint_count_overrides_adjacent_zero_event_text(self):
        from src.esg_demo.formal_extraction import _normalize_result
        from src.esg_demo.indicators import Indicator

        indicator = Indicator("s_customer_complaints", "客户投诉", "S", "quantitative", ("客户投诉",), ("起", "件"))
        raw = json.dumps(
            {
                "status": "found",
                "value": "0",
                "unit": "件",
                "evidence_quote": "公司共发生客户投诉10起，均已完成整改，未发生重大客户纠纷。",
                "page_no": 3,
                "block_id": "b6",
                "block_type": "paragraph",
            },
            ensure_ascii=False,
        )

        row = _normalize_result("r1", indicator, raw, 1, 0.1)

        self.assertEqual(row["status"], "found")
        self.assertEqual(row["value"], "10")
        self.assertEqual(row["unit"], "起")
        self.assertEqual(row["repair_method"], "customer_complaint_count_override")

    def test_work_injury_insurance_amount_is_conservatively_missing(self):
        from src.esg_demo.formal_extraction import _normalize_result
        from src.esg_demo.indicators import Indicator

        indicator = Indicator("s_work_injury", "工伤事故", "S", "quantitative", ("工伤",), ("起",))
        raw = json.dumps(
            {
                "status": "found",
                "value": "1342331.99",
                "unit": "元",
                "evidence_quote": "工伤保险投入金额 | 元 | 1,342,331.99",
                "page_no": 6,
                "block_id": "b7",
                "block_type": "table",
            },
            ensure_ascii=False,
        )

        row = _normalize_result("r1", indicator, raw, 1, 0.1)

        self.assertEqual(row["status"], "missing")
        self.assertEqual(row["value"], "")
        self.assertEqual(row["repair_method"], "conservative_missing")

    def test_customer_satisfaction_year_is_not_treated_as_metric_value(self):
        from src.esg_demo.formal_extraction import _normalize_result
        from src.esg_demo.indicators import Indicator

        indicator = Indicator("s_customer_satisfaction", "客户满意度", "S", "quantitative", ("满意度", "NPS"), ("%","分"))
        raw = json.dumps(
            {
                "status": "found",
                "value": "2025年，公司累计服务NPS较2024年有所增长",
                "unit": "",
                "evidence_quote": "2025年，公司累计服务NPS较2024年有所增长，且高于零售行业水平。",
                "page_no": 20,
                "block_id": "b8",
                "block_type": "paragraph",
            },
            ensure_ascii=False,
        )

        row = _normalize_result("r1", indicator, raw, 1, 0.1)

        self.assertEqual(row["status"], "missing")
        self.assertEqual(row["repair_method"], "conservative_missing")

    def test_customer_satisfaction_score_gets_unit_from_evidence(self):
        from src.esg_demo.formal_extraction import _normalize_result
        from src.esg_demo.indicators import Indicator

        indicator = Indicator("s_customer_satisfaction", "客户满意度", "S", "quantitative", ("满意度",), ("分", "%"))
        raw = json.dumps(
            {
                "status": "found",
                "value": "98",
                "unit": "",
                "evidence_quote": "报告期内，公司开展客户满意度调查，客户满意度总体得分为98分。",
                "page_no": 8,
                "block_id": "b9",
                "block_type": "paragraph",
            },
            ensure_ascii=False,
        )

        row = _normalize_result("r1", indicator, raw, 1, 0.1)

        self.assertEqual(row["status"], "found")
        self.assertEqual(row["unit"], "分")
        self.assertEqual(row["quantitative_incomplete"], "false")

    def test_voc_percentage_change_is_not_emission_amount(self):
        from src.esg_demo.formal_extraction import _normalize_result
        from src.esg_demo.indicators import Indicator

        indicator = Indicator("e_voc", "挥发性有机物排放量", "E", "quantitative", ("VOCs",), ("吨", "千克"))
        raw = json.dumps(
            {
                "status": "found",
                "value": "10",
                "unit": "%",
                "evidence_quote": "报告期内VOCs排放总量较上年下降近10%。",
                "page_no": 10,
                "block_id": "b10",
                "block_type": "paragraph",
            },
            ensure_ascii=False,
        )

        row = _normalize_result("r1", indicator, raw, 1, 0.1)

        self.assertEqual(row["status"], "missing")
        self.assertEqual(row["repair_method"], "conservative_missing")

    def test_employee_gender_and_patent_units_are_repaired_from_context(self):
        from src.esg_demo.formal_extraction import _normalize_result
        from src.esg_demo.indicators import Indicator

        gender = Indicator("s_employee_gender", "女性员工人数或占比", "S", "quantitative", ("女性员工",), ("人", "%"))
        gender_raw = json.dumps({"status": "found", "value": "3515", "unit": "", "evidence_quote": "性别结构 | 女性员工 | 3,515"}, ensure_ascii=False)
        gender_row = _normalize_result("r1", gender, gender_raw, 1, 0.1)
        self.assertEqual(gender_row["unit"], "人")
        self.assertEqual(gender_row["quantitative_incomplete"], "false")

        patent = Indicator("s_patents", "专利数量", "S", "quantitative", ("专利",), ("项", "件"))
        patent_raw = json.dumps({"status": "found", "value": "2", "unit": "", "evidence_quote": "发明专利 2"}, ensure_ascii=False)
        patent_row = _normalize_result("r1", patent, patent_raw, 1, 0.1)
        self.assertEqual(patent_row["unit"], "项")
        self.assertEqual(patent_row["quantitative_incomplete"], "false")

    def test_formal_sample_runner_retries_invalid_json_once(self):
        from src.esg_demo.formal_extraction import run_sample

        class RetryClient:
            def __init__(self):
                self.calls = 0

            def generate(self, prompt: str) -> str:
                self.calls += 1
                if self.calls == 1:
                    return '{"status":"found","value":"20"'
                return json.dumps(
                    {
                        "status": "found",
                        "value": "20",
                        "unit": "吨二氧化碳当量",
                        "evidence_quote": "温室气体排放总量 20 吨二氧化碳当量",
                        "page_no": 1,
                        "block_id": "000001_测试公司_2025_ESG报告:p1:b0",
                        "block_type": "table",
                        "llm_confidence": 0.9,
                        "llm_reason": "重试成功",
                    },
                    ensure_ascii=False,
                )

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report_dir = root / "outputs/final_results/parsed/000001_测试公司_2025_ESG报告"
            report_dir.mkdir(parents=True)
            (report_dir / "000001_测试公司_2025_ESG报告_content_list_v2.json").write_text(
                json.dumps([[{"type": "paragraph", "bbox": [0, 0, 1, 1], "content": {"content": "温室气体排放总量 20 吨二氧化碳当量"}}]], ensure_ascii=False),
                encoding="utf-8",
            )
            pool_dir = root / "outputs/formal"
            pool_dir.mkdir(parents=True)
            self._write_csv(
                pool_dir / "indicator_pool_v2.csv",
                [{"indicator_id": "e_ghg_total", "indicator_name": "温室气体排放总量", "dimension": "E", "indicator_type": "quantitative", "keywords": "温室气体排放总量", "common_units": "吨二氧化碳当量"}],
            )
            client = RetryClient()

            summary = run_sample(root, pool_dir / "indicator_pool_v2.csv", pool_dir / "llm_sample", 1, "qwen3:30b", "http://127.0.0.1:11434/api/generate", 3, client=client)

            self.assertEqual(client.calls, 2)
            self.assertEqual(summary["llm_error_count"], 0)
            with (pool_dir / "llm_sample/extraction_results.csv").open(encoding="utf-8-sig") as fh:
                row = list(csv.DictReader(fh))[0]
            self.assertEqual(row["status"], "found")
            self.assertIn("retry_after_invalid_json", row["llm_reason"])

    def test_formal_cli_script_is_directly_executable_from_project_root(self):
        result = subprocess.run(
            [sys.executable, "-m", "src.esg_demo.formal_extraction", "--help"],
            cwd=Path(__file__).resolve().parents[1],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("current ESG-65 evidence-constrained extraction", result.stdout)

    def test_system_entrypoint_exists(self):
        root = Path(__file__).resolve().parents[1]
        self.assertTrue((root / "scripts/esg_system.py").is_file())

    def test_esg_system_cli_help_mentions_new_report_input(self):
        result = subprocess.run(
            [sys.executable, "scripts/esg_system.py", "--help"],
            cwd=Path(__file__).resolve().parents[1],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--input-json", result.stdout)
        self.assertIn("--resume", result.stdout)

    def test_formal_runner_accepts_explicit_report_paths_and_resume(self):
        from src.esg_demo.formal_extraction import run_sample

        class FakeClient:
            def __init__(self):
                self.calls = 0

            def generate(self, prompt: str) -> str:
                self.calls += 1
                return json.dumps(
                    {
                        "status": "found",
                        "value": "20",
                        "unit": "吨二氧化碳当量",
                        "evidence_quote": "温室气体排放总量 20 吨二氧化碳当量",
                        "page_no": 1,
                        "block_id": "custom_report:p1:b0",
                        "block_type": "table",
                    },
                    ensure_ascii=False,
                )

        class NoCallClient:
            def generate(self, prompt: str) -> str:
                raise AssertionError("resume should skip completed rows")

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report_dir = root / "custom_report"
            report_dir.mkdir()
            report_json = report_dir / "custom_report_content_list_v2.json"
            report_json.write_text(
                json.dumps([[{"type": "table", "bbox": [0, 0, 1, 1], "content": {"html": "<table><tr><td>温室气体排放总量</td><td>20</td><td>吨二氧化碳当量</td></tr></table>"}}]], ensure_ascii=False),
                encoding="utf-8",
            )
            pool_dir = root / "outputs/formal"
            pool_dir.mkdir(parents=True)
            pool_path = pool_dir / "indicator_pool_v2.csv"
            self._write_csv(
                pool_path,
                [
                    {
                        "indicator_id": "e_ghg_total",
                        "indicator_name": "温室气体排放总量",
                        "dimension": "E",
                        "indicator_type": "quantitative",
                        "keywords": "温室气体排放总量",
                        "common_units": "吨二氧化碳当量",
                    }
                ],
            )
            out_dir = pool_dir / "new_reports"
            client = FakeClient()

            first = run_sample(root, pool_path, out_dir, 1, "qwen3:30b", "http://127.0.0.1:11434/api/generate", 3, client=client, report_paths=[report_json])
            second = run_sample(root, pool_path, out_dir, 1, "qwen3:30b", "http://127.0.0.1:11434/api/generate", 3, client=NoCallClient(), report_paths=[report_json], resume=True)

            self.assertEqual(first["reports"], 1)
            self.assertEqual(client.calls, 1)
            self.assertEqual(second["skipped_results"], 1)
            self.assertEqual(second["executed_calls"], 0)
            with (out_dir / "extraction_results.csv").open(encoding="utf-8-sig") as fh:
                self.assertEqual(len(list(csv.DictReader(fh))), 1)

    def _write_csv(self, path: Path, rows: list[dict]) -> None:
        with path.open("w", encoding="utf-8-sig", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)


if __name__ == "__main__":
    unittest.main()
