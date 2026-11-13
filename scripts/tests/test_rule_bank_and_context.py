from __future__ import annotations

import importlib.util
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("bank_checker", SCRIPTS / "check_pre_ai_style.py")
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)


def rule(rule_id="test-reviewed", expression="这是空泛占位表达", **overrides):
    result = {
        "id": rule_id, "expression": expression, "match_type": "literal",
        "severity": "high", "category": "test-expression", "reason": "说明问题。",
        "rewrite_guidance": "先核对事实再改写。", "exceptions": [],
        "source_ids": ["test-source"], "evidence_type": "editorial_example",
        "review_status": "reviewed",
    }
    result.update(overrides)
    return result


class RuleBankTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "core-rules.jsonl"
        self.write_rules(rule())

    def write_rules(self, *rules):
        self.path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rules), encoding="utf-8")

    def check(self, text):
        return checker.check_text(text, bank_path=self.path, profile="zeelin")

    def test_reviewed_rule_reports_provenance_without_modifying_text(self):
        text = "公司今天发布产品。这是空泛占位表达。"
        findings = self.check(text)
        item = next(item for item in findings if item["rule_id"] == "test-reviewed")
        self.assertEqual(["test-source"], item["source_ids"])
        self.assertEqual("reviewed", item["review_status"])
        self.assertEqual(item["excerpt"], text[item["offset"]:item["offset"] + len(item["excerpt"])])
        self.assertEqual("公司今天发布产品。这是空泛占位表达。", text)

    def test_candidates_do_not_become_active_bans(self):
        self.write_rules(rule(), rule("candidate-1", "普通词语", review_status="candidate"))
        self.assertFalse(any(item["rule_id"] == "candidate-1" for item in self.check("普通词语。")))

    def test_literal_rules_do_not_interpret_regex_symbols(self):
        self.write_rules(rule(expression="v1.0+功能"))
        self.assertFalse(self.check("v1x000功能"))
        self.assertTrue(self.check("v1.0+功能"))

    def test_regex_distinguishes_missing_from_present_object(self):
        self.write_rules(rule(expression=r"智能体为什么会多次消耗(?=[？?。！!\n]|$)", match_type="regex", severity="medium"))
        self.assertTrue(self.check("智能体为什么会多次消耗？"))
        self.assertFalse(self.check("智能体为什么会多次消耗输入token？"))

    def test_missing_bank_fails_explicitly(self):
        with self.assertRaisesRegex(checker.RuleBankError, "无法读取核心规则库"):
            checker.check_text("公司发布产品。", bank_path=Path(self.temp.name) / "missing.jsonl")

    def test_corrupt_or_unreviewed_only_bank_does_not_silently_pass(self):
        for content in ("{", json.dumps(rule(review_status="candidate")), json.dumps(rule(expression=".*", match_type="regex"))):
            with self.subTest(content=content):
                self.path.write_text(content, encoding="utf-8")
                with self.assertRaises(checker.RuleBankError):
                    self.check("公司发布产品。")

    def test_code_and_urls_are_excluded_but_offsets_stay_original(self):
        text = "```text\n同一堵墙\n```\n`同一堵墙` https://example.com/同一堵墙\n\n正文遇到同一堵墙。"
        walls = [item for item in self.check(text) if item["code"] == "banned-same-wall"]
        self.assertEqual(1, len(walls))
        self.assertEqual(text.rindex("同一堵墙"), walls[0]["offset"])
        self.assertEqual("high", walls[0]["severity"])

    def test_tilde_and_unclosed_fences_are_also_code(self):
        self.assertFalse(any(i["code"] == "banned-same-wall" for i in self.check("~~~\n同一堵墙\n~~~")))
        self.assertFalse(any(i["code"] == "banned-same-wall" for i in self.check("```text\n同一堵墙")))

    def test_quotes_remain_visible_for_source_review(self):
        for text in ("他称：“同一堵墙”。", '> 同一堵墙', '他称："同一堵墙"。', '他称：「同一堵墙」。'):
            with self.subTest(text=text):
                walls = [i for i in self.check(text) if i["code"] == "banned-same-wall"]
                self.assertEqual(1, len(walls))
                self.assertEqual("medium", walls[0]["severity"])
                self.assertEqual("quotation_or_term", walls[0]["context"])

    def test_same_phrase_outside_quote_is_still_high(self):
        text = '他称：“同一堵墙”。作者又写同一堵墙。'
        walls = [i for i in self.check(text) if i["code"] == "banned-same-wall"]
        self.assertEqual(["medium", "high"], [i["severity"] for i in walls])

    def test_report_titles_remain_visible_for_source_review(self):
        for text in ("公司发布《未来已来》报告。", "公司发布〈未来已来〉报告。"):
            with self.subTest(text=text):
                items = [i for i in self.check(text) if i["code"] == "template-cliche"]
                self.assertEqual(1, len(items))
                self.assertEqual("medium", items[0]["severity"])
                self.assertEqual("quotation_or_term", items[0]["context"])
                self.assertEqual("未来已来", items[0]["excerpt"])

    def test_valid_semantic_neighbours_are_not_hard_errors(self):
        texts = (
            "全班同学几乎全部到场。",
            "不能否认，这次调整没有增加成本。",
            "是否符合要求，是产品验收通过的标准。",
            "模型的第一层是嵌入层。",
            "模型能开口说话，输出合成语音。",
            "这项技术能够识别人类说话的声音。",
            "该系统能识别人类说话的声音。",
            "算法可以处理人类说话的声音。",
            "只有一次失败，就让整个团队停止了测试。",
            "只有3名观众，就占满了第一排座位。",
            "报告研究新质生产力的政策含义。",
            "平台解释了数据库事务的底层逻辑。",
        )
        for text in texts:
            with self.subTest(text=text):
                self.assertFalse([i for i in self.check(text) if i["severity"] == "high"])

    def test_real_errors_and_user_preference_still_block(self):
        for text in ("原因是系统超时造成的。", "投诉量减少两倍。", "三家公司遇到同一堵墙。", "只有升级，就能使用。", "数据开始开口说话。"):
            with self.subTest(text=text):
                self.assertTrue([i for i in self.check(text) if i["severity"] == "high"])

    def test_structural_findings_use_original_offsets_after_leading_space(self):
        text = "\n\n  " + "\n\n".join(("这个想法仍在讨论中，团队还要核对具体安排和实施条件。" * 3) for _ in range(4))
        findings = self.check(text)
        self.assertTrue(findings)
        for item in findings:
            self.assertEqual(item["excerpt"], text[item["offset"]:item["offset"] + len(item["excerpt"])])


