#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path


def run(cmd: list[str]) -> str:
    p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    return ((p.stdout or "") + (p.stderr or "")).strip()


def detect_stack(root: Path) -> dict:
    return {
        "python": (root / "pyproject.toml").exists() or (root / "requirements.txt").exists(),
        "node": (root / "package.json").exists(),
        "java": (root / "pom.xml").exists(),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--request", required=True)
    args = ap.parse_args()

    run_dir = Path(args.run_dir)
    root = Path.cwd()
    stack = detect_stack(root)
    git_status = run(["git", "status", "--short"])
    files = run(["git", "diff", "--name-only"])

    payload = {
        "request": args.request,
        "stack": stack,
        "git_status": git_status.splitlines(),
        "changed_files": [line for line in files.splitlines() if line.strip()],
    }
    (run_dir / "context.json").write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")

    print("## Stack detectada")
    print(f"- node: {stack['node']}")
    print(f"- python: {stack['python']}")
    print(f"- java: {stack['java']}")
    print("\n## Arquivos alterados")
    if payload["changed_files"]:
        for f in payload["changed_files"][:20]:
            print(f"- {f}")
    else:
        print("- sem alteracoes locais")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
