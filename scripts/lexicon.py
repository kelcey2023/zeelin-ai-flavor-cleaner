#!/usr/bin/env python3
"""Build/query the explicitly synthetic candidate corpus; never rewrite articles."""
from __future__ import annotations
import argparse
import csv
import gzip
import hashlib
import json
import re
import sys
import string
from collections import Counter
from pathlib import Path

BANK = Path(__file__).resolve().parents[1] / "references" / "lexicon"
CANDIDATES = BANK / "candidates-100000.jsonl.gz"
MANIFEST = BANK / "manifest.json"

def json_read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))

def rows(kind):
    if kind not in {'core', 'candidate'}:
        raise ValueError('kind must be core or candidate')
    path = BANK / "core-rules.jsonl" if kind == "core" else CANDIDATES
    if not path.is_file():
        raise ValueError(f"Missing {path.name}; run lexicon.py build for optional candidates")
    opener = open if kind == "core" else gzip.open
    with opener(path, "rt", encoding="utf-8-sig") as stream:
        for line in stream:
            if line.strip():
                yield json.loads(line)

def digest(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def source_ids():
    registry = json_read(BANK / 'sources.json')
    records = registry['sources'] + registry.get('local_sources', [])
    ids = [r['source_id'] for r in records]
    if len(ids) != len(set(ids)):
        raise ValueError('Duplicate source IDs')
    return set(ids)


def validate_sources(ids, known, label):
    if not isinstance(ids, list) or not ids or not all(isinstance(x, str) for x in ids):
        raise ValueError(f'Invalid source IDs: {label}')
    if not set(ids) <= known:
        raise ValueError(f'Unknown source ID: {label}')


def validate_seeds(seeds):
    known = source_ids()
    for key in ('subjects', 'aspects'):
        values = seeds[key]
        if not values or not all(isinstance(v, str) and v for v in values):
            raise ValueError(f'Empty/invalid {key}')
        if len(values) != len(set(values)):
            raise ValueError(f'Duplicate {key}')
    ids, templates = set(), set()
    for t in seeds['templates']:
        if t['id'] in ids or t['template'] in templates:
            raise ValueError('Duplicate template ID or text')
        ids.add(t['id']); templates.add(t['template'])
        if not re.fullmatch(r'ZT-[0-9]+', t['id']):
            raise ValueError('Template ID must be ZT- followed by digits')
        fields = [(field, spec, conv) for _, field, spec, conv in string.Formatter().parse(t['template']) if field is not None]
        if fields != [('topic', '', None)]:
            raise ValueError(f'Template must have one plain topic slot: {t["id"]}')
        for key in ('category', 'rewrite_guidance', 'exceptions'):
            if not isinstance(t.get(key), str) or not t[key]:
                raise ValueError(f'Missing template {key}')
        if t.get('review_status') != 'template_reviewed_variants_pending':
            raise ValueError('Template variants must remain pending')
        validate_sources(t['source_ids'], known, t['id'])
    if not ids:
        raise ValueError('No expansion templates')
    return len(ids) * len(seeds['subjects']) * len(seeds['aspects'])


def validate_core():
    known = source_ids()
    required = {'id', 'expression', 'match_type', 'severity', 'category', 'reason', 'rewrite_guidance', 'exceptions', 'source_ids', 'evidence_type', 'review_status', 'example_bad', 'example_good'}
    seen_ids, seen_patterns = set(), set()
    records = list(rows('core'))
    for row in records:
        if not isinstance(row, dict) or required.difference(row):
            raise ValueError('Missing core fields or non-object record')
        if row['id'] in seen_ids or not re.fullmatch(r'ZC-[0-9]+', row['id']):
            raise ValueError(f'Duplicate or invalid core ID: {row["id"]}')
        seen_ids.add(row['id'])
        if row['review_status'] != 'reviewed':
            raise ValueError('Only reviewed records belong in the core bank')
        if row['match_type'] not in {'literal', 'regex'} or row['severity'] not in {'high', 'medium', 'low'}:
            raise ValueError(f'Invalid core mode/severity: {row["id"]}')
        for key in ('expression', 'category', 'reason', 'rewrite_guidance', 'evidence_type', 'example_bad', 'example_good'):
            if not isinstance(row[key], str) or not row[key]:
                raise ValueError(f'Missing/invalid {key}: {row["id"]}')
        if not isinstance(row['exceptions'], list) or not row['exceptions'] or not all(isinstance(x, str) and x for x in row['exceptions']):
            raise ValueError(f'Missing exceptions: {row["id"]}')
        pair = (row['match_type'], row['expression'])
        if pair in seen_patterns:
            raise ValueError(f'Duplicate expression: {row["id"]}')
        seen_patterns.add(pair)
        validate_sources(row['source_ids'], known, row['id'])
        pattern = re.compile(re.escape(row['expression']) if row['match_type'] == 'literal' else row['expression'])
        if pattern.match(''):
            raise ValueError(f'Empty-matching pattern: {row["id"]}')
        if not pattern.search(row['example_bad']):
            raise ValueError(f'Problem example is not detected: {row["id"]}')
        if pattern.search(row['example_good']):
            raise ValueError(f'Normal example matches its rule: {row["id"]}')
    if not records:
        raise ValueError('No reviewed core rules')
    return records


def candidate_rows(seeds):
    for template in seeds["templates"]:
        for si, subject in enumerate(seeds["subjects"], 1):
            for ai, aspect in enumerate(seeds["aspects"], 1):
                yield {
                    "id": f"ZV-{template['id'][3:]}-{si:02}-{ai:02}",
                    "expression": template["template"].format(topic=f"{subject}的{aspect}"),
                    "family_id": template["id"],
                    "category": template["category"],
                    "subject": subject,
                    "aspect": aspect,
                    "severity": "candidate",
                    "review_status": "pending",
                    "evidence_type": "synthetic_expansion",
                    "source_ids": template["source_ids"],
                    "auto_block": False,
                    "rewrite_guidance": template["rewrite_guidance"],
                }

def build(csv_path=None):
    core = validate_core()
    seeds = json_read(BANK / "expansion-seeds.json")
    expected = validate_seeds(seeds)
    seen, counts, records = set(), Counter(), 0
    csv_stream = None
    try:
        if csv_path:
            csv_path.parent.mkdir(parents=True, exist_ok=True)
            csv_stream = csv_path.open("w", encoding="utf-8-sig", newline="")
            writer = csv.writer(csv_stream)
            writer.writerow(["编号", "候选表达", "母句式", "类别", "对象", "方面", "审核状态", "来源性质", "自动拦截", "修改方向"])
        # Fixed mtime keeps regenerated archive bytes reproducible.
        with CANDIDATES.open("wb") as raw:
            with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as archive:
                for record in candidate_rows(seeds):
                    if record["expression"] in seen:
                        raise ValueError("Duplicate expression: " + record["id"])
                    seen.add(record["expression"])
                    counts[record["category"]] += 1
                    records += 1
                    archive.write((json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8"))
                    if csv_stream:
                        writer.writerow([record["id"], record["expression"], record["family_id"], record["category"], record["subject"], record["aspect"], "待审", "本地句式组合生成，非网络摘录", "否", record["rewrite_guidance"]])
    finally:
        if csv_stream:
            csv_stream.close()
    if records != expected:
        raise ValueError('Incomplete candidate generation')
    manifest = {
        "schema_version": 2, "date": seeds['date'],
        "reviewed_core_rules": len(core),
        "candidate_expressions": records,
        "unique_candidate_expressions": len(seen),
        "candidate_templates": len(seeds["templates"]),
        "subject_slots": len(seeds["subjects"]),
        "aspect_slots": len(seeds["aspects"]),
        "formula": f"{len(seeds['templates'])} authored templates × {len(seeds['subjects'])} tool/system names × {len(seeds['aspects'])} attributes",
        "candidate_categories": dict(counts),
        "candidate_review_status": "pending",
        "candidate_default_scanning": False,
        "candidate_artifact_optional": True,
        "network_harvested_candidate_count": 0,
        "individual_candidate_semantic_review_count": 0,
        "notes": [
            "The candidate count denotes unique generated expressions, not independently verified bans.",
            "Built-in editorial rules and core bank entries are counted separately.",
            "Source research supports methods and boundaries, not statistical proof of these synthetic expressions.",
            "Same-family variants are not independent evidence; no AI probability is estimated."
        ],
        "files": {p.name: {"sha256": digest(p), "bytes": p.stat().st_size} for p in [CANDIDATES, BANK / "core-rules.jsonl", BANK / "expansion-seeds.json", BANK / "sources.json"]}
    }
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest

def validate(with_candidates=False):
    core = validate_core()
    seeds = json_read(BANK / "expansion-seeds.json")
    expected = validate_seeds(seeds)
    m = json_read(MANIFEST)
    if m['reviewed_core_rules'] != len(core) or m['candidate_expressions'] != expected:
        raise ValueError('Manifest counts changed; run lexicon.py build')
    for name, metadata in m["files"].items():
        if name == CANDIDATES.name and not with_candidates:
            continue
        if not (BANK / name).is_file():
            raise ValueError(f'Missing {name}; run lexicon.py build')
        if digest(BANK / name) != metadata["sha256"]:
            raise ValueError(f"Checksum changed: {name}; review and rebuild the manifest")
    if not with_candidates:
        return {'result': 'valid', 'core_rules': len(core), 'candidate_expressions_expected': expected, 'candidates_checked': False}
    seeds = json_read(BANK / "expansion-seeds.json")
    known_families = {t["id"] for t in seeds["templates"]}
    seen_ids, seen_text, counts = set(), set(), Counter()
    for row in rows("candidate"):
        if row["id"] in seen_ids or row["expression"] in seen_text:
            raise ValueError("Duplicate candidate")
        if row["review_status"] != "pending" or row["auto_block"] is not False or row["evidence_type"] != "synthetic_expansion":
            raise ValueError("Candidate was incorrectly promoted")
        if row["family_id"] not in known_families:
            raise ValueError("Unknown template")
        seen_ids.add(row["id"]); seen_text.add(row["expression"])
        counts[row["category"]] += 1
    if len(seen_ids) != expected or dict(counts) != m["candidate_categories"]:
        raise ValueError("Candidate count/category mismatch")
    core_ids = set()
    for row in rows("core"):
        if row["id"] in core_ids or row["review_status"] != "reviewed":
            raise ValueError("Invalid core status/id")
        core_ids.add(row["id"])
        for key in ["reason", "rewrite_guidance", "exceptions", "source_ids", "example_bad", "example_good"]:
            if not row.get(key):
                raise ValueError(f"Missing {key}: {row['id']}")
        if row["match_type"] == "regex":
            re.compile(row["expression"])
    return {"result": "valid", "core_rules": len(core_ids), "candidate_expressions": len(seen_ids), "categories": len(counts), 'candidates_checked': True}

def query(kind, query_text, category, limit):
    if limit < 1:
        raise ValueError('limit must be positive')
    for row in rows(kind):
        if category and row["category"] != category:
            continue
        if query_text and query_text not in row["expression"] and query_text != row["id"]:
            continue
        yield row
        limit -= 1
        if limit == 0:
            break

def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)
    b = sub.add_parser("build"); b.add_argument("--csv-path", type=Path)
    sub.add_parser("stats")
    v = sub.add_parser("validate")
    v.add_argument('--with-candidates', action='store_true')
    q = sub.add_parser("query")
    q.add_argument("text", nargs="?", default="")
    q.add_argument("--kind", choices=["core", "candidate"], default="core")
    q.add_argument("--category"); q.add_argument("--limit", type=int, default=20)
    args = p.parse_args(argv)
    if args.command == "query":
        if args.limit < 1:
            p.error("--limit must be positive")
        for row in query(args.kind, args.text, args.category, args.limit):
            print(json.dumps(row, ensure_ascii=False))
    else:
        result = build(args.csv_path) if args.command == "build" else validate(args.with_candidates) if args.command == "validate" else json_read(MANIFEST)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())

