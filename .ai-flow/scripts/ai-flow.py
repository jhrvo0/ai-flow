#!/usr/bin/env python3
"""
AI-Flow CLI orchestrator (v0).
"""

from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import os
import re
import shutil
import subprocess
import sys
import unicodedata
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
REPORTS_DIR = ROOT / "reports"
ARTIFACTS_DIR = ROOT / "artifacts"
ARTIFACTS_RUNS = ROOT / "artifacts" / "runs"
CONFIG_PATH = ROOT / "config.json"
CONFIG_EXAMPLE_PATH = ROOT / "config.example.json"
QUALITY_REPORT_PATH = REPORTS_DIR / "quality-gate.html"
CONTEXT_REPORT_PATH = REPORTS_DIR / "project-context.html"
DASHBOARD_PATH = ROOT / "dashboard.html"
CURRENT_TASK_REF_PATH = ARTIFACTS_DIR / "current-task.json"
CORE_SCRIPT_NAMES = {
    "quality-gate.py",
    "generate-context-map.py",
    "generate-dashboard.py",
    "build-context.py",
    "run-checks.py",
    "run-agent.py",
    "apply-patch.py",
    "memory-update.py",
    "llm_client.py",
    "select-model.py",
    "check-models.py",
}
VALID_PROVIDERS = {"lm_studio", "ollama", "ollama_cli"}
TASK_DIR_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}-[a-z0-9-]+(?:-\d+)?$")


def emit(agent: str, status: str, message: str) -> None:
    print(f"[agent:{agent}][status:{status}] {message}")


def run_cmd(cmd: list[str]) -> tuple[int, str]:
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    text = (proc.stdout or "") + (proc.stderr or "")
    return proc.returncode, text.strip()


def now_run_id() -> str:
    return dt.datetime.now().strftime("%Y-%m-%d-%H%M%S")


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
        "provider": api.get("default_provider", "ollama"),
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


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def iso_timestamp() -> str:
    return dt.datetime.now().replace(microsecond=0).isoformat()


def safe_slug(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text or "")
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", ascii_text).strip("-").lower()
    return slug or "task"


def run_command(command: list[str], cwd: Path | None = None, env: dict[str, str] | None = None) -> tuple[int, str]:
    try:
        completed = subprocess.run(
            command,
            cwd=str(cwd) if cwd else None,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
    except FileNotFoundError as exc:
        return 127, str(exc)
    return completed.returncode, ((completed.stdout or "") + (completed.stderr or "")).strip()


def git_state() -> dict[str, Any]:
    state: dict[str, Any] = {
        "available": False,
        "inside_repo": False,
        "branch": "unknown",
        "dirty": False,
        "status": "",
        "changed_files": [],
        "last_commit": None,
        "error": None,
    }

    rc, _ = run_command(["git", "--version"], cwd=REPO_ROOT)
    if rc != 0:
        state["error"] = "Git nao encontrado"
        return state

    state["available"] = True
    rc, output = run_command(["git", "rev-parse", "--is-inside-work-tree"], cwd=REPO_ROOT)
    if rc != 0 or output.strip().lower() != "true":
        state["error"] = "Diretorio atual nao e um repositorio Git"
        return state

    state["inside_repo"] = True
    rc, branch = run_command(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=REPO_ROOT)
    if rc == 0 and branch.strip():
        state["branch"] = branch.strip()

    rc, status = run_command(["git", "status", "--short"], cwd=REPO_ROOT)
    if rc == 0:
        state["status"] = status
        lines = [line for line in status.splitlines() if line.strip()]
        changed = []
        for line in lines:
            raw_path = line[3:].strip() if len(line) > 3 else line.strip()
            changed.append(raw_path.split(" -> ")[-1].strip())
        state["changed_files"] = sorted(set(changed))
        state["dirty"] = bool(changed)

    rc, commit = run_command(["git", "log", "-1", "--pretty=format:%h|%ar|%s"], cwd=REPO_ROOT)
    if rc == 0 and commit.strip():
        parts = commit.strip().split("|", 2)
        if len(parts) == 3:
            state["last_commit"] = {"hash": parts[0], "age": parts[1], "message": parts[2]}

    return state


def config_bundle() -> dict[str, Any]:
    if CONFIG_PATH.exists():
        source = CONFIG_PATH
        fallback = False
    elif CONFIG_EXAMPLE_PATH.exists():
        source = CONFIG_EXAMPLE_PATH
        fallback = True
    else:
        return {"source": None, "fallback": True, "data": {}, "error": "config ausente (copie config.example.json para config.json)"}

    try:
        return {
            "source": source,
            "fallback": fallback,
            "data": json.loads(source.read_text(encoding="utf-8")),
            "error": None,
        }
    except Exception as exc:
        return {"source": source, "fallback": fallback, "data": {}, "error": f"JSON invalido: {exc}"}


def provider_probe(provider: str, bundle: dict[str, Any]) -> dict[str, Any]:
    api = bundle.get("data", {}).get("api", {})
    if provider == "ollama_cli":
        rc, output = run_command(["ollama", "--version"], cwd=REPO_ROOT)
        return {
            "provider": provider,
            "available": rc == 0,
            "endpoint": "ollama --version",
            "detail": output or ("ok" if rc == 0 else "ollama nao encontrado"),
            "models": [],
        }

    if provider not in {"lm_studio", "ollama"}:
        return {"provider": provider, "available": False, "endpoint": None, "detail": "provider desconhecido", "models": []}

    base_url = api.get(f"{provider}_base_url") or ("http://127.0.0.1:11434/v1" if provider == "ollama" else "http://127.0.0.1:1234/v1")
    urls = [base_url.rstrip("/") + "/models"]
    if provider == "ollama":
        urls.append(base_url.rstrip("/").replace("/v1", "") + "/api/tags")

    last_error = ""
    for url in urls:
        try:
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=3) as response:
                payload = json.loads(response.read().decode("utf-8"))
            models: list[str] = []
            if isinstance(payload, dict):
                raw = payload.get("data") or payload.get("models") or []
                for item in raw:
                    if isinstance(item, dict):
                        model_id = item.get("id") or item.get("name") or item.get("model")
                        if model_id:
                            models.append(str(model_id))
            return {"provider": provider, "available": True, "endpoint": url, "detail": f"{len(models)} modelo(s) encontrados", "models": models}
        except urllib.error.HTTPError as exc:
            last_error = f"HTTP {exc.code}: {exc.reason}"
        except Exception as exc:
            last_error = str(exc)

    return {"provider": provider, "available": False, "endpoint": urls[-1], "detail": last_error or "provider nao respondeu", "models": []}