class InstalledBankTests(unittest.TestCase):
    def test_user_examples_have_different_severity_and_keep_offsets(self):
        text = "11月12日发布。上下文窗口像一次能摊开的材料。\n智能体为什么会多次消耗？"
        findings = checker.check_text(text)
        metaphor = next(i for i in findings if i["rule_id"] == "ZC-0049")
        omission = next(i for i in findings if i["rule_id"] == "ZC-0050")
        self.assertEqual("high", metaphor["severity"])
        self.assertEqual("medium", omission["severity"])
        for item in (metaphor, omission):
            self.assertEqual(item["excerpt"], text[item["offset"]:item["offset"] + len(item["excerpt"])])

    def test_complete_technical_questions_are_not_flagged_for_missing_object(self):
        for text in ("智能体为什么会多次消耗输入token？", "智能体为什么要反复消耗调用额度？"):
            with self.subTest(text=text):
                self.assertFalse(any(i["rule_id"] == "ZC-0050" for i in checker.check_text(text)))

    def test_cli_exit_and_json_are_usable_by_article_workflow(self):
        with tempfile.TemporaryDirectory() as folder:
            article = Path(folder) / "article.txt"
            article.write_text("上下文窗口像一次能摊开的材料。", encoding="utf-8")
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                result = checker.main([str(article), "--json", "--fail-on", "high"])
            self.assertEqual(1, result)
            self.assertTrue(any(i["rule_id"] == "ZC-0049" for i in json.loads(output.getvalue())))
            self.assertEqual("上下文窗口像一次能摊开的材料。", article.read_text(encoding="utf-8"))
            article.write_text("智能体为什么会多次消耗输入token？", encoding="utf-8")
            with contextlib.redirect_stdout(io.StringIO()):
                result = checker.main([str(article), "--fail-on", "high"])
            self.assertEqual(0, result)


if __name__ == "__main__":
    unittest.main()
