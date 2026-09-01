import json
import tempfile
import unittest
from pathlib import Path


class EsgDemoTests(unittest.TestCase):
    def _write_report(self, root: Path, report_id: str, text: str) -> None:
        report_dir = root / f"outputs/final_results/parsed/{report_id}"
        report_dir.mkdir(parents=True)
        json_path = report_dir / f"{report_id}_content_list_v2.json"
        json_path.write_text(
            json.dumps(
                [
                    [
                        {
                            "type": "paragraph",
                            "bbox": [0, 0, 10, 10],
                            "content": {"content": text},
                        }
                    ]
                ],
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    def test_default_model_is_qwen3_30b(self):
        from src.esg_demo.runner import DEFAULT_MODEL

        self.assertEqual(DEFAULT_MODEL, "qwen3:30b")

    def test_formal_indicator_pool_has_wide_esg_coverage(self):
        from src.esg_demo.indicators import FORMAL_INDICATORS

        self.assertGreaterEqual(len(FORMAL_INDICATORS), 80)
        self.assertEqual(len({indicator.indicator_id for indicator in FORMAL_INDICATORS}), len(FORMAL_INDICATORS))
        self.assertEqual({indicator.dimension for indicator in FORMAL_INDICATORS}, {"E", "S", "G"})
        self.assertTrue(all(indicator.keywords for indicator in FORMAL_INDICATORS))
        self.assertTrue(all(hasattr(indicator, "common_units") for indicator in FORMAL_INDICATORS))
        self.assertGreaterEqual(sum(1 for indicator in FORMAL_INDICATORS if indicator.is_core), 50)

    def test_flatten_blocks_extracts_text_and_table_fields(self):
        from src.esg_demo.blocks import flatten_report

        pages = [
            [
                {
                    "type": "list",
                    "bbox": [1, 2, 3, 4],
                    "content": {
                        "list_type": "text_list",
                        "list_items": [
                            {"item_content": [{"type": "text", "content": "能源消耗总量"}]},
                            {"item_content": [{"type": "text", "content": "100 吨标准煤"}]},
                        ],
                    },
                },
                {
                    "type": "table",
                    "bbox": [5, 6, 7, 8],
                    "content": {
                        "html": "<table><tr><td>温室气体排放总量</td><td>20</td><td>吨二氧化碳当量</td></tr></table>",
                        "table_type": "simple_table",
                        "table_nest_level": 1,
                        "table_caption": [{"type": "text", "content": "指标表"}],
                        "table_footnote": [{"type": "text", "content": "注：范围一和范围二"}],
                        "image_source": {"path": "images/table.jpg"},
                    },
                },
            ]
        ]

        rows = flatten_report("demo_report", Path("demo.json"), pages)

        self.assertEqual(rows[0]["block_id"], "demo_report:p1:b0")
        self.assertEqual(rows[0]["block_type"], "list")
        self.assertIn("能源消耗总量", rows[0]["text"])
        self.assertIn("100 吨标准煤", rows[0]["text"])
        self.assertEqual(rows[1]["table_type"], "simple_table")
        self.assertEqual(rows[1]["caption_text"], "指标表")
        self.assertEqual(rows[1]["footnote_text"], "注：范围一和范围二")
        self.assertEqual(rows[1]["image_path"], "images/table.jpg")
        self.assertIn("温室气体排放总量", rows[1]["text"])

    def test_select_candidate_blocks_filters_by_indicator_keywords(self):
        from src.esg_demo.extract import select_candidate_blocks
        from src.esg_demo.indicators import DEMO_INDICATORS

        indicator = next(i for i in DEMO_INDICATORS if i.indicator_id == "e_ghg_total")
        blocks = [
            {"block_id": "a", "block_type": "paragraph", "text": "董事会治理架构"},
            {
                "block_id": "b",
                "block_type": "table",
                "text": "温室气体排放总量 394.77 吨二氧化碳当量",
            },
        ]

        selected = select_candidate_blocks(blocks, indicator, max_blocks=5)

        self.assertEqual([row["block_id"] for row in selected], ["b"])

    def test_llm_status_is_found_when_payload_contains_extracted_content(self):
        from src.esg_demo.extract import normalize_llm_result
        from src.esg_demo.indicators import DEMO_INDICATORS

        indicator = next(i for i in DEMO_INDICATORS if i.indicator_id == "e_ghg_total")
        result = normalize_llm_result(
            "demo",
            indicator,
            json.dumps(
                {
                    "status": "已找到",
                    "value": "394.77",
                    "unit": "吨二氧化碳当量",
                    "evidence_quote": "温室气体排放总量 394.77 吨二氧化碳当量",
                },
                ensure_ascii=False,
            ),
        )

        self.assertEqual(result["status"], "found")
        self.assertIn("normalized invalid status", result["notes"])

    def test_prompt_disables_qwen3_thinking(self):
        from src.esg_demo.extract import build_prompt
        from src.esg_demo.indicators import DEMO_INDICATORS

        indicator = next(i for i in DEMO_INDICATORS if i.indicator_id == "e_ghg_total")
        prompt = build_prompt(
            "demo",
            indicator,
            [{"block_id": "b", "page_no": 1, "block_type": "table", "text": "温室气体排放总量 20 吨"}],
        )

        self.assertTrue(prompt.startswith("/no_think\n"))
        self.assertIn("qualitative_text 控制在 120 个汉字以内", prompt)
        self.assertIn("evidence_quote 控制在 160 个汉字以内", prompt)

    def test_ollama_generate_limits_output_tokens(self):
        from src.esg_demo.ollama import OllamaClient

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, traceback):
                return False

            def read(self):
                return json.dumps({"response": "{\"status\":\"missing\"}"}).encode("utf-8")

        class FakeOpener:
            def __init__(self):
                self.payload = None

            def open(self, req, timeout):
                self.payload = json.loads(req.data.decode("utf-8"))
                return FakeResponse()

        client = OllamaClient(model="qwen3:30b", url="http://example.invalid/api/generate")
        fake_opener = FakeOpener()
        client.opener = fake_opener

        client.generate("prompt")

        self.assertEqual(fake_opener.payload["format"], "json")
        self.assertEqual(fake_opener.payload["options"]["num_predict"], 1024)

    def test_openai_compatible_generate_disables_thinking_and_requests_json(self):
        from src.esg_demo.ollama import OpenAICompatibleClient

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, traceback):
                return False

            def read(self):
                return json.dumps(
                    {"choices": [{"message": {"content": "{\"status\":\"missing\"}"}}]}
                ).encode("utf-8")

        class FakeOpener:
            def __init__(self):
                self.payload = None

            def open(self, req, timeout):
                self.payload = json.loads(req.data.decode("utf-8"))
                return FakeResponse()

        client = OpenAICompatibleClient(
            model="qwen3.6-27b-q4_k_m",
            url="http://example.invalid/v1/chat/completions",
        )
        fake_opener = FakeOpener()
        client.opener = fake_opener

        result = client.generate("prompt")

        self.assertEqual(result, '{"status":"missing"}')
        self.assertEqual(fake_opener.payload["response_format"], {"type": "json_object"})
        self.assertFalse(fake_opener.payload["chat_template_kwargs"]["enable_thinking"])
        self.assertEqual(fake_opener.payload["max_tokens"], 1024)

    def test_no_llm_demo_writes_machine_outputs(self):
        from src.esg_demo.runner import run_demo

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report_dir = root / "outputs/final_results/parsed/605377_华旺科技_2025_ESG报告"
            report_dir.mkdir(parents=True)
            json_path = report_dir / "605377_华旺科技_2025_ESG报告_content_list_v2.json"
            json_path.write_text(
                json.dumps(
                    [
                        [
                            {
                                "type": "list",
                                "bbox": [0, 0, 10, 10],
                                "content": {
                                    "list_items": [
                                        {"item_content": [{"content": "温室气体排放总量"}]},
                                        {"item_content": [{"content": "279,713.69 吨二氧化碳当量"}]},
                                    ]
                                },
                            }
                        ]
                    ],
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            out_dir = root / "outputs/demo"

            summary = run_demo(
                project_root=root,
                report_filters=["605377"],
                out_dir=out_dir,
                model="qwen3:30b",
                ollama_url="http://127.0.0.1:11434/api/generate",
                max_blocks_per_indicator=3,
                use_llm=False,
            )

            self.assertEqual(summary["reports"], 1)
            self.assertTrue((out_dir / "block_table_sample.csv").is_file())
            self.assertTrue((out_dir / "extraction_results.json").is_file())
            self.assertTrue((out_dir / "extraction_results.csv").is_file())
            self.assertTrue((out_dir / "run_summary.json").is_file())
            results = json.loads((out_dir / "extraction_results.json").read_text(encoding="utf-8"))
            ghg = [r for r in results if r["indicator_id"] == "e_ghg_total"][0]
            self.assertEqual(ghg["status"], "candidate")
            self.assertIn("温室气体排放总量", ghg["evidence_quote"])

    def test_formal_no_llm_writes_pool_coverage_and_outputs(self):
        from src.esg_demo.runner import run_formal

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_report(
                root,
                "000001_测试公司_2025_ESG报告",
                "温室气体排放总量为 20 吨二氧化碳当量，员工总数为 100 人。",
            )
            out_dir = root / "outputs/final_results/new_reports"

            summary = run_formal(
                project_root=root,
                report_filters=[],
                report_limit=100,
                out_dir=out_dir,
                model="qwen3:30b",
                ollama_url="http://127.0.0.1:11434/api/generate",
                max_blocks_per_indicator=3,
                use_llm=False,
            )

            self.assertEqual(summary["indicator_set"], "formal_current")
            self.assertEqual(summary["reports"], 1)
            self.assertGreaterEqual(summary["indicators"], 80)
            self.assertTrue((out_dir / "indicator_pool.json").is_file())
            self.assertTrue((out_dir / "indicator_pool.csv").is_file())
            self.assertTrue((out_dir / "candidate_coverage.csv").is_file())
            self.assertTrue((out_dir / "quality_review_sample.csv").is_file())
            self.assertTrue((out_dir / "extraction_results.json").is_file())
            coverage = (out_dir / "candidate_coverage.csv").read_text(encoding="utf-8-sig")
            self.assertIn("e_ghg_total", coverage)
            self.assertIn("candidate", coverage)
            review = (out_dir / "quality_review_sample.csv").read_text(encoding="utf-8-sig")
            self.assertIn("manual_label", review)
            self.assertIn("e_ghg_total", review)
            results = json.loads((out_dir / "extraction_results.json").read_text(encoding="utf-8"))
            ghg = [row for row in results if row["indicator_id"] == "e_ghg_total"][0]
            self.assertEqual(ghg["status"], "candidate")
            self.assertIn("温室气体排放总量", ghg["evidence_quote"])

    def test_formal_runner_honors_report_limit(self):
        from src.esg_demo.runner import run_formal

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_report(root, "000001_一号公司_2025_ESG报告", "温室气体排放总量 1 吨")
            self._write_report(root, "000002_二号公司_2025_ESG报告", "温室气体排放总量 2 吨")

            summary = run_formal(
                project_root=root,
                report_filters=[],
                report_limit=1,
                out_dir=root / "outputs/final_results/new_reports",
                model="qwen3:30b",
                ollama_url="http://127.0.0.1:11434/api/generate",
                max_blocks_per_indicator=3,
                use_llm=False,
            )

            self.assertEqual(summary["reports"], 1)
            self.assertEqual(len(summary["report_ids"]), 1)

    def test_csv_writer_handles_multiline_quotes_and_backslashes(self):
        from src.esg_demo.runner import _write_csv

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "rows.csv"

            _write_csv(path, [{"text": '第一行\x00\n第二行 "quoted" \\ path', "value": "1"}])

            content = path.read_text(encoding="utf-8-sig")
            self.assertNotIn("\x00", content)
            self.assertIn('""quoted""', content)
            self.assertIn("\\ path", content)

if __name__ == "__main__":
    unittest.main()