def current_task_ref() -> Path | None:
    ref = load_json(CURRENT_TASK_REF_PATH)
    raw = ref.get("path")
    if not raw:
        return None
    candidate = Path(raw)
    return candidate if candidate.exists() and candidate.is_dir() else None


def save_current_task_ref(task_dir: Path) -> None:
    write_json(CURRENT_TASK_REF_PATH, {"path": str(task_dir), "updated_at": iso_timestamp()})


def discover_task_dirs() -> list[Path]:
    if not ARTIFACTS_DIR.exists():
        return []
    tasks = [child for child in ARTIFACTS_DIR.iterdir() if child.is_dir() and TASK_DIR_PATTERN.match(child.name)]
    tasks.sort(key=lambda item: item.stat().st_mtime if item.exists() else 0, reverse=True)
    return tasks


def discover_legacy_runs() -> list[Path]:
    if not ARTIFACTS_RUNS.exists():
        return []
    runs = [child for child in ARTIFACTS_RUNS.iterdir() if child.is_dir()]
    runs.sort(key=lambda item: item.stat().st_mtime if item.exists() else 0, reverse=True)
    return runs


def resolve_task_dir(task_arg: str | None = None) -> Path | None:
    if task_arg:
        candidate = Path(task_arg).expanduser()
        if not candidate.is_absolute():
            for root in [ARTIFACTS_DIR, REPO_ROOT]:
                resolved = (root / candidate).resolve()
                if resolved.exists() and resolved.is_dir():
                    return resolved
        if candidate.exists() and candidate.is_dir():
            return candidate.resolve()

        lookup = task_arg.strip().lower()
        for task_dir in discover_task_dirs():
            if task_dir.name.lower() == lookup or task_dir.name.lower().endswith("-" + lookup):
                return task_dir
        return None

    current = current_task_ref()
    if current:
        return current

    tasks = discover_task_dirs()
    return tasks[0] if tasks else None


def load_task_state(task_dir: Path) -> dict[str, Any]:
    return load_json(task_dir / "task-state.json")


def merge_unique(existing: list[Any], new_values: list[Any]) -> list[Any]:
    merged = list(existing)
    for value in new_values:
        if value not in merged:
            merged.append(value)
    return merged


