#!/usr/bin/env python3
"""Validate public rule data, examples, and portable package boundaries."""
from __future__ import annotations

import json
import re
from pathlib import Path

import check_pre_ai_style as checker
import lexicon

ROOT = Path(__file__).resolve().parents[1]


def validate():
    result = lexicon.validate()
    rules = lexicon.validate_core()
    for row in rules:
        findings = checker.check_text(row["example_bad"])
        if not any(item["rule_id"] == row["id"] for item in findings):
            raise ValueError(f"Checker does not detect problem example: {row['id']}")
        if any(item["severity"] == "high" for item in checker.check_text(row["example_good"])):
            raise ValueError(f"Normal example is hard-blocked: {row['id']}")

    for text in (
        "模型第一层的参数已经冻结。",
        "全班同学几乎全部到场。",
        "不能否认公司没有按时交付。",
        "这项技术能够识别人类说话的声音。",
        "智能体为什么会多次消耗输入token？",
        "公司发布《未来已来》报告。",
    ):
        if any(item["severity"] == "high" for item in checker.check_text(text)):
            raise ValueError(f"Normal boundary example is hard-blocked: {text}")

    for required in ("SKILL.md", "README.md", "profiles/zeelin-wechat.md",
                     "references/chinese-language-errors.md", "references/lexicon-guide.md"):
        if not (ROOT / required).is_file():
            raise ValueError(f"Missing public document: {required}")

    checked = 0
    for path in ROOT.rglob("*"):
        if not path.is_file() or ".git" in path.parts or "__pycache__" in path.parts:
            continue
        relative = path.relative_to(ROOT)
        if "backup" in path.name.lower() or path.name.startswith("SKILL.before"):
            raise ValueError(f"Backup must not be published: {relative}")
        if path.suffix.lower() not in {".md", ".py", ".json", ".jsonl", ".yml", ".yaml"}:
            continue
        text = path.read_text(encoding="utf-8-sig")
        if re.search(r"[A-Za-z]:[\\/]Users[\\/]|[/]Users[/][^/]+[/]|[/]home[/][^/]+[/]", text):
            raise ValueError(f"Machine-specific absolute path: {relative}")
        if re.search(r"(?i)(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|sk-proj-[A-Za-z0-9_-]{20,})", text):
            raise ValueError(f"Credential-shaped string: {relative}")
        checked += 1

    result.update({
        "core_problem_examples_detected": len(rules),
        "normal_core_examples_without_high": len(rules),
        "boundary_examples_checked": 6,
        "public_text_files_checked": checked,
        "default_profile": "general",
        "optional_profile": "zeelin",
    })
    return result


if __name__ == "__main__":
    print(json.dumps(validate(), ensure_ascii=False, indent=2))

