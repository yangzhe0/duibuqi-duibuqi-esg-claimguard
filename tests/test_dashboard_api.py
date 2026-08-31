import csv
import hashlib
import io
import json
import tempfile
import threading
import unittest
from collections import Counter
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import urlopen
from urllib.parse import quote, unquote

from dashboard_api import repository
from dashboard_api.audit import audit_queue, audit_summary
from dashboard_api.reviews import ReviewStore
from dashboard_api.tasks import PROJECT_ROOT, TaskManager, report_metadata
from dashboard_api.server import DashboardHandler
from http.server import ThreadingHTTPServer
from dashboard_api.model_runtime import GGML_CUDA_BACKEND, QWEN_MMPROJ_PATH, llama_server_command, runtime_assets
from dashboard_api.preaudit import claim_graph, export_workpaper_csv, preaudit_issues, preaudit_summary
from dashboard_api.natural_gold import (
    build_manifest,
    load_manifest,
    natural_gold_evaluation,
    natural_gold_summary,
    natural_gold_tasks,
    validate_annotation,
)


class DashboardRepositoryTests(unittest.TestCase):
    def tearDown(self):
        repository.clear_caches()

    def test_chinese_upload_filename_round_trip(self):
        filename = "示例企业_中文测试文档.pdf"
        self.assertEqual(unquote(quote(filename)), filename)

    def test_summary_uses_formal_results(self):
        summary = repository.summary()
        self.assertGreaterEqual(summary["report_count"], 200)
        self.assertEqual(summary["indicator_count"], 65)
        self.assertEqual(summary["total_results"], summary["report_count"] * 65)

    def test_evidence_resolves_block_bbox(self):
        row = next(row for row in repository.results() if row["status"] == "found")
        item = repository.evidence(row["report_id"], row["block_id"])
        if item is None and not repository.PARSED_ROOT.is_dir():
            self.skipTest("full parsed evidence assets are intentionally absent from the lightweight snapshot")
        self.assertIsNotNone(item)
        self.assertEqual(item["page_no"], int(row["page_no"]))
        self.assertEqual(len(item["bbox"]), 4)

    def test_query_results_filters_and_paginates(self):
        payload = repository.query_results({"dimension": "E", "status": "found", "limit": "7"})
        self.assertEqual(len(payload["items"]), 7)
        self.assertGreater(payload["total"], 7)
        self.assertTrue(all(row["dimension"] == "E" for row in payload["items"]))

    def test_csv_export_keeps_filtered_rows(self):
        report_id = repository.results()[0]["report_id"]
        expected_rows = sum(row["report_id"] == report_id for row in repository.results())
        payload = repository.export_csv({"report_id": report_id})
        self.assertTrue(payload.startswith(b"\xef\xbb\xbf"))
        decoded = payload.decode("utf-8-sig")
        self.assertEqual(len(list(csv.DictReader(decoded.splitlines()))), expected_rows)

    def test_default_snapshot_never_merges_or_overwrites_with_task_outputs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            baseline = root / "extraction/extraction_results.csv"
            baseline.parent.mkdir(parents=True)
            task_result = root / "tasks/task-1/extraction/extraction_results.csv"
            task_result.parent.mkdir(parents=True)
            self._write_results(baseline, [self._row("baseline-report", "missing")])
            self._write_results(task_result, [self._row("baseline-report", "found")])
            (root / "run_manifest.json").write_text(json.dumps({"run_id": "run-current"}), encoding="utf-8")
            (root / "validation.json").write_text(json.dumps({"passed": True}), encoding="utf-8")
            (root / "COMPLETE.json").write_text(
                json.dumps({"run_id": "run-current", "is_full_200": True, "validation_passed": True}),
                encoding="utf-8",
            )
            with patch.object(repository, "FORMAL_V3_ROOT", root):
                repository.clear_caches()
                rows = repository.results()
                self.assertEqual(len(rows), 1)
                self.assertEqual(rows[0]["status"], "missing")
                self.assertEqual(rows[0]["dataset_id"], repository.CURRENT_DATASET_ID)

    def test_formal_v3_is_selectable_only_after_complete_and_validation_pass(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result_path = root / "extraction/extraction_results.csv"
            result_path.parent.mkdir(parents=True)
            self._write_results(result_path, [self._row("v3-report", "found")])
            (root / "run_manifest.json").write_text(json.dumps({"run_id": "run-v3"}), encoding="utf-8")
            (root / "validation.json").write_text(json.dumps({"passed": False}), encoding="utf-8")
            with patch.object(repository, "FORMAL_V3_ROOT", root):
                repository.clear_caches()
                self.assertNotIn(
                    repository.CURRENT_DATASET_ID,
                    {item["dataset_id"] for item in repository.available_datasets()["items"]},
                )
                with self.assertRaises(ValueError):
                    repository.results(repository.CURRENT_DATASET_ID)

                (root / "validation.json").write_text(
                    json.dumps({"passed": True, "counts": {"result_rows": 1}}), encoding="utf-8"
                )
                (root / "COMPLETE.json").write_text(
                    json.dumps(
                        {
                            "run_id": "run-v3",
                            "completed_at": "2026-08-22T00:00:00Z",
                            "scope_type": "full200",
                            "is_full_200": True,
                            "validation_passed": True,
                        }
                    ),
                    encoding="utf-8",
                )
                rows = repository.results(repository.CURRENT_DATASET_ID)
                quality = repository.quality_metrics(repository.CURRENT_DATASET_ID)
                audit = audit_summary([], "v3-report", repository.CURRENT_DATASET_ID)
                preaudit = preaudit_summary([], "v3-report", repository.CURRENT_DATASET_ID)
                self.assertEqual(rows[0]["dataset_id"], repository.CURRENT_DATASET_ID)
                self.assertEqual(rows[0]["run_id"], "run-v3")
                self.assertTrue(quality["passed"])
                self.assertEqual(quality["run_id"], "run-v3")
                self.assertEqual(audit["run_id"], "run-v3")
                self.assertEqual(preaudit["run_id"], "run-v3")

    @staticmethod
    def _row(report_id: str, status: str) -> dict[str, str]:
        return {
            "report_id": report_id,
            "indicator_id": "e_test",
            "indicator_name": "测试指标",
            "dimension": "E",
            "indicator_type": "qualitative",
            "status": status,
            "value": "",
            "unit": "",
            "qualitative_text": "测试披露" if status == "found" else "",
            "evidence_quote": "测试披露" if status == "found" else "",
            "page_no": "1" if status == "found" else "",
            "block_id": f"{report_id}:p1:b0" if status == "found" else "",
            "block_type": "text" if status == "found" else "",
            "source_candidate_count": "1" if status == "found" else "0",
            "elapsed_seconds": "0.1" if status == "found" else "0",
        }

    @staticmethod
    def _write_results(path: Path, rows: list[dict[str, str]]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)


class ReviewStoreTests(unittest.TestCase):
    def test_upsert_and_metrics(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ReviewStore(Path(directory) / "reviews.sqlite3")
            store.upsert({"report_id": "r1", "indicator_id": "i1", "label": "correct"})
            store.upsert({"report_id": "r2", "indicator_id": "i1", "label": "missed"})
            metrics = store.metrics()
            self.assertEqual(metrics["reviewed_count"], 2)
            self.assertIsNone(metrics["precision"])
            self.assertIsNone(metrics["recall"])
            self.assertEqual(metrics["metrics_status"], "workflow_labels_only")

    def test_invalid_label_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ReviewStore(Path(directory) / "reviews.sqlite3")
            with self.assertRaises(ValueError):
                store.upsert({"report_id": "r1", "indicator_id": "i1", "label": "unknown"})

    def test_issue_action_round_trip(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ReviewStore(Path(directory) / "reviews.sqlite3")
            saved = store.upsert_issue_action(
                {"issue_id": "issue-1", "report_id": "report-1", "action": "resolved", "note": "已核对", "reviewer": "tester"}
            )
            self.assertEqual(saved["action"], "resolved")
            rows = store.issue_actions("report-1")
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["note"], "已核对")

    def test_invalid_issue_action_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ReviewStore(Path(directory) / "reviews.sqlite3")
            with self.assertRaises(ValueError):
                store.upsert_issue_action({"issue_id": "issue-1", "report_id": "report-1", "action": "delete"})


class PipelineTaskTests(unittest.TestCase):
    def test_upload_metadata_is_derived_without_filename_special_cases(self):
        metadata = report_metadata("123456_示例企业_2025_可持续发展报告.pdf", "a" * 64)
        self.assertEqual(metadata["stock_code"], "123456")
        self.assertEqual(metadata["company"], "示例企业")
        self.assertEqual(metadata["year"], "2025")
        self.assertEqual(metadata["report_type"], "可持续发展报告")
        self.assertEqual(metadata["id"], "upload-" + "a" * 16)

    def test_default_qwen_runtime_assets_and_text_command_are_ready(self):
        assets = runtime_assets()
        self.assertTrue(assets["server"]["ready"])
        self.assertTrue(assets["model"]["ready"])
        self.assertTrue(assets["mmproj"]["ready"])
        self.assertTrue(assets["cuda_backend"]["ready"])
        command = llama_server_command(12345)
        self.assertIn("qwen3.6-27b-q4_k_m", command)
        self.assertNotIn(str(QWEN_MMPROJ_PATH), command)
        self.assertTrue(GGML_CUDA_BACKEND.is_file())

    def test_visual_review_runtime_adds_projection_only_when_requested(self):
        command = llama_server_command(12345, include_vision=True)
        self.assertIn("--mmproj", command)
        self.assertIn(str(QWEN_MMPROJ_PATH), command)

    def test_upload_registration_keeps_frozen_ledgers_byte_identical(self):
        ledgers = [PROJECT_ROOT / "data/report_index.csv", PROJECT_ROOT / "data/download_log.csv"]
        before = {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in ledgers}
        with tempfile.TemporaryDirectory() as directory:
            manager = TaskManager(Path(directory))
            payload = b"%PDF-1.4\n%%EOF\n"
            with patch.object(manager._executor, "submit"):
                task = manager.create_upload("123456_隔离上传_2025_ESG报告.pdf", len(payload), io.BytesIO(payload))
            staged = Path(directory) / task["task_id"] / "upload.pdf"
            manager._register_pdf(task, staged)
            metadata_path = staged.parent / "report_metadata.json"
            self.assertTrue(metadata_path.is_file())
            self.assertEqual(json.loads(metadata_path.read_text(encoding="utf-8"))["local_path"], "upload.pdf")
            self.assertEqual(sorted(path.name for path in staged.parent.iterdir()), ["report_metadata.json", "task.json", "upload.pdf"])
            manager._executor.shutdown(wait=True)
        after = {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in ledgers}
        self.assertEqual(before, after)

    def test_completed_task_http_contract_and_unknown_formal_report(self):
        with tempfile.TemporaryDirectory() as directory:
            task_id = "a" * 32
            report_id = "task-only-report"
            root = Path(directory)
            task_dir = root / task_id
            (task_dir / "extraction").mkdir(parents=True)
            parsed_dir = task_dir / "parsed" / report_id
            parsed_dir.mkdir(parents=True)
            (task_dir / "upload.pdf").write_bytes(b"%PDF-1.4\n%%EOF\n")
            (task_dir / "task.json").write_text(json.dumps({
                "task_id": task_id, "report_id": report_id, "filename": f"{report_id}.pdf",
                "sha256": "b" * 64, "size": 15, "status": "completed", "stage": "completed",
                "progress": 100, "message": "completed", "created_at": "2026-08-25T00:00:00Z",
                "updated_at": "2026-08-25T00:01:00Z", "error": "",
            }), encoding="utf-8")
            row = self._task_row(report_id)
            with (task_dir / "extraction/extraction_results.csv").open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=list(row))
                writer.writeheader(); writer.writerow(row)
            (parsed_dir / f"{report_id}_content_list_v2.json").write_text(
                json.dumps([[{"type": "text", "bbox": [1, 2, 3, 4], "content": {"text": "任务证据原文"}}]], ensure_ascii=False),
                encoding="utf-8",
            )
            manager = TaskManager(root)

            class Handler(DashboardHandler):
                task_manager = manager

            server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base = f"http://127.0.0.1:{server.server_address[1]}"
            try:
                summary = json.load(urlopen(f"{base}/api/tasks/{task_id}/summary"))
                results = json.load(urlopen(f"{base}/api/tasks/{task_id}/results"))
                preaudit = json.load(urlopen(f"{base}/api/tasks/{task_id}/preaudit"))
                evidence = json.load(urlopen(f"{base}/api/tasks/{task_id}/evidence?block_id={report_id}:p1:b0"))
                pdf = urlopen(f"{base}/api/tasks/{task_id}/pdf").read()
                self.assertEqual(summary["dataset_id"], f"task:{task_id}")
                self.assertEqual(summary["total_results"], 1)
                self.assertEqual(results["items"][0]["report_id"], report_id)
                self.assertEqual(preaudit["scope"], "single_upload")
                self.assertEqual(evidence["text"], "任务证据原文")
                self.assertTrue(pdf.startswith(b"%PDF-"))
                with self.assertRaises(HTTPError) as caught:
                    urlopen(f"{base}/api/preaudit/summary?report_id=definitely-not-formal")
                self.assertEqual(caught.exception.code, 404)
            finally:
                server.shutdown(); server.server_close(); thread.join(timeout=5)
                manager._executor.shutdown(wait=True)

    @staticmethod
    def _task_row(report_id: str) -> dict[str, str]:
        return {
            "report_id": report_id, "indicator_id": "e_test", "indicator_name": "测试指标",
            "dimension": "E", "indicator_type": "qualitative", "status": "found", "value": "",
            "unit": "", "qualitative_text": "任务证据原文", "evidence_quote": "任务证据原文",
            "page_no": "1", "block_id": f"{report_id}:p1:b0", "block_type": "text",
            "source_candidate_count": "1", "elapsed_seconds": "0.1",
        }


class EvidenceRiskGraphTests(unittest.TestCase):
    def test_global_audit_summary_exposes_actionable_signals(self):
        payload = audit_summary([])
        self.assertEqual(payload["total_items"], len(repository.results()))
        self.assertGreater(payload["known_risk_count"], 0)
        self.assertGreater(payload["actionable_gap_count"], 0)
        self.assertGreater(payload["uncertain_count"], 0)
        self.assertEqual(payload["method"]["formula"], "100 × (0.35R + 0.25U + 0.25G + 0.15F)")

    def test_queue_is_explainable_and_peer_gaps_have_examples(self):
        report_id = audit_summary([])["suggested_report_id"]
        items = audit_queue([], report_id, 65)["items"]
        self.assertEqual(len(items), 65)
        self.assertTrue(all("signals" in item and item["priority_reasons"] for item in items))
        gaps = [item for item in items if item["category"] == "gap"]
        self.assertTrue(gaps)
        self.assertTrue(any(item["peer_examples"] for item in gaps))

    def test_review_feedback_removes_completed_item_from_default_queue(self):
        report_id = audit_summary([])["suggested_report_id"]
        first = audit_queue([], report_id, 1)["items"][0]
        review = {"report_id": first["report_id"], "indicator_id": first["indicator_id"], "label": "correct"}
        remaining = audit_queue([review], report_id, 65)["items"]
        self.assertFalse(any(item["indicator_id"] == first["indicator_id"] for item in remaining))
        reviewed = audit_queue([review], report_id, 65, include_reviewed=True)["items"]
        saved = next(item for item in reviewed if item["indicator_id"] == first["indicator_id"])
        self.assertTrue(saved["reviewed"])
        self.assertLess(saved["priority_score"], first["priority_score"])


class ClaimEvidencePreauditTests(unittest.TestCase):
    def setUp(self):
        self.report_id = preaudit_summary([], "")["suggested_report_id"]

    def test_graph_contains_real_nodes_and_queryable_relations(self):
        graph = claim_graph(self.report_id)
        self.assertGreater(graph["stats"]["claim_count"], 0)
        self.assertGreater(graph["stats"]["evidence_count"], 0)
        relation_types = {edge["type"] for edge in graph["edges"]}
        self.assertIn("supports", relation_types)
        self.assertIn("governed_by", relation_types)
        self.assertEqual(graph["stats"]["node_count"], len(graph["nodes"]))

    def test_issue_register_uses_severity_not_unvalidated_score(self):
        issues = preaudit_issues([], self.report_id, include_closed=True)["items"]
        self.assertTrue(issues)
        self.assertTrue(any(item["severity"] == "blocking" for item in issues))
        self.assertTrue(all("priority_score" not in item for item in issues))
        self.assertTrue(all(item["evidence"] or item["requirement"] for item in issues))

    def test_calculable_constraint_exposes_inputs_and_formula_when_available(self):
        issues = preaudit_issues([], self.report_id, include_closed=True)["items"]
        calculations = [item for item in issues if item["calculation"]]
        self.assertTrue(calculations)
        self.assertTrue(all(len(item["evidence"]) >= 3 for item in calculations))
        self.assertTrue(all(item["calculation"].get("formula") and item["calculation"].get("display") for item in calculations))

    def test_resolved_action_closes_issue_and_workpaper_keeps_trace(self):
        first = preaudit_issues([], self.report_id, include_closed=True)["items"][0]
        action = {
            "issue_id": first["issue_id"],
            "report_id": self.report_id,
            "action": "resolved",
            "note": "测试处置",
            "reviewer": "tester",
            "updated_at": "2026-08-09T00:00:00+00:00",
        }
        updated = preaudit_issues([action], self.report_id, include_closed=True)["items"]
        saved = next(item for item in updated if item["issue_id"] == first["issue_id"])
        self.assertTrue(saved["closed"])
        self.assertEqual(saved["action_note"], "测试处置")
        workpaper = export_workpaper_csv([action], self.report_id)
        self.assertTrue(workpaper.startswith(b"\xef\xbb\xbf"))
        self.assertIn("测试处置".encode("utf-8"), workpaper)


class NaturalGoldTests(unittest.TestCase):
    def setUp(self):
        if not load_manifest():
            self.skipTest("optional independent-evaluation fixtures are not part of the final public snapshot")

    def test_manifest_is_deterministic_balanced_and_model_blind(self):
        with tempfile.TemporaryDirectory() as directory:
            first = build_manifest(Path(directory))
            second = build_manifest(Path(directory))
            rows = first["rows"]
            self.assertEqual(first["metadata"]["manifest_sha256"], second["metadata"]["manifest_sha256"])
            self.assertEqual(len(rows), 300)
            self.assertEqual(Counter(row["dimension"] for row in rows), {"E": 100, "S": 100, "G": 100})
            self.assertEqual(len({row["indicator_id"] for row in rows}), 65)
            self.assertFalse(any("status" in row or "value" in row or "evidence_quote" in row for row in rows))

    def test_blind_roles_do_not_receive_peer_or_model_output(self):
        task = load_manifest()[0]
        annotations = [self._annotation(task, "annotator_a", "missing", "Alice")]
        item = natural_gold_tasks(annotations, "annotator_a", manifest_rows=[task])["items"][0]
        self.assertTrue(item["blinded"])
        self.assertFalse(item["model_output_visible"])
        self.assertNotIn("annotations", item)
        self.assertEqual(item["annotation"]["reviewer"], "Alice")

    def test_double_annotation_disagreement_and_third_person_adjudication(self):
        task = load_manifest()[0]
        with tempfile.TemporaryDirectory() as directory:
            store = ReviewStore(Path(directory) / "reviews.sqlite3")
            a = validate_annotation(self._annotation(task, "annotator_a", "missing", "Alice"), task, [])
            store.upsert_natural_gold_annotation(a)
            with self.assertRaises(ValueError):
                validate_annotation(self._annotation(task, "annotator_b", "found", "Alice"), task, store.natural_gold_annotations(task["task_id"]))
            b_payload = self._annotation(task, "annotator_b", "found", "Bob")
            b_payload.update({"value": "100", "evidence_pages": "2", "evidence_text": "原文证据"})
            b = validate_annotation(b_payload, task, store.natural_gold_annotations(task["task_id"]))
            store.upsert_natural_gold_annotation(b)
            summary = natural_gold_summary(store.natural_gold_annotations(), [task], {"manifest_state": "frozen"})
            self.assertEqual(summary["disagreements"], 1)
            self.assertEqual(summary["gold_count"], 0)
            adjudication = validate_annotation(
                self._annotation(task, "adjudicator", "missing", "Carol"),
                task,
                store.natural_gold_annotations(task["task_id"]),
            )
            store.upsert_natural_gold_annotation(adjudication)
            summary = natural_gold_summary(store.natural_gold_annotations(), [task], {"manifest_state": "frozen"})
            self.assertEqual(summary["adjudicated"], 1)
            self.assertEqual(summary["gold_count"], 1)
            self.assertTrue(summary["ready_to_evaluate"])

    def test_metrics_are_withheld_until_every_task_has_gold(self):
        tasks = load_manifest()[:2]
        annotations = [
            self._annotation(tasks[0], "annotator_a", "missing", "Alice"),
            self._annotation(tasks[0], "annotator_b", "missing", "Bob"),
        ]
        payload = natural_gold_evaluation(annotations, tasks, [])
        self.assertEqual(payload["status"], "not_ready")
        self.assertEqual(payload["metrics"], {})

    def test_evaluation_unlocks_only_after_complete_consensus(self):
        tasks = load_manifest()[:3]
        annotations = []
        predictions = []
        for task in tasks:
            annotations.extend(
                [
                    self._annotation(task, "annotator_a", "missing", "Alice"),
                    self._annotation(task, "annotator_b", "missing", "Bob"),
                ]
            )
            predictions.append({"report_id": task["report_id"], "indicator_id": task["indicator_id"], "status": "missing"})
        payload = natural_gold_evaluation(annotations, tasks, predictions)
        self.assertEqual(payload["status"], "ready")
        self.assertEqual(payload["metrics"]["disclosure_detection"]["tn"], 3)

    @staticmethod
    def _annotation(task: dict, role: str, disclosure: str, reviewer: str) -> dict:
        return {
            "task_id": task["task_id"],
            "role": role,
            "disclosure": disclosure,
            "subject": "",
            "period": "",
            "scope": "",
            "value": "",
            "unit": "",
            "evidence_pages": "",
            "evidence_text": "",
            "confidence": "medium",
            "note": "",
            "reviewer": reviewer,
        }


if __name__ == "__main__":
    unittest.main()