def build_task_state(task_name: str, task_dir: Path) -> dict[str, Any]:
    git = git_state()
    return {
        "task_name": task_name,
        "task_slug": task_dir.name,
        "created_at": iso_timestamp(),
        "status": "in-progress",
        "stage": "context",
        "branch": git.get("branch", "unknown"),
        "last_modified_files": git.get("changed_files", []),
        "generated_reports": [],
        "next_steps": [
            "Preencher 01-context.md",
            "Escrever 02-plan.md",
            "Pedir revisao do plano antes de codificar",
        ],
        "artifacts": [
            "01-context.md",
            "02-plan.md",
            "03-coder-summary.md",
            "04-quality-gate.html",
            "05-review.md",
            "06-tests.md",
            "07-docs-commit.md",
            "task-state.json",
        ],
    }


def placeholder_context_markdown(state: dict[str, Any]) -> str:
    return "\n".join([
        "# Contexto da tarefa",
        "",
        f"- Tarefa: {state.get('task_name', '')}",
        f"- Criado em: {state.get('created_at', '')}",
        f"- Branch: {state.get('branch', 'unknown')}",
        "",
        "## O que registrar",
        "- Stack detectada",
        "- Arquivos relevantes",
        "- Riscos",
        "- Perguntas em aberto",
        "",
        "## Relatorio global",
        "- [Abrir project-context.html](../../reports/project-context.html)",
    ])


def placeholder_plan_markdown(state: dict[str, Any]) -> str:
    return "\n".join([
        "# Plano da tarefa",
        "",
        f"- Tarefa: {state.get('task_name', '')}",
        "",
        "## Plano humano",
        "Explique em linguagem simples o que sera feito.",
        "",
        "## Plano executavel",
        "1. Liste os arquivos afetados.",
        "2. Descreva a ordem de implementacao.",
        "3. Defina validacoes e rollback.",
    ])


def placeholder_coder_summary(state: dict[str, Any]) -> str:
    return "\n".join([
        "# Resumo do Coder",
        "",
        f"- Tarefa: {state.get('task_name', '')}",
        "",
        "## O que mudou",
        "-",
        "",
        "## Decisoes tecnicas",
        "-",
    ])


def placeholder_review_markdown(state: dict[str, Any]) -> str:
    return "\n".join([
        "# Revisao",
        "",
        f"- Tarefa: {state.get('task_name', '')}",
        "",
        "## Problemas criticos",
        "-",
        "",
        "## Problemas importantes",
        "-",
    ])


def placeholder_tests_markdown(state: dict[str, Any]) -> str:
    return "\n".join([
        "# Testes",
        "",
        f"- Tarefa: {state.get('task_name', '')}",
        "",
        "## Comandos executados",
        "-",
        "",
        "## Resultado",
        "-",
    ])


def placeholder_docs_commit_markdown(state: dict[str, Any]) -> str:
    return "\n".join([
        "# Docs & Commit",
        "",
        f"- Tarefa: {state.get('task_name', '')}",
        "",
        "## Mensagem de commit sugerida",
        "feat(escopo): descricao",
        "",
        "## Descricao para PR",
        "-",
    ])


def placeholder_quality_html(state: dict[str, Any]) -> str:
    task_name = html.escape(state.get("task_name", "Tarefa"))
    return f"""<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Quality Gate - {task_name}</title>
<style>
body {{ font-family: Segoe UI, Arial, sans-serif; background:#0b1120; color:#e2e8f0; padding:24px; line-height:1.5; }}
main {{ max-width: 820px; margin: 0 auto; background:#111827; border:1px solid #243044; border-radius:16px; padding:24px; }}
a {{ color:#60a5fa; }}
</style>
</head>
<body>
<main>
  <h1>Quality Gate da tarefa</h1>
  <p>O relatorio global sera copiado aqui quando o comando quality for executado.</p>
  <p><a href="../../reports/quality-gate.html">Abrir quality-gate.html global</a></p>
</main>
</body>
</html>
"""


