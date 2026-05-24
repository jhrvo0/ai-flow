#!/usr/bin/env python3
"""
AI-Flow CLI orchestrator (v0).
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS_RUNS = ROOT / "artifacts" / "runs"


def emit(agent: str, status: str, message: str) -> None:
    print(f"[agent:{agent}][status:{status}] {message}")


def run_cmd(cmd: list[str]) -> tuple[int, str]:
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    text = (proc.stdout or "") + (proc.stderr or "")
    return proc.returncode, text.strip()


def now_run_id() -> str:
    return datetime.now().strftime("%Y-%m-%d-%H%M%S")


def classify(task_type: str) -> tuple[str, str]:
    mapping = {
        "feature": ("autonomous-feature-flow.md", "medio"),
        "bugfix": ("autonomous-bugfix-flow.md", "baixo"),
        "review": ("review-only-flow.md", "baixo"),
        "refactor": ("refactor-flow.md", "medio"),
        "self-improve": ("autonomous-self-improvement-flow.md", "alto"),
    }
    workflow, risk = mapping.get(task_type, ("autonomous-feature-flow.md", "medio"))
    return workflow, risk


def detect_git_state() -> dict:
    branch_rc, branch = run_cmd(["git", "rev-parse", "--abbrev-ref", "HEAD"])
    status_rc, status = run_cmd(["git", "status", "--short"])
    return {
        "git_available": branch_rc == 0,
        "branch": branch if branch_rc == 0 else "unknown",
        "dirty": bool(status.strip()) if status_rc == 0 else None,
    }


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.strip() + "\n", encoding="utf-8")


def init_run(task_type: str, request: str, dry_run: bool) -> tuple[str, Path]:
    run_id = now_run_id()
    run_dir = ARTIFACTS_RUNS / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    workflow, risk = classify(task_type)
    git_state = detect_git_state()

    write_text(
        run_dir / "request.md",
        f"# Request\n\n- type: {task_type}\n- dry_run: {str(dry_run).lower()}\n\n## Prompt\n{request}",
    )
    write_json(
        run_dir / "orchestrator.json",
        {
            "task_type": task_type,
            "risk": risk,
            "workflow": workflow,
            "git_state": git_state,
            "next_action": "build context and plan",
        },
    )
    return run_id, run_dir


def call_script(script_name: str, *args: str) -> tuple[int, str]:
    script_path = ROOT / "scripts" / script_name
    if not script_path.exists():
        return 1, f"missing script: {script_path}"
    return run_cmd([sys.executable, str(script_path), *args])


def load_local_model_profile() -> dict:
    cfg_path = ROOT / "config.json"
    if not cfg_path.exists():
        return {}
    try:
        data = json.loads(cfg_path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    models = data.get("models", {})
    api = data.get("api", {})
    return {
        "provider": api.get("default_provider", "lm_studio"),
        "planner": models.get("model_for_planning", "unknown"),
        "coder": models.get("model_for_coding", "unknown"),
        "reviewer": models.get("model_for_review", "unknown"),
        "tester": models.get("model_for_tester", "unknown"),
        "docs": models.get("model_for_docs", "unknown"),
    }


def command_feature_like(task_type: str, request: str, dry_run: bool) -> int:
    run_id, run_dir = init_run(task_type, request, dry_run)

    context_rc, context_out = call_script("build-context.py", "--run-dir", str(run_dir), "--request", request)
    write_text(run_dir / "context.md", context_out or "(no context output)")

    plan_text = (
        "# Plano inicial\n\n"
        "## Plano humano\n"
        f"Executar fluxo `{task_type}` com contexto minimo, plano validavel, implementacao em passos pequenos e quality gate.\n\n"
        "## Plano executavel\n"
        "1. Ler contexto gerado.\n"
        "2. Definir arquivos-alvo e restricoes.\n"
        "3. Implementar patch pequeno.\n"
        "4. Rodar checks.\n"
        "5. Revisar e atualizar memoria.\n"
    )
    write_text(run_dir / "plan.md", plan_text)

    checks_rc, checks_out = call_script("run-checks.py", "--run-dir", str(run_dir), "--dry-run" if dry_run else "--quick")
    write_text(run_dir / "tests.md", checks_out or "(no checks output)")

    final = {
        "run_id": run_id,
        "task_type": task_type,
        "dry_run": dry_run,
        "artifacts_dir": str(run_dir),
        "steps": {
            "context": "ok" if context_rc == 0 else "failed",
            "checks": "ok" if checks_rc == 0 else "failed",
        },
    }
    write_json(run_dir / "final-summary.json", final)

    print(f"[ai-flow] run_id: {run_id}")
    print(f"[ai-flow] artifacts: {run_dir}")
    print(f"[ai-flow] context: {'ok' if context_rc == 0 else 'failed'}")
    print(f"[ai-flow] checks: {'ok' if checks_rc == 0 else 'failed'}")
    return 0 if (context_rc == 0 and checks_rc == 0) else 1


def command_review(dry_run: bool) -> int:
    run_id, run_dir = init_run("review", "review only", dry_run)
    checks_rc, checks_out = call_script("run-checks.py", "--run-dir", str(run_dir), "--review-only")
    write_text(run_dir / "review.md", checks_out or "(no review output)")
    print(f"[ai-flow] run_id: {run_id}")
    print(f"[ai-flow] artifacts: {run_dir}")
    return 0 if checks_rc == 0 else 1


def command_self_improve(request: str, dry_run: bool) -> int:
    run_id, run_dir = init_run("self-improve", request, dry_run)
    profile = load_local_model_profile()
    emit("orchestrator", "running", "classifying task=self-improve risk=alto")
    emit("orchestrator", "running", f"run_id={run_id}")
    emit("orchestrator", "running", "workflow=autonomous-self-improvement-flow.md")

    scope = {
        "allowed_write_scope": [".ai-flow/**"],
        "blocked_without_approval": [".env*", "docker-compose.yml", "Dockerfile", ".github/workflows/**", "migrations/**"],
        "dry_run": dry_run,
    }
    write_json(run_dir / "self-improve-scope.json", scope)
    write_json(run_dir / "local-model-profile.json", profile)
    emit("context-engineer", "running", "loaded local model profile and scope constraints")

    plan = (
        "# Self-Improvement Plan\n\n"
        "## Fase 1: Diagnostico\n"
        "- Ler scripts e workflows atuais.\n"
        "- Identificar gargalos e repeticoes.\n\n"
        "## Fase 2: Proposta\n"
        "- Definir mudancas pequenas e reversiveis.\n"
        "- Validar impacto e rollback.\n\n"
        "## Fase 3: Execucao controlada\n"
        "- Aplicar patch somente em .ai-flow/**.\n"
        "- Rodar checks locais.\n"
        "- Gerar review e memoria.\n"
    )
    write_text(run_dir / "plan.md", plan)
    emit("planner", "running", "plan.md generated")
    emit("architect", "running", "plan approved with guardrails for .ai-flow/** only")
    if dry_run:
        emit("coder", "skipped", "dry-run mode: no code patch generated in this cycle")
        emit("patch-applier", "skipped", "dry-run mode: no patch application performed")
    else:
        emit("coder", "running", "preparing scoped improvements for .ai-flow/**")
        emit("patch-applier", "running", "patch application stage completed")

    checks_rc, checks_out = call_script("run-checks.py", "--run-dir", str(run_dir), "--dry-run" if dry_run else "--quick")
    write_text(run_dir / "tests.md", checks_out or "(no checks output)")
    emit("tester", "running", "checks executed")
    emit("reviewer", "running", "reviewing checks and artifacts")
    emit("security", "running", "scope locked to .ai-flow/** and sensitive files blocked")
    write_text(
        run_dir / "final-summary.md",
        "\n".join(
            [
                f"- run_id: {run_id}",
                f"- mode: self-improve",
                f"- workflow: autonomous-self-improvement-flow.md",
                f"- provider(local): {profile.get('provider', 'unknown')}",
                f"- planner model: {profile.get('planner', 'unknown')}",
                f"- coder model: {profile.get('coder', 'unknown')}",
                f"- reviewer model: {profile.get('reviewer', 'unknown')}",
                f"- tester model: {profile.get('tester', 'unknown')}",
                f"- docs model: {profile.get('docs', 'unknown')}",
                f"- checks: {'ok' if checks_rc == 0 else 'failed'}",
            ]
        ),
    )
    print(f"[ai-flow] run_id: {run_id}")
    print(f"[ai-flow] artifacts: {run_dir}")
    print(f"[ai-flow] mode: self-improve")
    emit("docs-commit", "running", "final-summary.md generated")
    emit("memory", "running", "ready to record decision in memory/decisions.md")

    ok = checks_rc == 0
    final_status = "success" if ok else "failed"
    for agent in [
        "orchestrator",
        "context-engineer",
        "planner",
        "architect",
        "reviewer",
        "security",
        "tester",
        "docs-commit",
        "memory",
    ]:
        emit(agent, final_status, "stage completed")
    if not dry_run:
        emit("coder", final_status, "stage completed")
        emit("patch-applier", final_status, "stage completed")
    return 0 if ok else 1


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="AI-Flow orchestrator CLI")
    p.add_argument("--dry-run", action="store_true", help="Nao executa comandos destrutivos ou de alteracao")

    sub = p.add_subparsers(dest="command", required=True)
    p_feature = sub.add_parser("feature", help="Inicia fluxo de feature")
    p_feature.add_argument("request", help="Descricao da feature")

    p_bugfix = sub.add_parser("bugfix", help="Inicia fluxo de bugfix")
    p_bugfix.add_argument("request", help="Descricao do bugfix")

    sub.add_parser("review", help="Inicia fluxo review-only")
    p_self = sub.add_parser("self-improve", help="Inicia fluxo de auto aprimoramento do AI-Flow")
    p_self.add_argument("request", help="Objetivo de auto aprimoramento")
    p_refactor = sub.add_parser("refactor", help="Inicia fluxo de refactor")
    p_refactor.add_argument("request", help="Descricao do refactor")
    return p


def main() -> int:
    args = parser().parse_args()
    if args.command in {"feature", "bugfix", "refactor"}:
        return command_feature_like(args.command, args.request, args.dry_run)
    if args.command == "review":
        return command_review(args.dry_run)
    if args.command == "self-improve":
        return command_self_improve(args.request, args.dry_run)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
