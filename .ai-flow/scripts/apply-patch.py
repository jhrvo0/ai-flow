#!/usr/bin/env python3
from __future__ import annotations

import argparse
import subprocess
from pathlib import Path


SENSITIVE_HINTS = (".env", "migrations", "docker-compose", "Dockerfile", ".github/workflows")


def run(cmd: list[str]) -> tuple[int, str]:
    p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    return p.returncode, ((p.stdout or "") + (p.stderr or "")).strip()


def main() -> int:
    ap = argparse.ArgumentParser(description="Aplica patch de forma controlada")
    ap.add_argument("--patch-file", required=True)
    ap.add_argument("--allow-sensitive", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    patch = Path(args.patch_file)
    if not patch.exists():
        print(f"patch file not found: {patch}")
        return 2

    patch_text = patch.read_text(encoding="utf-8", errors="replace")
    touched = [line[6:] for line in patch_text.splitlines() if line.startswith("+++ b/")]
    risky = [f for f in touched if any(h in f for h in SENSITIVE_HINTS)]
    if risky and not args.allow_sensitive:
        print("Patch bloqueado: arquivos sensiveis detectados.")
        for item in risky:
            print(f"- {item}")
        print("Use --allow-sensitive somente com aprovacao humana.")
        return 1

    cmd = ["git", "apply", "--check" if args.dry_run else "--index", str(patch)]
    rc, out = run(cmd)
    print(out)
    if rc != 0:
        return rc

    rc2, stat = run(["git", "diff", "--cached", "--stat"])
    if rc2 == 0:
        print("\nDiff stat:\n" + stat)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
