#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path


MEMORY_FILES = [
    "project-summary.md",
    "architecture.md",
    "conventions.md",
    "decisions.md",
    "known-issues.md",
]


def ensure_memory(root: Path) -> None:
    memory = root / "memory"
    memory.mkdir(parents=True, exist_ok=True)
    for name in MEMORY_FILES:
        f = memory / name
        if not f.exists():
            f.write_text(f"# {name.replace('.md', '').replace('-', ' ').title()}\n\n", encoding="utf-8")


def append_decision(root: Path, text: str) -> None:
    decisions = root / "memory" / "decisions.md"
    with decisions.open("a", encoding="utf-8") as fp:
        fp.write(f"- {text}\n")


def main() -> int:
    ap = argparse.ArgumentParser(description="Atualiza memoria do AI-Flow")
    ap.add_argument("--decision", help="Decisao a registrar")
    args = ap.parse_args()

    root = Path(__file__).resolve().parents[1]
    ensure_memory(root)
    if args.decision:
        append_decision(root, args.decision)
        print("Decisao registrada.")
    else:
        print("Memoria inicializada.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