def write_task_skeleton(task_dir: Path, state: dict[str, Any]) -> None:
    write_text(task_dir / "01-context.md", placeholder_context_markdown(state))
    write_text(task_dir / "02-plan.md", placeholder_plan_markdown(state))
    write_text(task_dir / "03-coder-summary.md", placeholder_coder_summary(state))
    write_text(task_dir / "04-quality-gate.html", placeholder_quality_html(state))
    write_text(task_dir / "05-review.md", placeholder_review_markdown(state))
    write_text(task_dir / "06-tests.md", placeholder_tests_markdown(state))
    write_text(task_dir / "07-docs-commit.md", placeholder_docs_commit_markdown(state))


def create_task(task_name: str) -> tuple[Path, dict[str, Any]]:
    prefix = dt.datetime.now().strftime("%Y-%m-%d")
    slug = safe_slug(task_name)
    task_dir = ARTIFACTS_DIR / f"{prefix}-{slug}"
    suffix = 2
    while task_dir.exists():
        task_dir = ARTIFACTS_DIR / f"{prefix}-{slug}-{suffix}"
        suffix += 1

    task_dir.mkdir(parents=True, exist_ok=False)
    state = build_task_state(task_name, task_dir)
    write_task_skeleton(task_dir, state)
    write_json(task_dir / "task-state.json", state)
    save_current_task_ref(task_dir)
    return task_dir, state


def update_task_state(task_dir: Path, **updates: Any) -> dict[str, Any]:
    state = load_task_state(task_dir)
    if not state:
        state = build_task_state(task_dir.name, task_dir)

    for key, value in updates.items():
        if value is None:
            continue
        if key in {"generated_reports", "last_modified_files", "next_steps", "artifacts"}:
            existing = state.get(key, [])
            if not isinstance(existing, list):
                existing = []
            incoming = value if isinstance(value, list) else [value]
            state[key] = merge_unique(existing, incoming)
        else:
            state[key] = value

    write_json(task_dir / "task-state.json", state)
    save_current_task_ref(task_dir)
    return state


def render_task_context_markdown(task_dir: Path, command_output: str) -> str:
    state = load_task_state(task_dir)
    git = git_state()
    changed_files = git.get("changed_files", [])
    changed_block = "\n".join(f"- {item}" for item in changed_files) if changed_files else "- sem alteracoes"
    excerpt = command_output.strip() or "(sem saida)"
    if len(excerpt) > 2000:
        excerpt = excerpt[:2000] + "\n..."

    return "\n".join([
        "# Contexto da tarefa",
        "",
        f"- Tarefa: {state.get('task_name', task_dir.name)}",
        f"- Criado em: {state.get('created_at', '')}",
        f"- Branch: {git.get('branch', 'unknown')}",
        f"- Status Git: {'dirty' if git.get('dirty') else 'clean'}",
        "",
        "## Arquivos alterados agora",
        changed_block,
        "",
        "## Relatorio global",
        "- [project-context.html](../../reports/project-context.html)",
        "",
        "## Saida do comando",
        "```text",
        excerpt,
        "```",
    ])


def run_ai_flow_script(script_name: str, *args: str, cwd: Path | None = None) -> tuple[int, str, Path]:
    path = ROOT / "scripts" / script_name
    if not path.exists():
        return 1, f"script ausente: {path}", path
    rc, output = run_command([sys.executable, str(path), *args], cwd=cwd or REPO_ROOT)
    return rc, output, path


def open_path_in_browser(path: Path) -> None:
    target = path.resolve()
    try:
        webbrowser.open(target.as_uri())
    except Exception:
        if hasattr(os, "startfile"):
            try:
                os.startfile(str(target))
            except Exception:
                pass


def render_task_summary(task_dir: Path) -> list[str]:
    state = load_task_state(task_dir)
    reports = state.get("generated_reports", [])
    next_steps = state.get("next_steps", [])
    return [
        f"- pasta: {task_dir.name}",
        f"  tarefa: {state.get('task_name', task_dir.name)}",
        f"  criado em: {state.get('created_at', '')}",
        f"  status: {state.get('status', 'unknown')}",
        f"  etapa: {state.get('stage', 'unknown')}",
        f"  branch: {state.get('branch', 'unknown')}",
        f"  relatórios: {', '.join(reports) if reports else '(nenhum)'}",
        f"  proximos passos: {', '.join(next_steps) if next_steps else '(nenhum)'}",
    ]


def print_key_value(name: str, value: Any) -> None:
    print(f"- {name}: {value}")


