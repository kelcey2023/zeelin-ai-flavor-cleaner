import runpy
import unittest
from pathlib import Path


SKILL = Path(__file__).resolve().parents[2]
RAW_CHECK = runpy.run_path(str(SKILL / "scripts/check_pre_ai_style.py"))["check_text"]

def CHECK(text):
    return RAW_CHECK(text, profile="zeelin")


class EvidenceProcessCommentaryTests(unittest.TestCase):

    def test_phrases_are_high_priority(self):
        for text in (
            "数字是真的，因果没那么简单。",
            "现在还没有一个可靠比例。",
            "一个经常被引用的数字也需要放回原文。",
        ):
            with self.subTest(text=text):
                findings = CHECK(text)
                self.assertTrue(
                    any(
                        item["code"] == "evidence-process-commentary"
                        and item["severity"] == "high"
                        for item in findings
                    )
                )

    def test_specific_evidence_boundaries_are_not_flagged(self):
        valid = (
            "研究观察到AI工具使用频率与修改次数相关，"
            "但没有检验前者是否导致后者。\n\n"
            "现有公开材料没有统计生成式AI直接导致的岗位减少比例。"
        )
        self.assertFalse(
            any(
                item["code"] == "evidence-process-commentary"
                for item in CHECK(valid)
            )
        )


if __name__ == "__main__":
    unittest.main()
