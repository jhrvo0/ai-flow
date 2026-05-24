#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def run_shell(command: str) -> tuple[int, str]:
    proc = subprocess.run(command, shell=True, capture_output=True, text=True, encoding="utf-8", errors="replace")
    return proc.returncode, ((proc.stdout or "") + (proc.stderr or "")).strip()


def load_commands() -> dict:
    cfg = ROOT / "config.json"
    if not cfg.exists():
        return {}
    data = json.loads(cfg.read_text(encoding="utf-8"))
    return data.get("commands", {})


def looks_like_env_error(output: str) -> bool:
    text = output.lower()
    patterns = [
        "is not recognized as the name",
        "command not found",
        "no such file or directory",
        "not found",
    ]
    return any(p in text for p in patterns)


def command_binary(command: str) -> str:
    return command.strip().split()[0] if command.strip() else ""


def try_commands(candidates: list[str]) -> tuple[bool, str, str]:
    """
    Returns: (ok, used_command, message)
    """
    last_msg = ""
    for cmd in candidates:
        binary = command_binary(cmd)
        if binary and shutil.which(binary) is None:
            last_msg = f"binario ausente no PATH: {binary}"
            continue
        rc, out = run_shell(cmd)
        if rc == 0:
            return True, cmd, (out.splitlines()[0][:200] if out else "ok")
        if looks_like_env_error(out):
            last_msg = f"erro de ambiente: {out.splitlines()[0][:200] if out else 'falha de ambiente'}"
            continue
        last_msg = f"erro de codigo/config: {out.splitlines()[0][:200] if out else 'falha'}"
    return False, "", last_msg or "sem comandos executaveis"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--review-only", action="store_true")
    args = ap.parse_args()

    commands = load_commands()
    order = ["format", "lint", "typecheck", "test", "build"]
    if args.quick:
        order = ["lint", "typecheck"]
    if args.review_only:
        order = ["lint", "typecheck"]

    all_ok = True
    lines = ["## Comandos executados"]
    for key in order:
        cmds = commands.get(key, [])
        if not cmds:
            lines.append(f"- {key}: sem comando configurado")
            continue
        if args.dry_run:
            lines.append(f"- {key}: DRY-RUN -> {cmds[0]}")
            continue
        ok, used, msg = try_commands(cmds)
        if ok:
            lines.append(f"- {key}: APROVADO -> {used}")
            lines.append(f"  {msg}")
            continue
        lines.append(f"- {key}: REPROVADO -> tentativas: {len(cmds)}")
        lines.append(f"  {msg}")
        if "ambiente" in msg or "PATH" in msg:
            lines.append("  classificacao: ambiente")
        else:
            lines.append("  classificacao: codigo/config")
        if not ok:
            all_ok = False

    run_dir = Path(args.run_dir)
    (run_dir / "checks-summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