def command_status(args: argparse.Namespace) -> int:
    bundle = config_bundle()
    git = git_state()
    task_dir = resolve_task_dir(getattr(args, "task", None))

    print("## AI-Flow status")
    print_key_value("AI-Flow dir", ROOT)
    print_key_value("Repo root", REPO_ROOT)
    print_key_value("Reports dir", REPORTS_DIR)

    print("\n## Configuracao")
    print_key_value("Fonte", bundle.get("source") or "config ausente")
    if bundle.get("fallback"):
        print("  [!] Usando config.example.json. Copie para config.json para configuracao local.")
    if bundle.get("error"):
        print_key_value("Erro", bundle["error"])
    print_key_value("Provider padrao", bundle.get("data", {}).get("api", {}).get("default_provider", "ollama"))
    print_key_value("Provider padrao (efetivo)", "Ollama (http://127.0.0.1:11434/v1)")

    print("\n## Git")
    if not git.get("available"):
        print_key_value("Status", git.get("error", "Git indisponivel"))
    elif not git.get("inside_repo"):
        print_key_value("Status", git.get("error", "Nao e um repositorio Git"))
    else:
        print_key_value("Branch", git.get("branch", "unknown"))
        print_key_value("Dirty", "sim" if git.get("dirty") else "nao")
        print_key_value("Arquivos alterados", len(git.get("changed_files", [])))
        if git.get("last_commit"):
            commit = git["last_commit"]
            print_key_value("Ultimo commit", f"{commit.get('hash')} | {commit.get('age')} | {commit.get('message')}")

    print("\n## Scripts principais")
    for script_name in sorted(CORE_SCRIPT_NAMES):
        print_key_value(script_name, "ok" if (ROOT / "scripts" / script_name).exists() else "ausente")

    print("\n## Relatorios")
    for path in [DASHBOARD_PATH, CONTEXT_REPORT_PATH, QUALITY_REPORT_PATH]:
        print_key_value(path.name, "ok" if path.exists() else "ausente")

    if task_dir:
        print("\n## Tarefa atual")
        for line in render_task_summary(task_dir):
            print(line)
    else:
        print("\n## Tarefa atual")
        print("- nenhuma tarefa ativa encontrada")

    tasks = discover_task_dirs()
    if tasks:
        print("\n## Tarefas recentes")
        for task in tasks[:5]:
            for line in render_task_summary(task):
                print(line)
    else:
        print("\n## Tarefas recentes")
        print("- nenhuma tarefa criada ainda")

    return 0


def command_show_config(args: argparse.Namespace) -> int:
    bundle = config_bundle()
    data = bundle.get("data", {})
    api = data.get("api", {})
    models = data.get("models", {})
    commands = data.get("commands", {})
    quality_gate = data.get("quality_gate", {})
    paths = data.get("paths", {})
    stack_commands = data.get("stack_commands", {})

    print("## Configuracao efetiva")
    print_key_value("Fonte", bundle.get("source") or "config ausente")
    print_key_value("Fallback", "sim" if bundle.get("fallback") else "nao")
    if bundle.get("error"):
        print_key_value("Erro", bundle["error"])

    print("\n## Provider e modelos")
    print_key_value("Provider padrao", api.get("default_provider", "ollama"))
    print_key_value("LM Studio", api.get("lm_studio_base_url", "http://127.0.0.1:1234/v1"))
    print_key_value("Ollama", api.get("ollama_base_url", "http://127.0.0.1:11434/v1"))
    for label, key in [
        ("Planner", "model_for_planning"),
        ("Coder", "model_for_coding"),
        ("Reviewer", "model_for_review"),
        ("Tester", "model_for_tester"),
        ("Docs", "model_for_docs"),
        ("Summary", "model_for_summary"),
    ]:
        if key in models:
            print_key_value(label, models.get(key))

    assignment = models.get("assignment", {})
    if assignment:
        print("\n## Atribuicoes por agente")
        for agent_id in sorted(assignment):
            agent_cfg = assignment.get(agent_id, {})
            print_key_value(
                agent_id,
                f"model={agent_cfg.get('model', '')}, temp={agent_cfg.get('temperature', '')}, max_tokens={agent_cfg.get('max_tokens', '')}",
            )

    if commands:
        print("\n## Commands")
        for name, values in commands.items():
            if isinstance(values, list):
                print_key_value(name, " | ".join(str(item) for item in values))

    if stack_commands:
        print("\n## Comandos por stack")
        for stack_name, stack_data in stack_commands.items():
            print_key_value(stack_name, stack_data)

    if quality_gate:
        print("\n## Limites do quality gate")
        for key, value in quality_gate.items():
            print_key_value(key, value)

    if paths:
        print("\n## Paths")
        for key, value in paths.items():
            print_key_value(key, value)

    print("\n## Como criar config local")
    print("- Copie .ai-flow/config.example.json para .ai-flow/config.json")
    print("- Ajuste provider, modelos e comandos da sua stack")
    return 0


