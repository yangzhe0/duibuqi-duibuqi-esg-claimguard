import csv
import json
import os
import tempfile
import unittest
from pathlib import Path


class StreamlitDataTests(unittest.TestCase):
    def test_build_streamlit_data_writes_required_schema(self):
        from scripts.analyze_extraction_quality import analyze_quality
        from scripts.build_review_set import build_review_set
        from scripts.build_streamlit_data import build_streamlit_data
        from tests.test_review_set import ReviewSetTests

        helper = ReviewSetTests()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            results = root / "extraction_results.csv"
            pool = root / "indicator_pool_v2.csv"
            review_dir = root / "review"
            out_path = root / "system_ui" / "streamlit_data.json"
            self._write_csv(pool, helper._indicator_rows())
            self._write_csv(results, helper._result_rows())
            build_review_set(results, pool, review_dir, sample_size=20)
            analyze_quality(results, pool, review_dir / "review_sample.csv", review_dir)

            data = build_streamlit_data(
                results_path=results,
                indicator_pool_path=pool,
                metrics_path=review_dir / "quality_metrics.json",
                risk_cases_path=review_dir / "risk_cases.csv",
                review_sample_path=review_dir / "review_sample.csv",
                out_path=out_path,
            )

            self.assertTrue(out_path.is_file())
            saved = json.loads(out_path.read_text(encoding="utf-8"))
            for key in ["summary", "results", "reports", "indicators", "risk_cases", "review_samples"]:
                self.assertIn(key, saved)
                self.assertIn(key, data)
            self.assertIn("concrete_risk_cases_count", saved["summary"])
            self.assertGreater(len(saved["results"]), 0)
            self.assertGreater(len(saved["risk_cases"]), 0)
            self.assertFalse((root / "dashboard.html").exists())
            self.assertFalse((out_path.parent / "dashboard.html").exists())

    def test_default_paths_are_project_root_based(self):
        from scripts import build_streamlit_data

        with tempfile.TemporaryDirectory() as tmp:
            old_cwd = Path.cwd()
            try:
                os.chdir(tmp)
                self.assertTrue(build_streamlit_data.DEFAULT_RESULTS.is_absolute())
                self.assertTrue(build_streamlit_data.DEFAULT_POOL.is_absolute())
                self.assertTrue(build_streamlit_data.DEFAULT_OUT.is_absolute())
                self.assertIn("contest_xiaoshumo", str(build_streamlit_data.DEFAULT_OUT))
            finally:
                os.chdir(old_cwd)

    def _write_csv(self, path: Path, rows: list[dict]) -> None:
        with path.open("w", encoding="utf-8-sig", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)


if __name__ == "__main__":
    unittest.main()
