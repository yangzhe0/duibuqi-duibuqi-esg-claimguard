import tempfile
import unittest
from collections import Counter
from pathlib import Path
from unittest.mock import patch
from urllib.parse import quote, unquote

from dashboard_api import repository
from dashboard_api.audit import audit_queue, audit_summary
from dashboard_api.reviews import ReviewStore
from dashboard_api.tasks import report_metadata
from dashboard_api.preaudit import claim_graph, export_workpaper_csv, preaudit_issues, preaudit_summary
from dashboard_api.natural_gold import (
    build_manifest,
    load_manifest,
    natural_gold_evaluation,
    natural_gold_summary,
    natural_gold_tasks,
    validate_annotation,
)
from dashboard_api.natural_gold_pilot import (
    PILOT_QUOTAS,
    _normalize_confidence,
    build_pilot,
    generate_silver_drafts,
    load_pilot,
    retrieve_silver_a,
    retrieve_silver_b,
)


class DashboardRepositoryTests(unittest.TestCase):
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
        self.assertEqual(payload.count(b"\n"), expected_rows + 1)


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

    def test_pilot30_is_frozen_stratified_and_uses_unique_indicators(self):
        with tempfile.TemporaryDirectory() as directory:
            payload = build_pilot(output_dir=Path(directory))
            rows = payload["rows"]
            self.assertEqual(len(rows), 30)
            self.assertEqual(Counter(row["dimension"] for row in rows), {"E": 10, "S": 10, "G": 10})
            self.assertEqual(len({row["indicator_id"] for row in rows}), 30)
            expected = {f"{dimension}/{kind}": count for dimension, kinds in PILOT_QUOTAS.items() for kind, count in kinds.items()}
            self.assertEqual(Counter(row["stratum"] for row in rows), expected)
            self.assertTrue(payload["metadata"]["silver_only"])

    def test_silver_retrievers_use_different_context_contracts(self):
        indicator = {
            "indicator_name": "客户满意度",
            "indicator_type": "quantitative",
            "keywords": "客户满意度|顾客满意度",
            "original_keywords": "客户满意度|满意度调查",
            "common_units": "%|分",
        }
        blocks = [
            {"page_no": 1, "block_index": 0, "block_id": "r:p1:b0", "block_type": "paragraph", "text": "客户服务"},
            {"page_no": 1, "block_index": 1, "block_id": "r:p1:b1", "block_type": "table", "text": "客户满意度 | % | 98"},
            {"page_no": 1, "block_index": 2, "block_id": "r:p1:b2", "block_type": "paragraph", "text": "调查范围为境内客户"},
        ]
        narrow = retrieve_silver_a(blocks, indicator)
        broad = retrieve_silver_b(blocks, indicator)
        self.assertEqual([row["block_id"] for row in narrow], ["r:p1:b1"])
        self.assertEqual([row["block_id"] for row in broad], ["r:p1:b0", "r:p1:b1", "r:p1:b2"])

    def test_silver_confidence_accepts_numeric_and_chinese_values(self):
        self.assertEqual(_normalize_confidence(0.9), ("high", True))
        self.assertEqual(_normalize_confidence("中"), ("medium", True))
        self.assertEqual(_normalize_confidence("0.2"), ("low", True))
        self.assertEqual(_normalize_confidence("大概"), ("low", False))

    def test_silver_empty_retrieval_never_infers_missing_or_calls_model(self):
        task = load_pilot()[0]
        with tempfile.TemporaryDirectory() as directory:
            with patch("dashboard_api.natural_gold_pilot._load_blocks", return_value=[]):
                with patch("dashboard_api.natural_gold_pilot._ollama_generate", side_effect=AssertionError("must not call model")):
                    rows = generate_silver_drafts(
                        "silver_a",
                        pilot_rows=[task],
                        output_dir=Path(directory),
                        resume=False,
                    )
        self.assertEqual(rows[0]["disclosure"], "uncertain")
        self.assertEqual(rows[0]["validation_errors"], "no_candidate_retrieval")
        self.assertEqual(rows[0]["raw_response_sha256"], "")

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