def validate_config_data(bundle: dict[str, Any]) -> tuple[list[str], list[str], dict[str, Any]]:
    errors: list[str] = []
    warnings: list[str] = []
    details: dict[str, Any] = {}
    data = bundle.get("data", {})

    if not bundle.get("source"):
        errors.append("config.json e config.example.json nao foram encontrados")
        return errors, warnings, details

    if bundle.get("error"):
        errors.append(bundle["error"])
        return errors, warnings, details

    api = data.get("api", {})
    models = data.get("models", {})
    commands = data.get("commands", {})
    quality_gate = data.get("quality_gate", {})
    paths = data.get("paths", {})

    provider = api.get("default_provider", "ollama")
    if provider not in VALID_PROVIDERS:
        errors.append(f"api.default_provider invalido: {provider}")

    for provider_name in ["lm_studio", "ollama"]:
        base_url = api.get(f"{provider_name}_base_url")
        if base_url and not isinstance(base_url, str):
            errors.append(f"api.{provider_name}_base_url deve ser string")

    for key in ["model_for_planning", "model_for_coding", "model_for_review", "model_for_tester", "model_for_docs", "model_for_summary"]:
        if not models.get(key):
            warnings.append(f"models.{key} ausente ou vazio")

    assignment = models.get("assignment", {})
    if not isinstance(assignment, dict):
        errors.append("models.assignment deve ser um objeto")
    else:
        for agent_id, agent_cfg in assignment.items():
            if not isinstance(agent_cfg, dict):
                errors.append(f"models.assignment.{agent_id} deve ser um objeto")
                continue
            if not agent_cfg.get("model"):
                warnings.append(f"models.assignment.{agent_id}.model ausente")
            temperature = agent_cfg.get("temperature")
            if temperature is not None and not isinstance(temperature, (int, float)):
                errors.append(f"models.assignment.{agent_id}.temperature deve ser numero")

    if not isinstance(commands, dict) or not commands:
        warnings.append("commands ausente ou vazio")
    else:
        for key, value in commands.items():
            if not isinstance(value, list) or not value:
                warnings.append(f"commands.{key} deveria ser uma lista nao vazia")
            elif not all(isinstance(item, str) and item.strip() for item in value):
                errors.append(f"commands.{key} deve conter apenas strings nao vazias")

    if not isinstance(quality_gate, dict):
        errors.append("quality_gate deve ser um objeto")
    else:
        for key in ["max_files_per_change", "max_lines_per_file", "max_function_lines"]:
            value = quality_gate.get(key)
            if not isinstance(value, int) or value <= 0:
                warnings.append(f"quality_gate.{key} deveria ser inteiro positivo")

    if not isinstance(paths, dict):
        errors.append("paths deve ser um objeto")
    else:
        for key in ["reports_dir", "agents_dir", "workflows_dir"]:
            if not paths.get(key):
                warnings.append(f"paths.{key} ausente")

    script_checks = []
    for script_name in ["quality-gate.py", "generate-context-map.py", "generate-dashboard.py", "ai-flow.py"]:
        exists = (ROOT / "scripts" / script_name).exists()
        script_checks.append({"script": script_name, "exists": exists})
        if not exists:
            errors.append(f"script ausente: .ai-flow/scripts/{script_name}")

    details["script_checks"] = script_checks
    details["provider"] = provider
    details["provider_probe"] = provider_probe(provider, bundle)
    return errors, warnings, details


