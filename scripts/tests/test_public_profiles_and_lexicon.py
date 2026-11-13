from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))
import check_pre_ai_style as checker
import lexicon


class PublicProfileTests(unittest.TestCase):
    def test_public_default_keeps_editorial_preferences_advisory(self):
        for text in ("三家公司遇到同一堵墙。", "未来已来。", "工作没有整齐消失。"):
            with self.subTest(text=text):
                general = checker.check_text(text)
                zeelin = checker.check_text(text, profile="zeelin")
                self.assertTrue(general)
                self.assertFalse(any(f["severity"] == "high" for f in general))
                self.assertTrue(any(f["severity"] == "high" for f in zeelin))
                self.assertTrue(all(f["profile"] == "general" for f in general))

    def test_clear_grammar_and_concept_errors_remain_high_in_both_profiles(self):
        for text in ("投诉量减少两倍。", "上下文窗口就是模型的训练数据。", "这款产品对用户很感兴趣。"):
            for profile in checker.PROFILES:
                with self.subTest(text=text, profile=profile):
                    self.assertTrue(any(f["severity"] == "high" for f in checker.check_text(text, profile=profile)))

    def test_quotes_do_not_become_hard_errors_in_either_profile(self):
        for profile in checker.PROFILES:
            findings = checker.check_text("公司发布《未来已来》报告。", profile=profile)
            self.assertTrue(findings)
            self.assertFalse(any(f["severity"] == "high" for f in findings))

    def test_unknown_profile_is_not_silently_accepted(self):
        with self.assertRaises(ValueError):
            checker.check_text("测试", profile="unknown")

    def test_cli_profile_changes_exit_code_without_rewriting_input(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "article.txt"
            original = "三家公司遇到同一堵墙。"
            path.write_text(original, encoding="utf-8")
            with contextlib.redirect_stdout(io.StringIO()):
                general = checker.main([str(path), "--fail-on", "high"])
                zeelin = checker.main([str(path), "--profile", "zeelin", "--fail-on", "high"])
            self.assertEqual(0, general)
            self.assertEqual(1, zeelin)
            self.assertEqual(original, path.read_text(encoding="utf-8"))


class PublicLexiconTests(unittest.TestCase):
    def test_lf_crlf_and_bom_checkouts_have_same_text_checksums(self):
        with tempfile.TemporaryDirectory() as folder:
            bank = Path(folder)
            for name in ('core-rules.jsonl', 'expansion-seeds.json', 'sources.json', 'manifest.json'):
                raw = lexicon.canonical_file_bytes(lexicon.BANK / name)
                (bank / name).write_bytes(b'\xef\xbb\xbf' + raw.replace(b'\n', b'\r\n'))
            for name in ('core-rules.jsonl', 'expansion-seeds.json', 'sources.json'):
                self.assertEqual(lexicon.file_metadata(lexicon.BANK / name), lexicon.file_metadata(bank / name))
            with mock.patch.object(lexicon, 'BANK', bank), mock.patch.object(lexicon, 'MANIFEST', bank / 'manifest.json'):
                self.assertEqual('valid', lexicon.validate()['result'])
                records = list(lexicon.rows('core'))
                records[0]['reason'] += ' 新增正文修改。'
                (bank / 'core-rules.jsonl').write_text('\n'.join(json.dumps(r, ensure_ascii=False) for r in records) + '\n', encoding='utf-8')
                with self.assertRaisesRegex(ValueError, 'Checksum changed: core-rules.jsonl'):
                    lexicon.validate()

    def test_binary_checksum_does_not_normalize_newlines_or_bom(self):
        with tempfile.TemporaryDirectory() as folder:
            first, second = Path(folder) / 'a.gz', Path(folder) / 'b.gz'
            first.write_bytes(b'\xef\xbb\xbfabc\r\ndef')
            second.write_bytes(b'abc\ndef')
            self.assertNotEqual(lexicon.digest(first), lexicon.digest(second))
            self.assertEqual('raw-bytes', lexicon.file_metadata(first)['hash_mode'])
            self.assertEqual(first.stat().st_size, lexicon.file_metadata(first)['bytes'])

    def test_reviewed_examples_and_sources_validate(self):
        rows = lexicon.validate_core()
        self.assertTrue(rows)
        self.assertEqual(len(rows), len({r["id"] for r in rows}))

    def test_clean_clone_validates_without_generated_candidates(self):
        with tempfile.TemporaryDirectory() as folder:
            bank = Path(folder)
            for name in ("core-rules.jsonl", "expansion-seeds.json", "sources.json", "manifest.json"):
                shutil.copyfile(lexicon.BANK / name, bank / name)
            with mock.patch.object(lexicon, "BANK", bank), mock.patch.object(lexicon, "MANIFEST", bank / "manifest.json"):
                result = lexicon.validate()
                self.assertFalse(result["candidates_checked"])
                with self.assertRaisesRegex(ValueError, "Missing"):
                    lexicon.validate(with_candidates=True)

    def test_generated_candidate_is_pending_and_never_active(self):
        seeds = lexicon.json_read(lexicon.BANK / "expansion-seeds.json")
        row = next(lexicon.candidate_rows(seeds))
        self.assertEqual("pending", row["review_status"])
        self.assertFalse(row["auto_block"])
        self.assertEqual("synthetic_expansion", row["evidence_type"])
        self.assertFalse(any(f["rule_id"].startswith("ZV-") for f in checker.check_text(row["expression"])))

    def test_queries_respect_limits_and_report_missing_optional_file(self):
        self.assertEqual(2, len(list(lexicon.query("core", "", None, 2))))
        with self.assertRaises(ValueError):
            list(lexicon.query("core", "", None, 0))
        with tempfile.TemporaryDirectory() as folder:
            with mock.patch.object(lexicon, "CANDIDATES", Path(folder) / "missing.jsonl.gz"):
                with self.assertRaisesRegex(ValueError, "build"):
                    list(lexicon.query("candidate", "", None, 2))

    def test_seed_expansion_count_is_derived_not_fixed(self):
        seeds = lexicon.json_read(lexicon.BANK / "expansion-seeds.json")
        small = dict(seeds, subjects=seeds["subjects"][:2], aspects=seeds["aspects"][:3])
        expected = len(seeds["templates"]) * 2 * 3
        self.assertEqual(expected, lexicon.validate_seeds(small))
        self.assertEqual(expected, sum(1 for _ in lexicon.candidate_rows(small)))


if __name__ == "__main__":
    unittest.main()

