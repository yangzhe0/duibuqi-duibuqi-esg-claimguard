import csv
import json
import os
import tempfile
import unittest
from pathlib import Path


class QualityAnalysisTests(unittest.TestCase):
    def test_quality_analysis_writes_metrics_and_risk_cases(self):
        from scripts.analyze_extraction_quality import analyze_quality
        from scripts.build_review_set import build_review_set
        from tests.test_review_set import ReviewSetTests

        helper = ReviewSetTests()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            results = root / "extraction_results.csv"
            pool = root / "indicator_pool_v2.csv"
            review_dir = root / "review"
            self._write_csv(pool, helper._indicator_rows())
            self._write_csv(results, helper._result_rows())
            build_review_set(results, pool, review_dir, sample_size=20)

            metrics = analyze_quality(results, pool, review_dir / "review_sample.csv", review_dir)

            self.assertTrue((review_dir / "quality_report.md").is_file())
            self.assertTrue((review_dir / "quality_metrics.json").is_file())
            self.assertTrue((review_dir / "risk_cases.csv").is_file())
            self.assertEqual(metrics["total_results"], 8)
            self.assertGreater(metrics["evidence_empty_count"], 0)
            self.assertGreater(metrics["possible_rate_as_count_count"], 0)
            self.assertGreater(metrics["possible_money_as_count_count"], 0)
            self.assertIn("concrete_risk_cases_count", metrics)
            self.assertGreater(metrics["concrete_risk_cases_count"], 0)
            self.assertIn("per_indicator_found_rate", metrics)
            with (review_dir / "risk_cases.csv").open(encoding="utf-8-sig", newline="") as fh:
                risk_rows = list(csv.DictReader(fh))
            self.assertGreaterEqual(len(risk_rows), 5)
            report = (review_dir / "quality_report.md").read_text(encoding="utf-8")
            self.assertIn("不等同于人工标注评价结论", report)
            self.assertFalse((root / "dashboard.html").exists())
            self.assertFalse((review_dir / "dashboard.html").exists())

    def test_default_paths_are_project_root_based(self):
        from scripts import analyze_extraction_quality

        with tempfile.TemporaryDirectory() as tmp:
            old_cwd = Path.cwd()
            try:
                os.chdir(tmp)
                self.assertTrue(analyze_extraction_quality.DEFAULT_RESULTS.is_absolute())
                self.assertTrue(analyze_extraction_quality.DEFAULT_POOL.is_absolute())
                self.assertTrue(analyze_extraction_quality.DEFAULT_REVIEW_SAMPLE.is_absolute())
                self.assertTrue(analyze_extraction_quality.DEFAULT_OUT_DIR.is_absolute())
                self.assertIn("contest_xiaoshumo", str(analyze_extraction_quality.DEFAULT_RESULTS))
            finally:
                os.chdir(old_cwd)

    def _write_csv(self, path: Path, rows: list[dict]) -> None:
        with path.open("w", encoding="utf-8-sig", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)


if __name__ == "__main__":
    unittest.main()
