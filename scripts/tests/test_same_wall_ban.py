import runpy
import unittest
from pathlib import Path

SKILL = Path(__file__).resolve().parents[2]
RAW_CHECK = runpy.run_path(str(SKILL / "scripts/check_pre_ai_style.py"))["check_text"]

def CHECK(text):
    return RAW_CHECK(text, profile="zeelin")


class SameWallBanTests(unittest.TestCase):

    def test_phrase_is_high_priority_in_title_and_body(self):
        for text in ("三家AI公司遇到了同一堵墙", "企业采购预算有限。几家公司的业务都遇到了同一堵墙。"):
            with self.subTest(text=text):
                self.assertTrue(any(f["severity"] == "high" and f["excerpt"] == "同一堵墙" for f in CHECK(text)))

    def test_specific_statement_is_not_flagged_as_wall_metaphor(self):
        self.assertFalse(any(f["code"] == "banned-same-wall" for f in CHECK("三家公司的客户都减少了采购预算。")))


if __name__ == "__main__":
    unittest.main()
