import csv
import json
import tempfile
import unittest
from pathlib import Path


class QualityReviewTests(unittest.TestCase):
    def test_review_quality_outputs_allowed_labels_and_decisions(self):
        from scripts.review_formal_quality import run_review

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            base = root / "outputs/formal_v1"
            base.mkdir(parents=True)
            (base / "run_summary.json").write_text(
                json.dumps(
                    {
                        "indicator_set": "formal_v1",
                        "reports": 2,
                        "indicators": 2,
                        "results": 4,
                        "llm_enabled": False,
                        "model": "qwen3:30b",
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            self._write_csv(
                base / "indicator_pool.csv",
                [
                    {
                        "indicator_id": "e_ghg_total",
                        "indicator_name": "温室气体排放总量",
                        "dimension": "E",
                        "indicator_type": "quantitative",
                        "keywords": "温室气体排放总量|碳排放总量",
                        "common_units": "吨二氧化碳当量|tCO2e",
                        "is_core": "True",
                    },
                    {
                        "indicator_id": "s_local_procurement",
                        "indicator_name": "本地采购",
                        "dimension": "S",
                        "indicator_type": "quantitative",
                        "keywords": "本地采购|当地采购",
                        "common_units": "万元|%",
                        "is_core": "True",
                    },
                ],
            )
            self._write_csv(
                base / "candidate_coverage.csv",
                [
                    {
                        "report_id": "r1",
                        "indicator_id": "e_ghg_total",
                        "indicator_name": "温室气体排放总量",
                        "dimension": "E",
                        "indicator_type": "quantitative",
                        "status": "candidate",
                        "candidate_count": "2",
                    },
                    {
                        "report_id": "r2",
                        "indicator_id": "e_ghg_total",
                        "indicator_name": "温室气体排放总量",
                        "dimension": "E",
                        "indicator_type": "quantitative",
                        "status": "candidate",
                        "candidate_count": "1",
                    },
                    {
                        "report_id": "r1",
                        "indicator_id": "s_local_procurement",
                        "indicator_name": "本地采购",
                        "dimension": "S",
                        "indicator_type": "quantitative",
                        "status": "missing",
                        "candidate_count": "0",
                    },
                    {
                        "report_id": "r2",
                        "indicator_id": "s_local_procurement",
                        "indicator_name": "本地采购",
                        "dimension": "S",
                        "indicator_type": "quantitative",
                        "status": "candidate",
                        "candidate_count": "1",
                    },
                ],
            )
            self._write_csv(base / "extraction_results.csv", [])
            self._write_csv(
                base / "quality_review_sample.csv",
                [
                    {
                        "report_id": "r1",
                        "indicator_id": "e_ghg_total",
                        "indicator_name": "温室气体排放总量",
                        "dimension": "E",
                        "indicator_type": "quantitative",
                        "status": "candidate",
                        "value": "",
                        "unit": "",
                        "qualitative_text": "",
                        "page_no": "1",
                        "block_id": "b1",
                        "block_type": "table",
                        "evidence_quote": "温室气体排放总量 | 吨二氧化碳当量 | 113,126.46",
                    },
                    {
                        "report_id": "r2",
                        "indicator_id": "s_local_procurement",
                        "indicator_name": "本地采购",
                        "dimension": "S",
                        "indicator_type": "quantitative",
                        "status": "candidate",
                        "value": "",
                        "unit": "",
                        "qualitative_text": "",
                        "page_no": "2",
                        "block_id": "b2",
                        "block_type": "paragraph",
                        "evidence_quote": "采购流程持续优化。",
                    },
                ],
            )

            summary = run_review(project_root=root, use_llm=False)

            self.assertEqual(summary["reviewed_rows"], 2)
            for name in [
                "quality_review_ai_labeled.csv",
                "quality_review_metrics.csv",
                "indicator_pruning_suggestions.csv",
                "formal_v1_quality_review.md",
            ]:
                self.assertTrue((base / name).is_file(), name)
            with (base / "quality_review_ai_labeled.csv").open(encoding="utf-8-sig") as fh:
                labeled = list(csv.DictReader(fh))
            labels = {row["ai_label"] for row in labeled}
            self.assertLessEqual(labels, {"correct", "partial", "wrong", "uncertain"})
            self.assertIn("correct", labels)
            self.assertIn("wrong", labels)
            with (base / "indicator_pruning_suggestions.csv").open(encoding="utf-8-sig") as fh:
                suggestions = list(csv.DictReader(fh))
            decisions = {row["decision"] for row in suggestions}
            self.assertLessEqual(decisions, {"keep", "revise_keywords", "merge_or_redefine", "drop", "need_more_review"})
            report = (base / "formal_v1_quality_review.md").read_text(encoding="utf-8")
            self.assertIn("AI-assisted quality review", report)
            self.assertIn("辅助质检预标注", report)

    def _write_csv(self, path: Path, rows: list[dict]) -> None:
        if not rows:
            path.write_text("", encoding="utf-8")
            return
        with path.open("w", encoding="utf-8-sig", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)


if __name__ == "__main__":
    unittest.main()
