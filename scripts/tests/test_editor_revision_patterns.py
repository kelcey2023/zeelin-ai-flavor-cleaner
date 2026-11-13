import runpy
import unittest
from pathlib import Path


SKILL = Path(__file__).resolve().parents[2]
RAW_CHECK = runpy.run_path(str(SKILL / "scripts/check_pre_ai_style.py"))["check_text"]

def CHECK(text):
    return RAW_CHECK(text, profile="zeelin")


class EditorRevisionPatternTests(unittest.TestCase):
    def test_decorative_modifier_is_blocked(self):
        findings = CHECK("工作没有整齐消失，定价方式在变。")
        self.assertTrue(
            any(
                item["code"] == "decorative-modifier"
                and item["severity"] == "high"
                for item in findings
            )
        )

    def test_empty_case_summary_is_blocked(self):
        findings = CHECK("新平台可以分流，也可以带来新需求；变化不会只朝一个方向走。")
        self.assertTrue(
            any(
                item["code"] == "empty-case-summary"
                and item["severity"] == "high"
                for item in findings
            )
        )

    def test_concrete_nearby_sentences_pass_new_rules(self):
        valid = (
            "工作没有消失，定价方式在变。\n\n"
            "新平台可以分流，也可以带来新需求。"
        )
        blocked = {"decorative-modifier", "empty-case-summary"}
        self.assertFalse(any(item["code"] in blocked for item in CHECK(valid)))


if __name__ == "__main__":
    unittest.main()
