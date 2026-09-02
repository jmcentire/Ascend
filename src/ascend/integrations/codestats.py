"""File classification and code-volume accounting.

ANALYSIS_STANDARD.md §1.5 Gate 1: never count raw lines. In the Wander codebase only
~22% of added lines are production code — 36% is data (prompt corpora; one commit of
948K lines), 15% generated (`.d.ts` API clients at 400K lines, lockfiles), 13% test.
Unclassified, a single engineer showed 33,023,081 insertions and topped every volume
ranking on committed data files.

Classes: prod_code | test | fixture | generated | data | config | docs | other.
Only prod_code and test count as authored code.
"""

from __future__ import annotations

import re

LOCK = re.compile(
    r"(^|/)(package-lock\.json|yarn\.lock|pnpm-lock\.yaml|deno\.lock|Cargo\.lock"
    r"|poetry\.lock|Gemfile\.lock|go\.sum|composer\.lock|uv\.lock)$"
)
GEN = re.compile(
    r"(^|/)(dist|build|out|\.next|generated|__generated__|vendor|third_party"
    r"|node_modules|\.terraform)/|\.(d\.ts|min\.js|min\.css|bundle\.js|pb\.go|gen\.go)$"
    r"|_pb2\.py$"
)
BIN = re.compile(
    r"\.(sqlite|db|png|jpe?g|gif|ico|svg|woff2?|ttf|eot|pdf|zip|gz|tar|parquet"
    r"|mp4|webp|avif|wasm|so|dylib)$", re.I,
)
FIXT = re.compile(
    r"(^|/)(fixtures?|__fixtures__|snapshots?|__snapshots__|testdata|cassettes|golden)/"
    r"|\.(snap|golden)$|(^|/)testing/.*/(expected|calls)/|(^|/)testing/.*\.json$", re.I,
)
DATA = re.compile(
    r"(^|/)(data|output|outputs|analysis|replays|corpus|corpora|dumps|exports"
    r"|seeds?|samples?)/|corpus|-report\.json$|mentions.*\.json$"
    r"|\.(csv|tsv|ndjson|jsonl)$", re.I,
)
DATA_EXT = re.compile(r"\.(json|ya?ml|csv|tsv|ndjson|jsonl|txt)$", re.I)
TEST = re.compile(
    r"(^|/)(tests?|__tests__|spec|e2e|integration|__integration__)/"
    r"|\.(test|spec)\.[a-z]+$", re.I,
)
CODE = re.compile(
    r"\.(ts|tsx|js|jsx|mjs|cjs|py|go|rs|rb|java|kt|swift|scala|sql|sh|bash|tf|vue|svelte)$",
    re.I,
)
DOC = re.compile(r"\.(md|mdx|txt|rst|adoc)$|(^|/)docs?/", re.I)
CFG = re.compile(
    r"\.(json|ya?ml|toml|ini|env|conf|cfg|xml|properties)$|^\.[a-z]+rc"
    r"|(^|/)Dockerfile|(^|/)Makefile", re.I,
)

AUTHORED = ("prod_code", "test")


def classify(path: str) -> str:
    """Classify a repo-relative path into one of the eight content classes."""
    if LOCK.search(path) or GEN.search(path) or BIN.search(path):
        return "generated"
    if FIXT.search(path):
        return "fixture"
    if DATA.search(path) and DATA_EXT.search(path):
        return "data"
    if TEST.search(path):
        return "test"
    if CODE.search(path):
        return "prod_code"
    if DOC.search(path):
        return "docs"
    if CFG.search(path):
        return "config"
    return "other"


def empty_line_stats() -> dict[str, int]:
    return {
        "prod_added": 0, "prod_deleted": 0,
        "test_added": 0, "generated_added": 0,
        "data_added": 0, "other_added": 0,
    }


def accumulate(stats: dict[str, int], path: str, added: int, deleted: int) -> None:
    """Fold one numstat row into a member's line stats."""
    cls = classify(path)
    if cls == "prod_code":
        stats["prod_added"] += added
        stats["prod_deleted"] += deleted
    elif cls == "test":
        stats["test_added"] += added
    elif cls in ("generated", "fixture"):
        stats["generated_added"] += added
    elif cls == "data":
        stats["data_added"] += added
    else:
        stats["other_added"] += added


def test_ratio(stats: dict[str, int]) -> float:
    """Share of authored lines that are test code."""
    authored = stats["prod_added"] + stats["test_added"]
    return round(stats["test_added"] / authored, 3) if authored else 0.0
