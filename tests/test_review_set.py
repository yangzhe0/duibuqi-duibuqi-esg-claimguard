import csv
import json
import os
import tempfile
import unittest
from pathlib import Path


class ReviewSetTests(unittest.TestCase):
    def test_build_review_set_identifies_required_issue_types(self):
        from scripts.build_review_set import build_review_set

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            results = root / "extraction_results.csv"
            pool = root / "indicator_pool_v2.csv"
            out_dir = root / "review"
            self._write_csv(pool, self._indicator_rows())
            self._write_csv(results, self._result_rows())

            summary = build_review_set(results, pool, out_dir, sample_size=20)

            self.assertTrue((out_dir / "review_sample.csv").is_file())
            self.assertTrue((out_dir / "review_sample.json").is_file())
            self.assertTrue((out_dir / "review_summary.json").is_file())
            self.assertEqual(summary["total_review_samples"], 8)
            with (out_dir / "review_sample.csv").open(encoding="utf-8-sig", newline="") as fh:
                rows = list(csv.DictReader(fh))
            issue_types = {row["suspected_issue_type"] for row in rows}
            self.assertIn("evidence_empty", issue_types)
            self.assertIn("evidence_too_short", issue_types)
            self.assertIn("value_unit_missing", issue_types)
            self.assertIn("possible_rate_as_count", issue_types)
            self.assertIn("possible_money_as_count", issue_types)
            self.assertIn("possible_zero_event", issue_types)
            self.assertTrue(any(row["needs_manual_check"] == "true" for row in rows))
            self.assertFalse((root / "dashboard.html").exists())
            self.assertFalse((out_dir / "dashboard.html").exists())

    def test_default_paths_are_project_root_based(self):
        from scripts import build_review_set

        with tempfile.TemporaryDirectory() as tmp:
            old_cwd = Path.cwd()
            try:
                os.chdir(tmp)
                self.assertTrue(build_review_set.DEFAULT_RESULTS.is_absolute())
                self.assertTrue(build_review_set.DEFAULT_POOL.is_absolute())
                self.assertTrue(build_review_set.DEFAULT_OUT_DIR.is_absolute())
                self.assertIn("contest_xiaoshumo", str(build_review_set.DEFAULT_RESULTS))
            finally:
                os.chdir(old_cwd)

    def _indicator_rows(self):
        return [
            {"indicator_id": "s_customer_complaints", "indicator_name": "客户投诉", "dimension": "S", "indicator_type": "quantitative", "keywords": "客户投诉", "common_units": "件|次"},
            {"indicator_id": "s_work_injury", "indicator_name": "工伤事故", "dimension": "S", "indicator_type": "quantitative", "keywords": "工伤", "common_units": "起"},
            {"indicator_id": "g_anti_corruption", "indicator_name": "反腐败机制", "dimension": "G", "indicator_type": "boolean", "keywords": "反腐败", "common_units": ""},
            {"indicator_id": "e_ghg_total", "indicator_name": "温室气体排放总量", "dimension": "E", "indicator_type": "quantitative", "keywords": "温室气体", "common_units": "吨二氧化碳当量"},
            {"indicator_id": "s_training", "indicator_name": "员工培训", "dimension": "S", "indicator_type": "qualitative", "keywords": "培训", "common_units": ""},
        ]

    def _result_rows(self):
        base = {
            "qualitative_text": "",
            "page_no": "1",
            "block_id": "b1",
            "block_type": "paragraph",
            "llm_confidence": "0.8",
            "llm_reason": "",
            "source_candidate_count": "1",
            "elapsed_seconds": "0.1",
            "postprocess_repaired": "false",
            "quantitative_incomplete": "false",
            "repair_method": "none",
            "repair_reason": "",
            "raw_response": "",
        }
        rows = [
            {"report_id": "r1", "indicator_id": "e_ghg_total", "indicator_name": "温室气体排放总量", "dimension": "E", "indicator_type": "quantitative", "status": "found", "value": "10", "unit": "吨二氧化碳当量", "evidence_quote": ""},
            {"report_id": "r1", "indicator_id": "s_training", "indicator_name": "员工培训", "dimension": "S", "indicator_type": "qualitative", "status": "found", "value": "", "unit": "", "evidence_quote": "培训"},
            {"report_id": "r2", "indicator_id": "e_ghg_total", "indicator_name": "温室气体排放总量", "dimension": "E", "indicator_type": "quantitative", "status": "found", "value": "12", "unit": "", "evidence_quote": "温室气体排放总量 12"},
            {"report_id": "r2", "indicator_id": "s_customer_complaints", "indicator_name": "客户投诉", "dimension": "S", "indicator_type": "quantitative", "status": "found", "value": "98", "unit": "%", "evidence_quote": "客户投诉解决率为98%"},
            {"report_id": "r3", "indicator_id": "s_work_injury", "indicator_name": "工伤事故", "dimension": "S", "indicator_type": "quantitative", "status": "found", "value": "100", "unit": "万元", "evidence_quote": "工伤保险投入100万元"},
            {"report_id": "r3", "indicator_id": "s_work_injury", "indicator_name": "工伤事故", "dimension": "S", "indicator_type": "quantitative", "status": "found", "value": "0", "unit": "起", "evidence_quote": "报告期内未发生工伤事故"},
            {"report_id": "r4", "indicator_id": "g_anti_corruption", "indicator_name": "反腐败机制", "dimension": "G", "indicator_type": "boolean", "status": "found", "value": "true", "unit": "", "evidence_quote": "反腐败"},
            {"report_id": "r4", "indicator_id": "s_training", "indicator_name": "员工培训", "dimension": "S", "indicator_type": "qualitative", "status": "missing", "value": "", "unit": "", "evidence_quote": ""},
        ]
        return [{**base, **row} for row in rows]

    def _write_csv(self, path: Path, rows: list[dict]) -> None:
        with path.open("w", encoding="utf-8-sig", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)


if __name__ == "__main__":
    unittest.main()