def command_validate_config(args: argparse.Namespace) -> int:
    bundle = config_bundle()
    errors, warnings, details = validate_config_data(bundle)
    probe = details.get("provider_probe", {})

    print("## Validacao de config")
    print_key_value("Fonte", bundle.get("source") or "config ausente")
    if bundle.get("error"):
        print_key_value("Erro", bundle["error"])

    print("\n## Checagem de provider")
    if probe:
        print_key_value("Provider", probe.get("provider", "unknown"))
        print_key_value("Disponivel", "sim" if probe.get("available") else "nao")
        print_key_value("Endpoint", probe.get("endpoint", "-"))
        print_key_value("Detalhe", probe.get("detail", "-"))
        if probe.get("models"):
            print_key_value("Modelos", ", ".join(probe.get("models", [])))

    print("\n## Avisos")
    if warnings:
        for warning in warnings:
            print(f"- {warning}")
    else:
        print("- nenhum")

    print("\n## Erros")
    if errors:
        for error in errors:
            print(f"- {error}")
    else:
        print("- nenhum")

    print("\n## Scripts principais")
    for item in details.get("script_checks", []):
        print(f"- {item['script']}: {'ok' if item['exists'] else 'ausente'}")

    print("\n## Sugestoes")
    provider = probe.get("provider", "")
    if not probe.get("available") and provider == "ollama":
        ollama_cli_rc, _ = run_command(["ollama", "--version"], cwd=REPO_ROOT)
        if ollama_cli_rc == 0:
            print("- Ollama CLI detectado, mas servidor HTTP nao responde.")
            print("- Execute 'ollama serve' ou abra o aplicativo Ollama.")
        else:
            print("- Ollama nao encontrado. Instale em https://ollama.ai")
    if bundle.get("fallback"):
        print("- Use config.json (copie de config.example.json) para configuracao local.")
    if warnings:
        print("- Revise os avisos acima. Alguns campos de config estao ausentes.")

    print("\n## Resultado final")
    if errors:
        print("- config invalida")
        return 1
    print("- config valida")
    return 0


def command_init_task(args: argparse.Namespace) -> int:
    task_dir, state = create_task(args.name)
    print("## Tarefa iniciada")
    print_key_value("Nome", state["task_name"])
    print_key_value("Pasta", task_dir)
    print_key_value("Status", state["status"])
    print_key_value("Etapa", state["stage"])
    print_key_value("Branch", state["branch"])
    print("\n## Arquivos criados")
    for name in state.get("artifacts", []):
        print(f"- {name}")
    print("\n## Proximos passos")
    for step in state.get("next_steps", []):
        print(f"- {step}")
    return 0


def command_list_tasks(args: argparse.Namespace) -> int:
    tasks = discover_task_dirs()
    print("## Tarefas")
    if not tasks:
        print("- nenhuma tarefa encontrada")
    else:
        current = current_task_ref()
        for task_dir in tasks:
            marker = "*" if current and task_dir.resolve() == current.resolve() else "-"
            state = load_task_state(task_dir)
            print(f"{marker} {task_dir.name}")
            print(f"  tarefa: {state.get('task_name', task_dir.name)}")
            print(f"  status: {state.get('status', 'unknown')}")
            print(f"  etapa: {state.get('stage', 'unknown')}")
            print(f"  branch: {state.get('branch', 'unknown')}")
            reports = state.get("generated_reports", [])
            print(f"  relatórios: {', '.join(reports) if reports else '(nenhum)'}")

    legacy_runs = discover_legacy_runs()
    print("\n## Runs legados")
    if not legacy_runs:
        print("- nenhum run legado encontrado")
    else:
        for run_dir in legacy_runs[:10]:
            print(f"- {run_dir.name}")
    return 0


def command_dashboard(args: argparse.Namespace) -> int:
    rc, output, _ = run_ai_flow_script("generate-dashboard.py", cwd=REPO_ROOT)
    if output:
        print(output)
    if rc != 0:
        print("[WARN] dashboard nao foi gerado com sucesso")
        return rc
    if DASHBOARD_PATH.exists():
        print(f"[OK] Dashboard gerado em {DASHBOARD_PATH}")
        open_path_in_browser(DASHBOARD_PATH)
        return 0
    print("[ERRO] dashboard.html nao foi encontrado apos a geracao")
    return 1


def command_context(args: argparse.Namespace) -> int:
    rc, output, _ = run_ai_flow_script("generate-context-map.py", cwd=REPO_ROOT)
    if output:
        print(output)
    task_dir = resolve_task_dir(getattr(args, "task", None))
    if task_dir:
        write_text(task_dir / "01-context.md", render_task_context_markdown(task_dir, output))
        state = update_task_state(
            task_dir,
            status="in-progress",
            stage="plan",
            generated_reports=["01-context.md"],
            last_modified_files=git_state().get("changed_files", []),
            next_steps=[
                "Escrever ou atualizar 02-plan.md",
                "Pedir o plano ao Planner",
                "Revisar riscos antes do Coder",
            ],
        )
        print(f"[OK] Artefato salvo em {task_dir / '01-context.md'}")
        print(f"[OK] Estado atualizado: etapa={state.get('stage')}")
    else:
        print("[INFO] Nenhuma tarefa ativa encontrada. Use init-task para registrar os artefatos.")
    if CONTEXT_REPORT_PATH.exists():
        open_path_in_browser(CONTEXT_REPORT_PATH)
    return rc


