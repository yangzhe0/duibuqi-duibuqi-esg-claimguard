import csv
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


class FormalV3Tests(unittest.TestCase):
    def test_empty_vlm_table_is_backfilled_from_same_page_model_bbox(self):
        import scripts.run_esg_formal_v3 as formal_v3

        with tempfile.TemporaryDirectory(dir=formal_v3.PROJECT_ROOT / "outputs") as tmp:
            root = Path(tmp)
            report_id = "r-table"
            parsed = formal_v3.canonical_json(root, report_id)
            parsed.parent.mkdir(parents=True)
            parsed.write_text(
                json.dumps(
                    [
                        [
                            {
                                "type": "table",
                                "bbox": [101, 200, 300, 399],
                                "content": {"html": "", "image_source": {"path": "images/"}},
                            }
                        ]
                    ]
                ),
                encoding="utf-8",
            )
            (parsed.parent / f"{report_id}_model.json").write_text(
                json.dumps(
                    [
                        [
                            {
                                "type": "table",
                                "bbox": [0.1, 0.2, 0.3, 0.4],
                                "content": "<table><tr><td>员工</td><td>20人</td></tr></table>",
                            }
                        ]
                    ]
                ),
                encoding="utf-8",
            )
            summary = formal_v3.repair_empty_vlm_tables(root, {"reports": [{"report_id": report_id}]})
            repaired = json.loads(parsed.read_text())
            self.assertEqual(summary["tables_repaired_total"], 1)
            self.assertIn("20人", repaired[0][0]["content"]["html"])
            self.assertEqual(repaired[0][0]["content"]["image_source"]["path"], "")

    def test_failed_qwen_preflight_is_archived_and_retried(self):
        import scripts.run_esg_formal_v3 as formal_v3

        class FakeClient:
            def generate(self, prompt: str) -> str:
                return json.dumps({"status": "missing"})

        with tempfile.TemporaryDirectory(dir=formal_v3.PROJECT_ROOT / "outputs") as tmp:
            root = Path(tmp)
            output = root / "extraction/qwen_preflight.json"
            output.parent.mkdir(parents=True)
            output.write_text(json.dumps({"config_sha256": "a" * 64, "passed": False}), encoding="utf-8")
            indicator = SimpleNamespace(
                indicator_id="g_test",
                name="测试",
                dimension="G",
                indicator_type="boolean",
            )
            candidates = [{"block_id": "r:p1:b0", "page_no": 1, "block_type": "paragraph", "text": "测试证据"}]
            manifest = {
                "config_sha256": "a" * 64,
                "extraction_config": {"context_tokens": 8192, "max_output_tokens": 1024},
            }
            with (
                mock.patch.object(formal_v3, "_load_indicators", return_value=[indicator]),
                mock.patch.object(formal_v3, "load_content_list", return_value=[[{}]]),
                mock.patch.object(formal_v3, "flatten_report", return_value=[{}]),
                mock.patch.object(formal_v3, "select_candidate_blocks", return_value=candidates),
                mock.patch.object(formal_v3, "_build_v2_prompt", side_effect=["x" * size for size in range(100, 106)]),
                mock.patch.object(formal_v3, "build_llm_client", return_value=FakeClient()),
                mock.patch.object(formal_v3, "llama_token_count", side_effect=range(100, 106)),
            ):
                payload = formal_v3.run_qwen_preflight(
                    root,
                    manifest,
                    "http://unused",
                    [Path(f"/tmp/r{index}/content.json") for index in range(6)],
                )
            self.assertTrue(payload["passed"])
            self.assertEqual(len(payload["cases"]), 5)
            self.assertEqual(len(list(output.parent.glob("qwen_preflight_failed_*.json"))), 1)

    def test_safe_output_root_rejects_protected_trees(self):
        from scripts.run_esg_formal_v3 import PROJECT_ROOT, safe_output_root

        with self.assertRaises(ValueError):
            safe_output_root(PROJECT_ROOT / "data/new")
        with self.assertRaises(ValueError):
            safe_output_root(PROJECT_ROOT / "data/new")
        accepted = safe_output_root(PROJECT_ROOT / "outputs/formal_v3_test")
        self.assertEqual(accepted, (PROJECT_ROOT / "outputs/formal_v3_test").resolve())

    def test_valid_content_list(self):
        from scripts.run_esg_formal_v3 import valid_content_list

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "content.json"
            path.write_text(json.dumps([[{"type": "text", "content": "ESG"}]]), encoding="utf-8")
            self.assertTrue(valid_content_list(path))
            self.assertTrue(valid_content_list(path, 1))
            self.assertFalse(valid_content_list(path, 2))
            path.write_text("[]", encoding="utf-8")
            self.assertFalse(valid_content_list(path))

    def test_extraction_resume_contract_detects_parsed_change(self):
        from scripts.run_esg_formal_v3 import PROJECT_ROOT, canonical_json, ensure_extraction_contract

        with tempfile.TemporaryDirectory(dir=PROJECT_ROOT / "outputs") as tmp:
            root = Path(tmp)
            report_id = "r001"
            parsed = canonical_json(root, report_id)
            parsed.parent.mkdir(parents=True)
            parsed.write_text("[[{\"type\": \"text\"}]]", encoding="utf-8")
            manifest = {
                "run_id": "test-run",
                "config_sha256": "a" * 64,
                "indicator_pool": {"sha256": "b" * 64},
                "extraction_config": {"context_tokens": 8192, "max_output_tokens": 1024},
                "reports": [{"report_id": report_id}],
            }
            with mock.patch("scripts.run_esg_formal_v3.runtime_fingerprints", return_value={"model": {"sha256": "c" * 64}}):
                ensure_extraction_contract(root, manifest)
                parsed.write_text("[[{\"type\": \"table\"}]]", encoding="utf-8")
                with self.assertRaises(RuntimeError):
                    ensure_extraction_contract(root, manifest)

    def test_validation_accepts_exact_contract(self):
        from scripts.run_esg_formal_v3 import EXPECTED_REPORTS, INDICATOR_POOL, _read_csv, sha256, validate_all

        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1] / "outputs") as tmp:
            root = Path(tmp)
            reports = [{"report_id": f"r{i:03d}", "pages": 1} for i in range(EXPECTED_REPORTS)]
            indicator_ids = [row["indicator_id"] for row in _read_csv(INDICATOR_POOL)]
            for report in reports:
                parsed = root / "parsed" / report["report_id"] / f"{report['report_id']}_content_list_v2.json"
                parsed.parent.mkdir(parents=True)
                parsed.write_text("[[{\"type\": \"text\"}]]", encoding="utf-8")
            extraction = root / "extraction"
            extraction.mkdir()
            fields = ["report_id", "indicator_id", "status", "run_id", "pdf_sha256", "parsed_sha256", "llm_model"]
            with (extraction / "extraction_results.csv").open("w", encoding="utf-8-sig", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=fields)
                writer.writeheader()
                for report in reports:
                    for indicator_id in indicator_ids:
                        writer.writerow(
                            {
                                "report_id": report["report_id"],
                                "indicator_id": indicator_id,
                                "status": "missing",
                                "run_id": "test-full200",
                                "pdf_sha256": "a" * 64,
                                "parsed_sha256": "b" * 64,
                                "llm_model": "qwen3.6-27b-q4_k_m",
                            }
                        )
            (extraction / "run_summary.json").write_text(
                json.dumps(
                    {
                        "model": "qwen3.6-27b-q4_k_m",
                        "llm_api": "openai",
                        "llm_error_count": 0,
                        "reports": EXPECTED_REPORTS,
                        "indicators": len(indicator_ids),
                        "results": EXPECTED_REPORTS * len(indicator_ids),
                        "report_ids": [report["report_id"] for report in reports],
                    }
                ),
                encoding="utf-8",
            )
            shutil.copy2(INDICATOR_POOL, root / "indicator_pool.csv")
            (root / "cohort_manifest.json").write_text(
                json.dumps({"report_count": EXPECTED_REPORTS, "page_count": EXPECTED_REPORTS}), encoding="utf-8"
            )
            parser_root = root / "parser"
            parser_root.mkdir()
            (parser_root / "parse_attempts_summary.json").write_text(
                json.dumps(
                    {
                        "retained_attempt_report_coverage": EXPECTED_REPORTS,
                        "canonical_without_retained_attempt_count": 0,
                        "canonical_report_count": EXPECTED_REPORTS,
                    }
                ),
                encoding="utf-8",
            )
            with mock.patch(
                "scripts.run_esg_formal_v3.validate_data001_corrections",
                return_value={"passed": True, "correction_count": 4, "failure_count": 0, "failures": []},
            ):
                validation = validate_all(
                    root,
                    {
                        "run_id": "test-full200",
                        "page_count": EXPECTED_REPORTS,
                        "reports": reports,
                        "indicator_pool": {
                            "path": "outputs/formal_v3_mineru25_qwen36/indicator_pool.csv",
                            "sha256": sha256(INDICATOR_POOL),
                        },
                    },
                )
            self.assertTrue(validation["passed"])


if __name__ == "__main__":
    unittest.main()