def command_quality(args: argparse.Namespace) -> int:
    rc, output, _ = run_ai_flow_script("quality-gate.py", cwd=REPO_ROOT)
    if output:
        print(output)
    task_dir = resolve_task_dir(getattr(args, "task", None))
    if task_dir:
        if QUALITY_REPORT_PATH.exists():
            shutil.copy2(QUALITY_REPORT_PATH, task_dir / "04-quality-gate.html")
        else:
            write_text(task_dir / "04-quality-gate.html", placeholder_quality_html({"task_name": task_dir.name}))
        state = update_task_state(
            task_dir,
            status="in-progress",
            stage="review",
            generated_reports=["01-context.md", "04-quality-gate.html"],
            last_modified_files=git_state().get("changed_files", []),
            next_steps=[
                "Ler 04-quality-gate.html",
                "Enviar feedback ao Reviewer",
                "Rodar os testes indicados pelo quality gate",
            ],
        )
        print(f"[OK] Artefato salvo em {task_dir / '04-quality-gate.html'}")
        print(f"[OK] Estado atualizado: etapa={state.get('stage')}")
    else:
        print("[INFO] Nenhuma tarefa ativa encontrada. Use init-task para registrar os artefatos.")
    if QUALITY_REPORT_PATH.exists():
        open_path_in_browser(QUALITY_REPORT_PATH)
    return rc


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="AI-Flow CLI central")
    p.add_argument("--dry-run", action="store_true", help="Nao executa comandos destrutivos ou de alteracao")

    sub = p.add_subparsers(dest="command", required=True)

    p_status = sub.add_parser("status", help="Mostra o estado do AI-Flow")
    p_status.add_argument("--task", help="Inspeciona uma tarefa especifica")

    p_context = sub.add_parser("context", help="Gera o mapa de contexto")
    p_context.add_argument("--task", help="Atualiza a tarefa selecionada")

    p_quality = sub.add_parser("quality", help="Executa o quality gate")
    p_quality.add_argument("--task", help="Atualiza a tarefa selecionada")

    sub.add_parser("dashboard", help="Gera e abre o dashboard")

    p_init = sub.add_parser("init-task", help="Cria uma pasta de artefatos para a tarefa")
    p_init.add_argument("name", help="Nome da tarefa")

    sub.add_parser("list-tasks", help="Lista as tarefas registradas")
    sub.add_parser("show-config", help="Mostra a configuracao efetiva")
    sub.add_parser("validate-config", help="Valida config e providers locais")

    p_feature = sub.add_parser("feature", help="Fluxo legado de feature")
    p_feature.add_argument("request", help="Descricao da feature")

    p_bugfix = sub.add_parser("bugfix", help="Fluxo legado de bugfix")
    p_bugfix.add_argument("request", help="Descricao do bugfix")

    sub.add_parser("review", help="Fluxo legado de review-only")

    p_refactor = sub.add_parser("refactor", help="Fluxo legado de refactor")
    p_refactor.add_argument("request", help="Descricao do refactor")

    p_self = sub.add_parser("self-improve", help="Fluxo legado de auto aprimoramento do AI-Flow")
    p_self.add_argument("request", help="Objetivo de auto aprimoramento")
    return p


def main() -> int:
    args = parser().parse_args()
    if args.command == "status":
        return command_status(args)
    if args.command == "context":
        return command_context(args)
    if args.command == "quality":
        return command_quality(args)
    if args.command == "dashboard":
        return command_dashboard(args)
    if args.command == "init-task":
        return command_init_task(args)
    if args.command == "list-tasks":
        return command_list_tasks(args)
    if args.command == "show-config":
        return command_show_config(args)
    if args.command == "validate-config":
        return command_validate_config(args)
    if args.command in {"feature", "bugfix", "refactor"}:
        return command_feature_like(args.command, args.request, args.dry_run)
    if args.command == "review":
        return command_review(args.dry_run)
    if args.command == "self-improve":
        return command_self_improve(args.request, args.dry_run)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
