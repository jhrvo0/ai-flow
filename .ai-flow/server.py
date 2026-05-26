"""
.ai-flow/server.py

Servidor HTTP local que serve o dashboard e expoe API para:
- Gerenciar projetos (listar, adicionar, remover)
- Rodar scripts (quality gate, context map)
- Consultar Git (status, branch, log, diff)
- Chamar Ollama (padrao) ou LM Studio para execucao de agentes
- Editor Monaco com snapshots, undo/redo e terminal ao vivo

Provider padrao: Ollama (http://127.0.0.1:11434/v1)
Provider fallback: LM Studio (http://127.0.0.1:1234/v1)

Uso:
  python .ai-flow/server.py
  # Abre em http://localhost:8899
"""

import subprocess
import datetime
import json
import os
import sys
import webbrowser
import threading
import time
import re
import difflib
import hashlib
import uuid
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

AI_FLOW_DIR = Path(__file__).resolve().parent
SERVER_PORT = 8899

# Globals for background terminal execution
TERMINAL_TASKS = {}
LATEST_TASK_ID = None


# ─── Utilitarios ──────────────────────────────────────────

def run_cmd(cmd, cwd=None):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, check=False,
                           encoding="utf-8", errors="replace", cwd=cwd)
        return r.stdout.strip(), r.stderr.strip(), r.returncode
    except FileNotFoundError:
        return "", "command not found", -1


def json_response(handler, data, status=200):
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.end_headers()
    handler.wfile.write(json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8"))


def error_response(handler, msg, status=500):
    json_response(handler, {"ok": False, "error": msg}, status)


def ok_response(handler, data=None):
    resp = {"ok": True}
    if data is not None:
        resp["data"] = data
    json_response(handler, resp)


def read_json(path):
    if Path(path).exists():
        try:
            return json.loads(Path(path).read_text(encoding="utf-8"))
        except Exception:
            return None
    return None


def write_json(path, data):
    Path(path).write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def load_config():
    cfg_path = AI_FLOW_DIR / "config.json"
    if not cfg_path.exists():
        cfg_path = AI_FLOW_DIR / "config.example.json"
    return read_json(cfg_path) or {}


# ─── Projetos ─────────────────────────────────────────────

def load_projects():
    """Auto-discover + manual, merged."""
    ai_flow = AI_FLOW_DIR
    root = ai_flow.parent

    auto = set()
    if (root / ".git").exists():
        auto.add(str(root.resolve()))
    try:
        for entry in sorted(root.iterdir()):
            if entry.is_dir() and not entry.name.startswith("."):
                if (entry / ".git").exists():
                    auto.add(str(entry.resolve()))
    except PermissionError:
        pass

    manual = set()
    pj = ai_flow / "projects.json"
    data = read_json(pj) if pj.exists() else []
    if isinstance(data, list):
        for p in data:
            manual.add(str(Path(p).resolve()))

    all_paths = sorted(auto | manual)
    write_json(pj, all_paths)
    return all_paths


def is_safe_project_path(proj_path_str):
    if not proj_path_str:
        return False
    try:
        resolved = str(Path(proj_path_str).resolve()).lower()
        valid_projects = [str(Path(p).resolve()).lower() for p in load_projects()]
        return resolved in valid_projects
    except Exception:
        return False


def is_safe_file_path(proj_path_str, file_path_str):
    if not is_safe_project_path(proj_path_str):
        return False
    try:
        resolved_proj = Path(proj_path_str).resolve()
        if not os.path.isabs(file_path_str):
            resolved_file = (resolved_proj / file_path_str).resolve()
        else:
            resolved_file = Path(file_path_str).resolve()
        
        proj_str = str(resolved_proj).lower()
        file_str = str(resolved_file).lower()
        
        sep = os.sep.lower()
        if not proj_str.endswith(sep):
            proj_str_sep = proj_str + sep
        else:
            proj_str_sep = proj_str
            
        return file_str == proj_str or file_str.startswith(proj_str_sep)
    except Exception:
        return False


def _update_active_task_state(project_path, report_name, stage=None):
    try:
        current_task_path = AI_FLOW_DIR / "artifacts" / "current-task.json"
        if current_task_path.exists():
            data = json.loads(current_task_path.read_text(encoding="utf-8"))
            path_str = data.get("path")
            if path_str:
                task_dir = Path(path_str)
                state_file = task_dir / "task-state.json"
                if state_file.exists():
                    state = json.loads(state_file.read_text(encoding="utf-8"))
                    
                    # Update reports list
                    reports = state.get("generated_reports", [])
                    if report_name not in reports:
                        reports.append(report_name)
                    state["generated_reports"] = reports
                    
                    # Update stage if provided
                    if stage:
                        state["stage"] = stage
                        
                    # Also update last modified files from git state if possible
                    try:
                        status_out, _, _ = run_cmd(["git", "status", "--porcelain"], cwd=project_path)
                        if status_out:
                            changed = []
                            for line in status_out.splitlines():
                                if len(line) > 3:
                                    changed.append(line[3:].strip())
                            state["last_modified_files"] = list(set(state.get("last_modified_files", []) + changed))
                    except Exception:
                        pass
                        
                    state["updated_at"] = datetime.datetime.now().isoformat()
                    state_file.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception as e:
        print(f"Erro ao atualizar o estado da tarefa: {e}")


def collect_recent_artifacts(project_path, limit=6):
    pp = Path(project_path)
    ai_flow_dir = pp / ".ai-flow"
    artifact_roots = [ai_flow_dir / "artifacts", ai_flow_dir / "reports"]
    artifacts = []
    seen = set()

    for root_dir in artifact_roots:
        if not root_dir.exists():
            continue
        try:
            for file_path in root_dir.rglob("*"):
                if not file_path.is_file():
                    continue
                resolved = str(file_path.resolve())
                if resolved in seen:
                    continue
                try:
                    mtime = file_path.stat().st_mtime
                except OSError:
                    mtime = 0
                artifacts.append({
                    "path": str(file_path.relative_to(pp)).replace("\\", "/"),
                    "name": file_path.name,
                    "kind": file_path.suffix.lower().lstrip(".") or "arquivo",
                    "mtime": mtime,
                })
                seen.add(resolved)
        except Exception:
            continue

    artifacts = sorted(artifacts, key=lambda item: item.get("mtime", 0), reverse=True)
    for item in artifacts[:limit]:
        item.pop("mtime", None)
    return artifacts[:limit]


def get_project_info(path):
    pp = Path(path)
    name = pp.name

    branch, _, _ = run_cmd(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=path)
    commit_out, _, _ = run_cmd(
        ["git", "log", "-1", "--pretty=format:%h|%an|%ar|%s"], cwd=path
    )
    commit = {"hash": "?", "author": "?", "date": "?", "message": "?"}
    if commit_out:
        parts = commit_out.split("|", 3)
        if len(parts) == 4:
            commit = dict(zip(["hash", "author", "date", "message"], parts))

    status_out, _, _ = run_cmd(["git", "status", "--porcelain"], cwd=path)
    has_changes = bool(status_out)
    changes_count = len(status_out.strip().split("\n")) if status_out else 0

    file_count = 0
    try:
        for f in pp.rglob("*"):
            if f.is_file() and ".git" not in f.parts:
                file_count += 1
        file_count = min(file_count, 9999)
    except Exception:
        pass

    date_out, _, _ = run_cmd(["git", "log", "-1", "--format=%ci", "--", "."], cwd=path)
    last_modified = (date_out or "")[:10]

    has_aiflow = (pp / ".ai-flow").exists()
    has_context = (pp / ".ai-flow" / "reports" / "project-context.html").exists()
    has_quality = (pp / ".ai-flow" / "reports" / "quality-gate.html").exists()
    has_diagnosis = (pp / ".ai-flow" / "reports" / "ai-flow-diagnosis.md").exists()
    has_manual_checklist = (pp / ".ai-flow" / "reports" / "manual-test-checklist.md").exists()
    recent_artifacts = collect_recent_artifacts(pp)

    return {
        "name": name, "path": str(pp.resolve()),
        "branch": branch or "?", "commit": commit,
        "has_changes": has_changes, "changes_count": changes_count,
        "file_count": file_count, "last_modified": last_modified,
        "has_aiflow": has_aiflow,
        "has_context_map": has_context, "has_quality_report": has_quality,
        "has_diagnosis": has_diagnosis,
        "has_manual_checklist": has_manual_checklist,
        "recent_artifacts": recent_artifacts,
    }


def get_projects_data():
    paths = load_projects()
    projects = []
    for p in paths:
        if not Path(p).exists():
            continue
        projects.append(get_project_info(p))
    return projects


# ─── Git helpers ──────────────────────────────────────────

def git_status(path):
    out, _, _ = run_cmd(["git", "status", "--porcelain"], cwd=path)
    entries = []
    for line in out.split("\n") if out else []:
        if line.strip():
            entries.append({"code": line[:2].strip(), "path": line[3:].strip()})
    return entries


def git_diff(path):
    out, _, _ = run_cmd(["git", "diff"], cwd=path)
    if not out:
        out, _, _ = run_cmd(["git", "diff", "--cached"], cwd=path)
    return out


def git_log(path, n=10):
    out, _, _ = run_cmd(
        ["git", "log", f"--max-count={n}", "--pretty=format:%h|%an|%ar|%s"],
        cwd=path
    )
    commits = []
    for line in out.split("\n") if out else []:
        parts = line.split("|", 3)
        if len(parts) == 4:
            commits.append(dict(zip(["hash", "author", "date", "message"], parts)))
    return commits


# ─── Run scripts ──────────────────────────────────────────

def run_quality_gate(project_path):
    script = AI_FLOW_DIR / "scripts" / "quality-gate.py"
    if not script.exists():
        return {"ok": False, "error": "quality-gate.py nao encontrado"}
    out, err, code = run_cmd(["python", str(script)], cwd=project_path)
    report_path = Path(project_path) / ".ai-flow" / "reports" / "quality-gate.html"
    if report_path.exists():
        _update_active_task_state(project_path, "quality-gate.html", "quality")
    return {
        "ok": code == 0,
        "output": out or err,
        "report_exists": report_path.exists(),
        "report_path": str(report_path) if report_path.exists() else None,
    }


def run_context_map(project_path):
    script = AI_FLOW_DIR / "scripts" / "generate-context-map.py"
    if not script.exists():
        return {"ok": False, "error": "generate-context-map.py nao encontrado"}
    out, err, code = run_cmd(["python", str(script)], cwd=project_path)
    report_path = Path(project_path) / ".ai-flow" / "reports" / "project-context.html"
    if report_path.exists():
        _update_active_task_state(project_path, "project-context.html", "context")
    return {
        "ok": code == 0,
        "output": out or err,
        "report_exists": report_path.exists(),
        "report_path": str(report_path) if report_path.exists() else None,
    }


def run_self_improve(project_path, request, dry_run=True):
    script = AI_FLOW_DIR / "scripts" / "ai-flow.py"
    if not script.exists():
        return {"ok": False, "error": "ai-flow.py nao encontrado"}
    python_bin = sys.executable or "python"
    cmd = [python_bin, str(script)]
    if dry_run:
        cmd.append("--dry-run")
    cmd.extend(["self-improve", request])
    out, err, code = run_cmd(cmd, cwd=project_path)
    return {
        "ok": code == 0,
        "output": out or err,
        "report_exists": False,
        "report_path": None,
    }


def run_regenerate_dashboard():
    script = AI_FLOW_DIR / "scripts" / "generate-dashboard.py"
    if not script.exists():
        return {"ok": False, "error": "generate-dashboard.py nao encontrado"}
    out, err, code = run_cmd(["python", str(script)], cwd=AI_FLOW_DIR.parent)
    return {"ok": code == 0, "output": out or err}


# ─── File operations ──────────────────────────────────────

FILE_IGNORE = {"node_modules", ".git", "__pycache__", ".next", "dist", "build", ".cache", "coverage", "venv", ".venv", "target"}
FILE_EXT_IGNORE = {".pyc", ".exe", ".dll", ".so", ".dylib", ".bin", ".jpg", ".png", ".gif", ".ico", ".svg", ".woff", ".woff2", ".ttf", ".eot"}

def list_files(project_path, depth=0, max_depth=4):
    """Retorna arvore de arquivos do projeto."""
    pp = Path(project_path)
    if not pp.exists() or depth > max_depth:
        return []
    entries = []
    try:
        items = sorted(pp.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower()))
    except PermissionError:
        return []
    for item in items:
        if item.name in FILE_IGNORE or item.suffix.lower() in FILE_EXT_IGNORE:
            continue
        if item.name.startswith(".") and item.name not in (".env.example", ".gitignore", ".ai-flow"):
            continue
        entry = {
            "name": item.name,
            "path": str(item.resolve()),
            "type": "dir" if item.is_dir() else "file",
            "size": item.stat().st_size if item.is_file() else 0,
        }
        if item.is_dir():
            entry["children"] = list_files(item, depth + 1, max_depth)
        entries.append(entry)
    return entries


def read_file_content(file_path):
    pp = Path(file_path)
    if not pp.exists() or not pp.is_file():
        return None, "Arquivo nao encontrado"
    try:
        content = pp.read_text(encoding="utf-8")
        return content, None
    except UnicodeDecodeError:
        return None, "Arquivo binario (nao foi possivel ler como texto)"
    except Exception as e:
        return None, str(e)


def write_file_content(file_path, content):
    pp = Path(file_path)
    try:
        pp.parent.mkdir(parents=True, exist_ok=True)
        pp.write_text(content, encoding="utf-8")
        return True, None
    except Exception as e:
        return False, str(e)


def find_project_path(file_path):
    try:
        file_path_abs = Path(file_path).resolve()
    except Exception:
        return str(AI_FLOW_DIR.parent.resolve())
    
    projects = load_projects()
    for p in projects:
        try:
            p_abs = Path(p).resolve()
            if hasattr(file_path_abs, "is_relative_to") and file_path_abs.is_relative_to(p_abs):
                return p
            else:
                # Fallback for Python < 3.9
                try:
                    file_path_abs.relative_to(p_abs)
                    return p
                except ValueError:
                    pass
        except Exception:
            pass
    return str(AI_FLOW_DIR.parent.resolve())


def is_dangerous_command(command):
    cmd_lower = command.lower().strip()
    dangerous_patterns = [
        r"\brm\s+-rf\b",
        r"\bdel\b",
        r"\bformat\b",
        r"\brmdir\s+/s\b",
        r"\bmkfs\b",
        r"\bdd\b"
    ]
    for pattern in dangerous_patterns:
        if re.search(pattern, cmd_lower):
            return True
    return False


def clean_tag_content(content):
    if content.startswith('\r\n'):
        content = content[2:]
    elif content.startswith('\n'):
        content = content[1:]
    if content.endswith('\r\n'):
        content = content[:-2]
    elif content.endswith('\n'):
        content = content[:-1]
    return content


def parse_patches(text):
    patches = []
    patch_pattern = re.compile(r'<patch\s+file=["\']([^"\']+)["\']>(.*?)</patch>', re.DOTALL)
    for file_path, block in patch_pattern.findall(text):
        search_blocks = re.findall(r'<search>(.*?)</search>', block, re.DOTALL)
        replace_blocks = re.findall(r'<replace>(.*?)</replace>', block, re.DOTALL)
        for s, r in zip(search_blocks, replace_blocks):
            patches.append({
                "file": file_path.strip(),
                "search": clean_tag_content(s),
                "replace": clean_tag_content(r)
            })
    return patches


def normalize_newlines(text):
    if text is None:
        return ""
    return text.replace("\r\n", "\n").replace("\r", "\n")


def apply_search_replace_patch(original_content, search_text, replace_text):
    if not search_text:
        return replace_text, None
        
    norm_orig = normalize_newlines(original_content)
    norm_search = normalize_newlines(search_text)
    norm_replace = normalize_newlines(replace_text)
    
    if norm_search not in norm_orig:
        return None, "Texto original (search) nao encontrado no arquivo. Verifique se o arquivo nao foi alterado."
        
    norm_new = norm_orig.replace(norm_search, norm_replace, 1)
    
    # Restore original line endings style if possible
    if "\r\n" in original_content and "\r\n" not in norm_new:
        norm_new = norm_new.replace("\n", "\r\n")
        
    return norm_new, None


# ─── Snapshot / Undo System ──────────────────────────────

AI_FLOW_HISTORY_DIR = AI_FLOW_DIR / "history"


def _ensure_history_dir(project_path, file_path):
    proj_hash = hashlib.sha256(str(Path(project_path).resolve()).encode()).hexdigest()[:12]
    file_hash = hashlib.sha256(str(Path(file_path).resolve()).encode()).hexdigest()[:12]
    hist_dir = AI_FLOW_HISTORY_DIR / proj_hash
    hist_dir.mkdir(parents=True, exist_ok=True)
    return hist_dir / f"{file_hash}.json"


def _load_history(project_path, file_path):
    hist_path = _ensure_history_dir(project_path, file_path)
    if hist_path.exists():
        try:
            return json.loads(hist_path.read_text(encoding="utf-8"))
        except Exception:
            return None
    return None


def _save_history(hist_path, data):
    Path(hist_path).write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def _compute_diff(old_content, new_content, fromfile="a", tofile="b"):
    if old_content is None: old_content = ""
    if new_content is None: new_content = ""
    old_lines = old_content.splitlines(keepends=True)
    new_lines = new_content.splitlines(keepends=True)
    diff_lines = list(difflib.unified_diff(old_lines, new_lines, fromfile=fromfile, tofile=tofile, n=3))
    return "".join(diff_lines)


def _run_qg_async(proj_path):
    try:
        run_quality_gate(proj_path)
    except Exception:
        pass


def take_snapshot(project_path, file_path, content=None, agent="manual", description="Edicao manual"):
    """Save a snapshot of the file content. If content is None, reads from file."""
    hist_path = _ensure_history_dir(project_path, file_path)
    if content is None:
        content, err = read_file_content(file_path)
        if err:
            return None, err

    history = _load_history(project_path, file_path)
    if history is None:
        history = {
            "file": str(Path(file_path).resolve()),
            "project": str(Path(project_path).resolve()),
            "snapshots": [],
            "current": None,
        }

    snapshot_id = f"s{len(history['snapshots']) + 1}"
    snapshot = {
        "id": snapshot_id,
        "timestamp": datetime.datetime.now().isoformat(),
        "content": content,
        "size": len(content) if content else 0,
        "agent": agent,
        "description": description,
    }
    history["snapshots"].append(snapshot)
    history["current"] = snapshot_id

    if len(history["snapshots"]) > 50:
        history["snapshots"] = history["snapshots"][-50:]

    _save_history(hist_path, history)
    return snapshot, None


def restore_snapshot(project_path, file_path, snapshot_id):
    history = _load_history(project_path, file_path)
    if not history:
        return None, "Nenhum historico encontrado"

    target = None
    for s in history["snapshots"]:
        if s["id"] == snapshot_id:
            target = s
            break

    if not target:
        return None, f"Snapshot {snapshot_id} nao encontrado"

    take_snapshot(project_path, file_path, description=f"Antes de desfazer para {snapshot_id}")
    ok, err = write_file_content(file_path, target["content"])
    if err:
        return None, err

    history["current"] = snapshot_id
    _save_history(_ensure_history_dir(project_path, file_path), history)
    return target, None


def get_history(project_path, file_path):
    history = _load_history(project_path, file_path)
    if not history:
        return {"ok": True, "data": {"file": file_path, "history": [], "current": None}}

    result = []
    for i, s in enumerate(history["snapshots"]):
        prev = history["snapshots"][i-1]["content"] if i > 0 else ""
        cur = s["content"]
        diff = _compute_diff(prev, cur) if prev != cur else ""
        result.append({
            "id": s["id"],
            "timestamp": s["timestamp"],
            "size": s["size"],
            "diff": diff[:1000],
            "agent": s.get("agent", "?"),
            "description": s.get("description", ""),
            "is_current": s["id"] == history.get("current"),
        })
    return {"ok": True, "data": {"file": file_path, "history": result, "current": history.get("current")}}


def get_diff_between(project_path, file_path, from_id, to_id):
    history = _load_history(project_path, file_path)
    if not history:
        return None, "Nenhum historico encontrado"

    from_content = to_content = None
    for s in history["snapshots"]:
        if s["id"] == from_id: from_content = s["content"]
        if s["id"] == to_id: to_content = s["content"]

    if from_content is None: return None, f"Snapshot {from_id} nao encontrado"
    if to_content is None: return None, f"Snapshot {to_id} nao encontrado"

    return _compute_diff(from_content, to_content), None


# ─── Git commit ──────────────────────────────────────────

def git_commit(project_path, message, author=None):
    cmds = [
        ["git", "add", "-A"],
        ["git", "commit", "-m", message],
    ]
    if author:
        cmds[1] = ["git", "commit", "-m", message, "--author", author]

    for cmd in cmds:
        out, err, code = run_cmd(cmd, cwd=project_path)
        if code != 0 and "nothing to commit" not in out and "nothing to commit" not in err:
            return {"ok": False, "step": " ".join(cmd), "error": err or out}
    return {"ok": True, "output": out}


# ─── Agent helpers ────────────────────────────────────────

AGENT_FILE_CANDIDATES = {
    "orchestrator": ["00-orchestrator.md"],
    "context-engineer": ["01-context-engineer.md"],
    "planner": ["02-planner.md", "planner.md"],
    "architect": ["03-architect.md"],
    "coder": ["04-coder.md", "coder.md"],
    "patch-applier": ["05-patch-applier.md"],
    "reviewer": ["06-reviewer.md", "reviewer-quality-gate.md"],
    "security": ["08-security.md"],
    "tester": ["07-tester.md", "tester.md"],
    "docs": ["09-docs-commit.md", "docs-commit.md"],
    "memory": ["10-memory.md"],
}

AGENT_LEGACY_ALIASES = {
    "reviewer-quality-gate": "reviewer",
    "docs-commit": "docs",
}

AGENT_MODEL_KEYS = {
    "orchestrator": "model_for_planning",
    "context-engineer": "model_for_planning",
    "planner": "model_for_planning",
    "architect": "model_for_planning",
    "coder": "model_for_coding",
    "patch-applier": "model_for_coding",
    "reviewer": "model_for_review",
    "security": "model_for_review",
    "tester": "model_for_tester",
    "docs": "model_for_docs",
    "memory": "model_for_summary",
    "summarizer": "model_for_summary",
}


def _agent_label_from_id(agent_id):
    return agent_id.replace("-", " ").replace("_", " ").title()


def _build_agent_catalog():
    agents_dir = AI_FLOW_DIR / "agents"
    catalog = []
    seen_files = set()

    for agent_id, candidates in AGENT_FILE_CANDIDATES.items():
        for filename in candidates:
            filepath = agents_dir / filename
            if filepath.exists():
                resolved = str(filepath.resolve())
                if resolved in seen_files:
                    break
                catalog.append({
                    "id": agent_id,
                    "name": _agent_label_from_id(agent_id),
                    "file": filename,
                    "path": resolved,
                })
                seen_files.add(resolved)
                break

    return catalog

def get_agents_list():
    return _build_agent_catalog()


def get_agent_content(agent_id):
    agents = {agent["id"]: agent for agent in _build_agent_catalog()}
    if agent_id not in agents:
        agent_id = AGENT_LEGACY_ALIASES.get(agent_id, agent_id)
    agent = agents.get(agent_id)
    if not agent:
        return None, "Agente nao encontrado"
    filepath = Path(agent["path"])
    if not filepath.exists():
        return None, "Arquivo do agente nao encontrado"
    try:
        content = filepath.read_text(encoding="utf-8")
        return content, None
    except Exception as e:
        return None, str(e)


def resolve_agent_model(provider, agent_id, explicit_model=""):
    if explicit_model and explicit_model != "__auto__":
        return explicit_model

    cfg = load_config()
    models_cfg = cfg.get("models", {})
    normalized_agent = AGENT_LEGACY_ALIASES.get(agent_id, agent_id or "")
    normalized_agent = normalized_agent.strip().lower()

    assignment_cfg = models_cfg.get("assignment", {}).get(normalized_agent, {})
    assigned_model = assignment_cfg.get("model")
    if assigned_model:
        return assigned_model

    model_key = AGENT_MODEL_KEYS.get(normalized_agent)
    fallback_model = assignment_cfg.get("fallback_model")
    if model_key:
        return resolve_model(provider, model_key, fallback_model or "qwen2.5-coder-7b-instruct")

    return resolve_model(provider, "model_for_coding", fallback_model or "qwen2.5-coder:7b")


# ─── Providers ────────────────────────────────────────────

PROVIDER_HELP = {
    "ollama": {
        "label": "Ollama (HTTP) - Recomendado",
        "base_url_key": "ollama_base_url",
        "default_url": "http://localhost:11434/v1",
        "type": "http",
    },
    "ollama_cli": {
        "label": "Ollama (CLI)",
        "type": "cli",
    },
    "lm_studio": {
        "label": "LM Studio (fallback)",
        "base_url_key": "lm_studio_base_url",
        "default_url": "http://localhost:1234/v1",
        "type": "http",
    },
}


def check_ollama_cli():
    out, err, code = run_cmd(["ollama", "--version"])
    return code == 0


def list_ollama_cli_models():
    out, err, code = run_cmd(["ollama", "list"])
    if code != 0 or not out:
        return {"ok": False, "error": err or "ollama list falhou", "models": []}
    models = []
    for line in out.split("\n"):
        line = line.strip()
        if not line or line.startswith("NAME") or line.startswith("---"):
            continue
        parts = line.split()
        if parts:
            name = parts[0]
            models.append({"id": name, "name": name})
    return {"ok": True, "models": models}


def call_ollama_cli(model, prompt, temperature=0.2):
    import shlex
    full_prompt = prompt.replace("\r\n", "\n").replace('"', "'")
    cmd = ["ollama", "run", model, full_prompt]
    env = {**os.environ, "OLLAMA_NOHISTORY": "1"}
    out, err, code = run_cmd_env(cmd, env=env)
    if code != 0:
        return {"ok": False, "error": err or out or "ollama CLI falhou"}
    return {"ok": True, "response": out.strip()}


def run_cmd_env(cmd, cwd=None, env=None):
    try:
        r = subprocess.run(
            cmd, capture_output=True, text=True, check=False,
            encoding="utf-8", errors="replace", cwd=cwd, env=env,
        )
        return r.stdout.strip(), r.stderr.strip(), r.returncode
    except FileNotFoundError:
        return "", "command not found", -1


def get_provider_config(provider=None):
    cfg = load_config()
    api_cfg = cfg.get("api", {})
    if not provider:
        provider = api_cfg.get("default_provider", "ollama")
    info = PROVIDER_HELP.get(provider, PROVIDER_HELP.get("ollama", PROVIDER_HELP["lm_studio"]))
    base_url = api_cfg.get(info.get("base_url_key", ""), info.get("default_url", ""))
    return provider, base_url.rstrip("/"), info.get("type", "http")


def resolve_model(provider, model_type_key, default_fallback):
    cfg = load_config()
    configured_model = cfg.get("models", {}).get(model_type_key)
    if configured_model:
        return configured_model
    res = list_provider_models(provider)
    if res.get("ok") and res.get("models"):
        return res["models"][0]["id"]
    return default_fallback


def list_provider_models(provider=None):
    provider, base_url, ptype = get_provider_config(provider)

    if ptype == "cli":
        return list_ollama_cli_models()

    import urllib.request
    urls_to_try = [f"{base_url}/models"]

    # Ollama also supports /api/tags
    if provider == "ollama":
        ollama_base = base_url.replace("/v1", "").rstrip("/")
        urls_to_try.append(f"{ollama_base}/api/tags")

    last_error = None
    for url in urls_to_try:
        try:
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                models = []

                if "data" in data and isinstance(data["data"], list):
                    for m in data["data"]:
                        mid = m.get("id") or m.get("name") or ""
                        if mid:
                            models.append({"id": mid, "name": mid})

                elif "models" in data and isinstance(data["models"], list):
                    for m in data["models"]:
                        mid = m.get("name") or m.get("model") or ""
                        if mid:
                            models.append({"id": mid, "name": mid})

                if models:
                    return {"ok": True, "provider": provider, "models": models}
                last_error = "Nenhum modelo encontrado na resposta"

        except urllib.error.HTTPError as e:
            if e.code == 404 and len(urls_to_try) > 1:
                continue
            last_error = f"HTTP {e.code}: {e.reason}"
        except Exception as e:
            last_error = str(e)
            continue

    return {"ok": False, "provider": provider, "error": last_error or "Provider nao respondeu", "models": []}


def call_provider(provider, model, messages, temperature=0.2):
    provider, base_url, ptype = get_provider_config(provider)

    # CLI-based provider (ollama CLI)
    if ptype == "cli":
        # Combine messages into a single prompt
        parts = []
        for m in messages:
            role = m.get("role", "user")
            content = m.get("content", "")
            if role == "system":
                parts.append(f"System: {content}")
            elif role == "user":
                parts.append(f"User: {content}")
            elif role == "assistant":
                parts.append(f"Assistant: {content}")
        full_prompt = "\n\n".join(parts)
        return call_ollama_cli(model, full_prompt, temperature)

    # HTTP-based provider (LM Studio, Ollama HTTP)
    import urllib.request
    url = f"{base_url}/chat/completions"
    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": 4096,
        "stream": False,
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            content = result["choices"][0]["message"]["content"]
            return {"ok": True, "response": content}
    except urllib.error.HTTPError as e:
        try:
            body = e.read().decode("utf-8", errors="replace")
            detail = json.loads(body).get("error", body)
            if isinstance(detail, dict):
                detail = detail.get("message", str(detail))
        except Exception:
            detail = f"HTTP {e.code}: {e.reason}"
        return {"ok": False, "error": detail}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ─── HTTP Handler ─────────────────────────────────────────

class AIFlowHandler(BaseHTTPRequestHandler):

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        params = parse_qs(parsed.query)

        # API routes
        if path == "/api/projects":
            return ok_response(self, get_projects_data())

        if path == "/api/config":
            return ok_response(self, load_config())

        if path.startswith("/api/project/"):
            proj_path = params.get("path", [None])[0]
            if not proj_path:
                return error_response(self, "parametro 'path' obrigatorio")
            if not is_safe_project_path(proj_path):
                return error_response(self, "Caminho do projeto nao registrado ou invalido", 403)
            info = get_project_info(proj_path)
            return ok_response(self, info)

        if path == "/api/git/status":
            proj_path = params.get("path", [None])[0]
            if not proj_path:
                return error_response(self, "parametro 'path' obrigatorio")
            if not is_safe_project_path(proj_path):
                return error_response(self, "Caminho do projeto nao registrado ou invalido", 403)
            return ok_response(self, git_status(proj_path))

        if path == "/api/git/diff":
            proj_path = params.get("path", [None])[0]
            if not proj_path:
                return error_response(self, "parametro 'path' obrigatorio")
            if not is_safe_project_path(proj_path):
                return error_response(self, "Caminho do projeto nao registrado ou invalido", 403)
            return ok_response(self, {"diff": git_diff(proj_path)})

        if path == "/api/git/log":
            proj_path = params.get("path", [None])[0]
            if not proj_path:
                return error_response(self, "parametro 'path' obrigatorio")
            if not is_safe_project_path(proj_path):
                return error_response(self, "Caminho do projeto nao registrado ou invalido", 403)
            return ok_response(self, git_log(proj_path))

        if path == "/api/code/search":
            proj_path = params.get("path", [None])[0]
            query = params.get("query", [None])[0]
            reindex = params.get("reindex", ["false"])[0].lower() == "true"
            if not query:
                return error_response(self, "parametro 'query' obrigatorio")
            if not proj_path:
                proj_path = str(AI_FLOW_DIR.parent.resolve())
            if not is_safe_project_path(proj_path):
                return error_response(self, "Caminho do projeto nao registrado ou invalido", 403)
            print(f"  /api/code/search query={query!r} path={proj_path!r}")
            try:
                import importlib.util
                indexer_path = AI_FLOW_DIR / "scripts" / "indexer.py"
                if not indexer_path.exists():
                    return error_response(self, "Script indexador nao encontrado em .ai-flow/scripts/indexer.py")
                spec = importlib.util.spec_from_file_location("indexer", str(indexer_path))
                indexer = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(indexer)
                results = indexer.search_context(proj_path, query, force_reindex=reindex)
                return ok_response(self, results)
            except Exception as e:
                return error_response(self, f"Erro ao executar busca: {str(e)}")

        if path == "/api/files":
            proj_path = params.get("path", [None])[0]
            if not proj_path:
                return error_response(self, "parametro 'path' obrigatorio")
            if not is_safe_project_path(proj_path):
                return error_response(self, "Caminho do projeto nao registrado ou invalido", 403)
            files = list_files(proj_path)
            print(f"  /api/files path={proj_path!r} -> {len(files)} entries")
            return ok_response(self, files)

        if path == "/api/file":
            proj_path = params.get("path", [None])[0]
            file_path = params.get("file", [None])[0]
            if not proj_path or not file_path:
                return error_response(self, "parametros 'path' e 'file' obrigatorios")
            if not is_safe_file_path(proj_path, file_path):
                return error_response(self, "Acesso negado: arquivo fora do projeto ou projeto nao registrado", 403)
            content, err = read_file_content(file_path)
            if err:
                return error_response(self, err)
            history = _load_history(proj_path, file_path)
            hcount = len(history["snapshots"]) if history else 0
            return ok_response(self, {
                "content": content,
                "name": Path(file_path).name,
                "has_edits": hcount > 1,
                "history_count": hcount,
            })

        if path == "/api/file/history":
            proj_path = params.get("path", [None])[0]
            file_path = params.get("file", [None])[0]
            if not proj_path or not file_path:
                return error_response(self, "parametros 'path' e 'file' obrigatorios")
            if not is_safe_file_path(proj_path, file_path):
                return error_response(self, "Acesso negado: arquivo fora do projeto ou projeto nao registrado", 403)
            return json_response(self, get_history(proj_path, file_path))

        if path == "/api/file/diff-between":
            proj_path = params.get("path", [None])[0]
            file_path = params.get("file", [None])[0]
            from_id = params.get("from", [None])[0]
            to_id = params.get("to", [None])[0]
            if not proj_path or not file_path or not from_id or not to_id:
                return error_response(self, "parametros 'path','file','from','to' obrigatorios")
            if not is_safe_file_path(proj_path, file_path):
                return error_response(self, "Acesso negado: arquivo fora do projeto ou projeto nao registrado", 403)
            diff, err = get_diff_between(proj_path, file_path, from_id, to_id)
            if err:
                return error_response(self, err)
            return ok_response(self, {"diff": diff})

        if path == "/api/server/check":
            return ok_response(self, {"status": "online", "version": "1.0"})

        if path == "/api/agents":
            return ok_response(self, get_agents_list())

        if path == "/api/agents/load":
            agent_id = params.get("id", [None])[0]
            if not agent_id:
                return error_response(self, "parametro 'id' obrigatorio")
            content, err = get_agent_content(agent_id)
            if err:
                return error_response(self, err)
            return ok_response(self, {"id": agent_id, "content": content})

        # ─── Workflows ───
        if path == "/api/workflows":
            workflows_dir = AI_FLOW_DIR / "workflows"
            workflows_dir.mkdir(parents=True, exist_ok=True)
            files = []
            for f in workflows_dir.glob("*.flow.json"):
                files.append(f.name.replace(".flow.json", ""))
            return ok_response(self, files)

        if path == "/api/workflows/load":
            name = params.get("name", [None])[0]
            if not name:
                return error_response(self, "parametro 'name' obrigatorio")
            # Sanitize name
            name = "".join(c for c in name if c.isalnum() or c in "-_")
            filepath = (AI_FLOW_DIR / "workflows" / f"{name}.flow.json").resolve()
            if not filepath.parent == (AI_FLOW_DIR / "workflows").resolve():
                return error_response(self, "Acesso negado", 403)
            if not filepath.exists():
                return error_response(self, "fluxo nao encontrado")
            try:
                content = json.loads(filepath.read_text(encoding="utf-8"))
                return ok_response(self, content)
            except Exception as e:
                return error_response(self, str(e))

        if path == "/api/providers":
            available = []
            for pid, info in PROVIDER_HELP.items():
                entry = {"id": pid, "label": info["label"], "type": info.get("type", "http")}
                if pid == "ollama_cli":
                    entry["available"] = check_ollama_cli()
                else:
                    entry["available"] = True
                if pid == "ollama":
                    entry["recommended"] = True
                available.append(entry)
            return ok_response(self, available)

        if path == "/api/models":
            prov = params.get("provider", [None])[0]
            result = list_provider_models(prov if prov else None)
            return json_response(self, result)

        if path == "/api/git/context":
            proj_path = params.get("path", [None])[0]
            if not proj_path:
                return error_response(self, "parametro 'path' obrigatorio")
            if not is_safe_project_path(proj_path):
                return error_response(self, "Caminho do projeto nao registrado ou invalido", 403)
            diff = git_diff(proj_path)
            status = git_status(proj_path)
            branch, _, _ = run_cmd(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=proj_path)
            return ok_response(self, {
                "diff": diff,
                "status": status,
                "branch": branch or "?",
                "path": proj_path,
            })

        if path == "/api/terminal/output":
            task_id = params.get("task_id", [None])[0]
            global LATEST_TASK_ID
            
            if not task_id:
                task_id = LATEST_TASK_ID
                
            if not task_id:
                return error_response(self, "Nenhuma tarefa em execucao ou especificada")
                
            if task_id not in TERMINAL_TASKS:
                return error_response(self, f"Tarefa {task_id} nao encontrada", 404)
                
            task = TERMINAL_TASKS[task_id]
            return ok_response(self, {
                "task_id": task_id,
                "command": task["command"],
                "output": task["output"],
                "done": task["done"],
                "exit_code": task["exit_code"]
            })

        # Serve dashboard.html as root
        if path == "/" or path == "":
            dash = AI_FLOW_DIR / "dashboard.html"
            if dash.exists():
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(dash.read_bytes())
                return

        # Serve static files from .ai-flow/
        if not path.startswith("/api/"):
            file_path = AI_FLOW_DIR / path.lstrip("/")
            if file_path.exists() and file_path.is_file():
                ext = file_path.suffix.lower()
                mime = {
                    ".html": "text/html; charset=utf-8",
                    ".css": "text/css; charset=utf-8",
                    ".js": "application/javascript; charset=utf-8",
                    ".json": "application/json; charset=utf-8",
                    ".png": "image/png",
                    ".jpg": "image/jpeg",
                    ".svg": "image/svg+xml",
                    ".md": "text/markdown; charset=utf-8",
                }.get(ext, "application/octet-stream")
                self.send_response(200)
                self.send_header("Content-Type", mime)
                self.end_headers()
                self.wfile.write(file_path.read_bytes())
                return

        # 404
        self.send_response(404)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"404 - Not Found")

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path

        # Read body
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode("utf-8") if length else "{}"
        try:
            data = json.loads(body) if body else {}
        except json.JSONDecodeError:
            data = {}

        # ─── Projects ───
        if path == "/api/projects/add":
            proj_path = data.get("path", "")
            if not proj_path:
                return error_response(self, "campo 'path' obrigatorio")
            p = Path(proj_path)
            if not p.exists() or not p.is_dir():
                return error_response(self, f"O diretorio '{proj_path}' nao existe ou nao e uma pasta valida.", 400)
            resolved = str(p.resolve())
            paths = load_projects()  # loads and syncs
            if resolved not in paths:
                paths.append(resolved)
                write_json(AI_FLOW_DIR / "projects.json", sorted(set(paths)))
            # Regenerate dashboard
            run_regenerate_dashboard()
            return ok_response(self, get_project_info(resolved))

        if path == "/api/projects/remove":
            proj_path = data.get("path", "")
            if not proj_path:
                return error_response(self, "campo 'path' obrigatorio")
            resolved = str(Path(proj_path).resolve())
            paths = load_projects()
            if resolved in paths:
                paths.remove(resolved)
                write_json(AI_FLOW_DIR / "projects.json", sorted(set(paths)))
            # Regenerate dashboard
            run_regenerate_dashboard()
            return ok_response(self)

        if path == "/api/projects/refresh":
            load_projects()  # re-sync
            run_regenerate_dashboard()
            return ok_response(self, get_projects_data())

        # ─── Run scripts ───
        if path == "/api/run/quality-gate":
            proj_path = data.get("path", "")
            if not proj_path:
                return error_response(self, "campo 'path' obrigatorio")
            if not is_safe_project_path(proj_path):
                return error_response(self, "Caminho do projeto nao registrado ou invalido", 403)
            result = run_quality_gate(proj_path)
            return json_response(self, result)

        if path == "/api/run/context-map":
            proj_path = data.get("path", "")
            if not proj_path:
                return error_response(self, "campo 'path' obrigatorio")
            if not is_safe_project_path(proj_path):
                return error_response(self, "Caminho do projeto nao registrado ou invalido", 403)
            result = run_context_map(proj_path)
            return json_response(self, result)

        if path == "/api/run/self-improve":
            proj_path = data.get("path", "")
            if not proj_path:
                return error_response(self, "campo 'path' obrigatorio")
            if not is_safe_project_path(proj_path):
                return error_response(self, "Caminho do projeto nao registrado ou invalido", 403)
            request = data.get("request", "Melhorar AI-Flow com pequenas melhorias locais")
            dry_run = bool(data.get("dry_run", True))
            result = run_self_improve(proj_path, request, dry_run)
            return json_response(self, result)

        # ─── Agent ───
        if path == "/api/agent/call":
            model = data.get("model", "qwen2.5-coder:7b")
            agent = data.get("agent", "")
            system = data.get("system", "")
            user = data.get("user", "")
            temperature = data.get("temperature", 0.2)
            provider = data.get("provider", "")
            messages = data.get("messages", None)
            save_run = data.get("save_run", False)

            if not messages and not user:
                return error_response(self, "campo 'user' ou 'messages' obrigatorio")

            if messages is None:
                messages = []
                if system:
                    messages.append({"role": "system", "content": system})
                messages.append({"role": "user", "content": user})

            if not provider:
                provider, _, _ = get_provider_config(None)

            model = resolve_agent_model(provider, agent, model)

            result = call_provider(provider, model, messages, temperature)

            if not result.get("ok"):
                error_msg = result.get("error", "")
                p = provider or "ollama"
                if p in ("ollama", "ollama_cli"):
                    if "not found" in error_msg.lower() or "404" in error_msg:
                        result["error"] = f"Modelo '{model}' nao encontrado no Ollama. Rode: ollama pull {model}"
                    elif "connection refused" in error_msg.lower() or "failed to connect" in error_msg.lower():
                        result["error"] = f"Ollama nao esta rodando. Execute 'ollama serve' ou abra o aplicativo Ollama."
                    elif "command not found" in error_msg.lower():
                        result["error"] = "Ollama CLI nao encontrado. Instale o Ollama em https://ollama.ai"
            else:
                if save_run and agent:
                    try:
                        current_task_path = AI_FLOW_DIR / "artifacts" / "current-task.json"
                        task_dir = None
                        if current_task_path.exists():
                            task_data = json.loads(current_task_path.read_text(encoding="utf-8"))
                            path_str = task_data.get("path")
                            if path_str:
                                p = Path(path_str)
                                if p.exists() and p.is_dir():
                                    task_dir = p
                        
                        run_id = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                        if task_dir:
                            run_subdir = task_dir / "runs" / f"{run_id}-{agent}"
                        else:
                            run_subdir = (AI_FLOW_DIR / "artifacts" / "runs" / f"{run_id}-{agent}")
                            
                        run_subdir.mkdir(parents=True, exist_ok=True)
                        
                        # Write files
                        (run_subdir / "response.md").write_text(result.get("response", ""), encoding="utf-8")
                        (run_subdir / "prompt.md").write_text(
                            f"# Agent: {agent}\n\n## Messages\n\n" + json.dumps(messages, indent=2, ensure_ascii=False),
                            encoding="utf-8"
                        )
                        
                        # Save metadata
                        meta = {
                            "agent_id": agent,
                            "model": model,
                            "provider": provider,
                            "created_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            "git_context_used": False,
                        }
                        (run_subdir / "metadata.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
                    except Exception as e:
                        print(f"Erro ao salvar run do canvas: {e}")

            return json_response(self, result)

        # ─── Git commit ───
        if path == "/api/git/commit":
            proj_path = data.get("path", "")
            message = data.get("message", "")
            if not proj_path or not message:
                return error_response(self, "campos 'path' e 'message' obrigatorios")
            if not is_safe_project_path(proj_path):
                return error_response(self, "Caminho do projeto nao registrado ou invalido", 403)
            result = git_commit(proj_path, message)
            return json_response(self, result)

        # ─── File write ───
        if path == "/api/file/write":
            file_path = data.get("file", "")
            content = data.get("content", "")
            if not file_path:
                return error_response(self, "campo 'file' obrigatorio")
            proj_path = find_project_path(file_path)
            if not is_safe_file_path(proj_path, file_path):
                return error_response(self, "Acesso negado: arquivo nao pertence a um projeto registrado", 403)
            ok, err = write_file_content(file_path, content)
            if err:
                return error_response(self, err)
            return ok_response(self, {"path": file_path})

        # ─── File edit (with snapshot + quality gate) ───
        if path == "/api/file/edit":
            proj_path = data.get("path", "")
            file_path = data.get("file", "")
            content = data.get("content", "")
            description = data.get("description", "Edicao via dashboard")
            agent = data.get("agent", "manual")
            if not proj_path or not file_path:
                return error_response(self, "campos 'path' e 'file' obrigatorios")
            if not is_safe_file_path(proj_path, file_path):
                return error_response(self, "Acesso negado: arquivo fora do projeto ou projeto nao registrado", 403)
            # Read current content before edit
            old_content, err = read_file_content(file_path)
            if err:
                if "Arquivo nao encontrado" in err:
                    old_content = ""
                else:
                    return error_response(self, f"Erro ao ler arquivo: {err}")
            # Snapshot old content
            s1, err = take_snapshot(proj_path, file_path, old_content, agent, f"Antes: {description}")
            if err:
                return error_response(self, f"Erro ao salvar snapshot: {err}")
            # Write new content
            ok, err = write_file_content(file_path, content)
            if err:
                return error_response(self, f"Erro ao escrever arquivo: {err}")
            # Snapshot new content
            s2, err = take_snapshot(proj_path, file_path, content, agent, description)
            if err:
                return error_response(self, f"Erro ao salvar snapshot: {err}")
            diff = _compute_diff(old_content, content,
                                 fromfile=f"a/{Path(file_path).name}",
                                 tofile=f"b/{Path(file_path).name}")
            threading.Thread(target=_run_qg_async, args=(proj_path,), daemon=True).start()
            return ok_response(self, {
                "snapshot_id": s2["id"],
                "diff": diff,
                "undo_snapshot_id": s1["id"],
            })

        # ─── File patch (with search-and-replace, snapshot + quality gate) ───
        if path == "/api/file/patch":
            proj_path = data.get("path", "")
            file_path = data.get("file", "")
            search_text = data.get("search", "")
            replace_text = data.get("replace", "")
            description = data.get("description", "Patch via dashboard")
            agent = data.get("agent", "composer")
            if not proj_path or not file_path:
                return error_response(self, "campos 'path' e 'file' obrigatorios")
            
            # Resolve path: if relative, make absolute using project path
            resolved_file_path = file_path
            if not os.path.isabs(file_path):
                resolved_file_path = str(Path(proj_path) / file_path)
                
            if not is_safe_file_path(proj_path, resolved_file_path):
                return error_response(self, "Acesso negado: arquivo fora do projeto ou projeto nao registrado", 403)

            # Read current content before edit
            old_content, err = read_file_content(resolved_file_path)
            if err:
                if "Arquivo nao encontrado" in err:
                    old_content = ""
                else:
                    return error_response(self, f"Erro ao ler arquivo: {err}")
            
            # Apply search and replace patch
            new_content, err = apply_search_replace_patch(old_content, search_text, replace_text)
            if err:
                return error_response(self, f"Erro ao aplicar patch: {err}")
                
            # Snapshot old content
            s1, err = take_snapshot(proj_path, resolved_file_path, old_content, agent, f"Antes: {description}")
            if err:
                return error_response(self, f"Erro ao salvar snapshot: {err}")
            # Write new content
            ok, err = write_file_content(resolved_file_path, new_content)
            if err:
                return error_response(self, f"Erro ao escrever arquivo: {err}")
            # Snapshot new content
            s2, err = take_snapshot(proj_path, resolved_file_path, new_content, agent, description)
            if err:
                return error_response(self, f"Erro ao salvar snapshot: {err}")
            diff = _compute_diff(old_content, new_content,
                                 fromfile=f"a/{Path(resolved_file_path).name}",
                                 tofile=f"b/{Path(resolved_file_path).name}")
            threading.Thread(target=_run_qg_async, args=(proj_path,), daemon=True).start()
            return ok_response(self, {
                "snapshot_id": s2["id"],
                "diff": diff,
                "undo_snapshot_id": s1["id"],
                "file": resolved_file_path,
            })

        # ─── File undo ───
        if path == "/api/file/undo":
            proj_path = data.get("path", "")
            file_path = data.get("file", "")
            if not proj_path or not file_path:
                return error_response(self, "campos 'path' e 'file' obrigatorios")
            if not is_safe_file_path(proj_path, file_path):
                return error_response(self, "Acesso negado: arquivo fora do projeto ou projeto nao registrado", 403)
            history = _load_history(proj_path, file_path)
            if not history or not history.get("current"):
                return error_response(self, "Nenhum historico para desfazer")
            cid = history["current"]
            cidx = -1
            for i, s in enumerate(history["snapshots"]):
                if s["id"] == cid: cidx = i; break
            if cidx <= 0:
                return error_response(self, "Nao ha versoes anteriores para desfazer")
            prev_id = history["snapshots"][cidx - 1]["id"]
            restored, err = restore_snapshot(proj_path, file_path, prev_id)
            if err:
                return error_response(self, err)
            diff = _compute_diff(history["snapshots"][cidx]["content"], restored["content"],
                                 fromfile=f"a/{Path(file_path).name}",
                                 tofile=f"b/{Path(file_path).name}")
            return ok_response(self, {
                "snapshot_id": prev_id, "diff": diff,
                "description": restored["description"], "timestamp": restored["timestamp"],
            })

        # ─── File redo ───
        if path == "/api/file/redo":
            proj_path = data.get("path", "")
            file_path = data.get("file", "")
            if not proj_path or not file_path:
                return error_response(self, "campos 'path' e 'file' obrigatorios")
            if not is_safe_file_path(proj_path, file_path):
                return error_response(self, "Acesso negado: arquivo fora do projeto ou projeto nao registrado", 403)
            history = _load_history(proj_path, file_path)
            if not history or not history.get("current"):
                return error_response(self, "Nenhum historico para refazer")
            cid = history["current"]
            cidx = -1
            for i, s in enumerate(history["snapshots"]):
                if s["id"] == cid: cidx = i; break
            if cidx < 0 or cidx >= len(history["snapshots"]) - 1:
                return error_response(self, "Nao ha versoes posteriores para refazer")
            next_id = history["snapshots"][cidx + 1]["id"]
            restored, err = restore_snapshot(proj_path, file_path, next_id)
            if err:
                return error_response(self, err)
            diff = _compute_diff(history["snapshots"][cidx]["content"], restored["content"],
                                 fromfile=f"a/{Path(file_path).name}",
                                 tofile=f"b/{Path(file_path).name}")
            return ok_response(self, {
                "snapshot_id": next_id, "diff": diff,
                "description": restored["description"], "timestamp": restored["timestamp"],
            })

        # ─── File restore ───
        if path == "/api/file/restore":
            proj_path = data.get("path", "")
            file_path = data.get("file", "")
            snapshot_id = data.get("snapshot_id", "")
            if not proj_path or not file_path or not snapshot_id:
                return error_response(self, "campos 'path', 'file' e 'snapshot_id' obrigatorios")
            if not is_safe_file_path(proj_path, file_path):
                return error_response(self, "Acesso negado: arquivo fora do projeto ou projeto nao registrado", 403)
            restored, err = restore_snapshot(proj_path, file_path, snapshot_id)
            if err:
                return error_response(self, err)
            return ok_response(self, {
                "snapshot_id": snapshot_id,
                "description": restored["description"],
                "timestamp": restored["timestamp"],
            })

        # ─── Workflows ───
        if path == "/api/workflows/save":
            name = data.get("name", "")
            flow = data.get("flow", {})
            if not name:
                return error_response(self, "campo 'name' obrigatorio")
            # Sanitize name
            name = "".join(c for c in name if c.isalnum() or c in "-_")
            workflows_dir = (AI_FLOW_DIR / "workflows").resolve()
            filepath = (workflows_dir / f"{name}.flow.json").resolve()
            if not filepath.parent == workflows_dir:
                return error_response(self, "Acesso negado", 403)
            try:
                filepath.write_text(json.dumps(flow, indent=2, ensure_ascii=False), encoding="utf-8")
                return ok_response(self, {"name": name})
            except Exception as e:
                return error_response(self, str(e))

        # ─── Config ───
        if path == "/api/config/save":
            write_json(AI_FLOW_DIR / "config.json", data)
            return ok_response(self)

        # ─── File edit patch ───
        if path == "/api/file/edit-patch":
            file_path = data.get("path", "")
            target_content = data.get("target_content", "")
            replacement_content = data.get("replacement_content", "")
            description = data.get("description", "Edicao via patch")
            agent = data.get("agent", "composer")

            if not file_path:
                return error_response(self, "campo 'path' obrigatorio")

            proj_path = find_project_path(file_path)
            if not is_safe_file_path(proj_path, file_path):
                return error_response(self, "Acesso negado: arquivo nao pertence a um projeto registrado", 403)

            old_content, err = read_file_content(file_path)
            if err:
                return error_response(self, f"Erro ao ler arquivo: {err}")

            if target_content not in old_content:
                return error_response(self, "Conteudo original (target_content) nao encontrado no arquivo para correspondencia exata.")

            s1, err = take_snapshot(proj_path, file_path, old_content, agent, f"Antes: {description}")
            if err:
                return error_response(self, f"Erro ao salvar snapshot anterior: {err}")

            new_content = old_content.replace(target_content, replacement_content, 1)

            ok, err = write_file_content(file_path, new_content)
            if err:
                return error_response(self, f"Erro ao escrever arquivo: {err}")

            s2, err = take_snapshot(proj_path, file_path, new_content, agent, description)
            if err:
                return error_response(self, f"Erro ao salvar snapshot posterior: {err}")

            diff = _compute_diff(old_content, new_content,
                                 fromfile=f"a/{Path(file_path).name}",
                                 tofile=f"b/{Path(file_path).name}")

            threading.Thread(target=_run_qg_async, args=(proj_path,), daemon=True).start()

            return ok_response(self, {
                "snapshot_id": s2["id"],
                "diff": diff,
                "undo_snapshot_id": s1["id"],
            })

        # ─── Terminal run ───
        if path == "/api/terminal/run":
            command = data.get("command", "")
            cwd = data.get("cwd", None)

            if not command:
                return error_response(self, "campo 'command' obrigatorio")

            if is_dangerous_command(command):
                return error_response(self, "Comando bloqueado por seguranca (del, rm -rf, format, etc.)", 403)

            task_id = f"task_{uuid.uuid4().hex[:12]}"
            
            try:
                process = subprocess.Popen(
                    command,
                    shell=True,
                    cwd=cwd,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    bufsize=1
                )
            except Exception as e:
                return error_response(self, f"Falha ao iniciar processo: {e}")

            # Prune old tasks if history is large (e.g. limit to 100 entries)
            if len(TERMINAL_TASKS) > 100:
                try:
                    sorted_keys = sorted(TERMINAL_TASKS.keys(), key=lambda k: TERMINAL_TASKS[k].get("timestamp", ""))
                    for old_key in sorted_keys[:-100]:
                        TERMINAL_TASKS.pop(old_key, None)
                except Exception:
                    pass

            TERMINAL_TASKS[task_id] = {
                "command": command,
                "cwd": cwd,
                "process": process,
                "output": "",
                "done": False,
                "exit_code": None,
                "timestamp": datetime.datetime.now().isoformat()
            }
            
            global LATEST_TASK_ID
            LATEST_TASK_ID = task_id

            def read_output_thread(tid, proc):
                try:
                    for line in iter(proc.stdout.readline, ''):
                        if tid in TERMINAL_TASKS:
                            TERMINAL_TASKS[tid]["output"] += line
                        else:
                            break
                except Exception as e:
                    if tid in TERMINAL_TASKS:
                        TERMINAL_TASKS[tid]["output"] += f"\n[Erro na leitura da saida: {e}]\n"
                finally:
                    proc.stdout.close()
                    proc.wait()
                    if tid in TERMINAL_TASKS:
                        TERMINAL_TASKS[tid]["done"] = True
                        TERMINAL_TASKS[tid]["exit_code"] = proc.returncode

            threading.Thread(target=read_output_thread, args=(task_id, process), daemon=True).start()

            return ok_response(self, {"task_id": task_id})

        # ─── Terminal kill ───
        if path == "/api/terminal/kill":
            task_id = data.get("task_id", "")

            if not task_id:
                task_id = LATEST_TASK_ID
                
            if not task_id:
                return error_response(self, "Nenhuma tarefa especificada ou em execucao")
                
            if task_id not in TERMINAL_TASKS:
                return error_response(self, f"Tarefa {task_id} nao encontrada", 404)
                
            task = TERMINAL_TASKS[task_id]
            if task["done"]:
                return ok_response(self, {"message": "Tarefa ja concluida"})
                
            try:
                proc = task["process"]
                proc.terminate()
                for _ in range(10):
                    if proc.poll() is not None:
                        break
                    time.sleep(0.1)
                else:
                    proc.kill()
                    proc.wait()
                
                task["done"] = True
                task["exit_code"] = proc.returncode
                return ok_response(self, {"message": f"Processo {task_id} terminado"})
            except Exception as e:
                return error_response(self, f"Erro ao terminar processo: {e}")

        # ─── Terminal input ───
        if path == "/api/terminal/input":
            task_id = data.get("task_id", "")
            text = data.get("text", "")

            if not task_id:
                task_id = LATEST_TASK_ID
                
            if not task_id:
                return error_response(self, "Nenhuma tarefa especificada ou em execucao")
                
            if task_id not in TERMINAL_TASKS:
                return error_response(self, f"Tarefa {task_id} nao encontrada", 404)
                
            task = TERMINAL_TASKS[task_id]
            if task["done"]:
                return error_response(self, "Tarefa ja concluida, nao e possivel enviar entrada")
                
            try:
                proc = task["process"]
                if proc.stdin:
                    proc.stdin.write(text + "\n")
                    proc.stdin.flush()
                    return ok_response(self, {"message": "Entrada enviada"})
                else:
                    return error_response(self, "Canal stdin do processo nao esta disponivel")
            except Exception as e:
                return error_response(self, f"Erro ao enviar entrada para o processo: {e}")

        # ─── Agent compose ───
        if path == "/api/agent/compose":
            messages = data.get("messages", None)
            instructions = data.get("instructions", "")
            model = data.get("model", "")
            provider = data.get("provider", "")
            temperature = data.get("temperature", None)

            if not messages:
                messages = []

            if instructions:
                messages.append({"role": "user", "content": instructions})

            if not messages:
                return error_response(self, "Nenhuma mensagem ou instrucao fornecida")

            provider, base_url, ptype = get_provider_config(provider if provider else None)

            model_planning = model if model else resolve_model(provider, "model_for_planning", "phi4-mini:3.8b")
            model_coding = model if model else resolve_model(provider, "model_for_coding", "qwen2.5-coder:7b")

            planner_prompt, err = get_agent_content("planner")
            if err or not planner_prompt:
                planner_prompt = (
                    "Você é o Planejador do Composer. Seu papel é analisar o pedido do usuário e o histórico de conversas "
                    "para propor um plano detalhado de alterações, identificando arquivos afetados e passos de implementação."
                )

            planning_messages = [{"role": "system", "content": planner_prompt}]
            for m in messages:
                if m.get("role") != "system":
                    planning_messages.append(m)

            temp_planning = temperature if temperature is not None else 0.3
            plan_res = call_provider(provider, model_planning, planning_messages, temperature=temp_planning)
            if not plan_res.get("ok"):
                return error_response(self, f"Erro na etapa de planejamento com {model_planning}: {plan_res.get('error')}")

            plan_text = plan_res.get("response", "")

            coder_prompt, err = get_agent_content("coder")
            if err or not coder_prompt:
                coder_prompt = (
                    "Você é o Codificador do Composer. Seu papel é gerar as alterações de código recomendadas "
                    "seguindo o plano estabelecido."
                )

            coder_system_prompt = (
                f"{coder_prompt}\n\n"
                "INSTRUÇÕES CRÍTICAS DE FORMATAÇÃO DE CODE DIFFS:\n"
                "Para cada arquivo que deseja alterar, você deve propor as mudanças EXATAMENTE usando tags XML estruturadas:\n"
                "<patch file=\"caminho/do/arquivo\">\n"
                "<search>\n"
                "[bloco de código original exato no arquivo, mantendo espaçamento e quebras de linha]\n"
                "</search>\n"
                "<replace>\n"
                "[bloco de código substituto com as alterações aplicadas]\n"
                "</replace>\n"
                "</patch>\n\n"
                "Você pode especificar múltiplos blocos de patch para um ou mais arquivos. Todos os patches devem ser válidos. "
                "Explique brevemente as alterações feitas antes ou após os blocos XML."
            )

            coder_messages = [{"role": "system", "content": coder_system_prompt}]
            for m in messages:
                if m.get("role") != "system":
                    coder_messages.append(m)
            coder_messages.append({
                "role": "system",
                "content": f"Aqui está o plano de implementação que você deve seguir e codificar:\n\n{plan_text}"
            })

            temp_coding = temperature if temperature is not None else 0.2
            code_res = call_provider(provider, model_coding, coder_messages, temperature=temp_coding)
            if not code_res.get("ok"):
                return error_response(self, f"Erro na etapa de codificação com {model_coding}: {code_res.get('error')}")

            code_text = code_res.get("response", "")

            patches = parse_patches(code_text)

            return json_response(self, {
                "ok": True,
                "plan": plan_text,
                "response": code_text,
                "patches": patches
            })

        # ─── Agent apply patches ───
        if path == "/api/agent/apply-patches":
            patches = data.get("patches", None)
            agent = data.get("agent", "composer")
            description = data.get("description", "Aplicacao automatica de patches do Composer")

            if not isinstance(patches, list):
                return error_response(self, "campo 'patches' deve ser uma lista")

            results = []
            proj_paths_to_qg = set()

            for idx, patch in enumerate(patches):
                file_path = patch.get("file", "")
                search_content = patch.get("search", "")
                replace_content = patch.get("replace", "")

                if not file_path:
                    results.append({
                        "index": idx,
                        "file": file_path,
                        "ok": False,
                        "error": "Caminho do arquivo nao especificado no patch"
                    })
                    continue

                old_content, err = read_file_content(file_path)
                if err:
                    results.append({
                        "index": idx,
                        "file": file_path,
                        "ok": False,
                        "error": f"Erro ao ler arquivo: {err}"
                    })
                    continue

                if search_content not in old_content:
                    results.append({
                        "index": idx,
                        "file": file_path,
                        "ok": False,
                        "error": "Conteudo de busca nao encontrado no arquivo para correspondencia exata"
                    })
                    continue

                proj_path = find_project_path(file_path)
                if not is_safe_file_path(proj_path, file_path):
                    results.append({
                        "index": idx,
                        "file": file_path,
                        "ok": False,
                        "error": "Acesso negado: arquivo nao pertence a um projeto registrado"
                    })
                    continue

                proj_paths_to_qg.add(proj_path)

                s1, err = take_snapshot(proj_path, file_path, old_content, agent, f"Antes: {description}")
                if err:
                    results.append({
                        "index": idx,
                        "file": file_path,
                        "ok": False,
                        "error": f"Erro ao salvar snapshot anterior: {err}"
                    })
                    continue

                new_content = old_content.replace(search_content, replace_content, 1)

                ok, err = write_file_content(file_path, new_content)
                if err:
                    results.append({
                        "index": idx,
                        "file": file_path,
                        "ok": False,
                        "error": f"Erro ao escrever novo conteudo: {err}"
                    })
                    continue

                s2, err = take_snapshot(proj_path, file_path, new_content, agent, description)
                
                results.append({
                    "index": idx,
                    "file": file_path,
                    "ok": True,
                    "snapshot_id": s2["id"] if s2 else None,
                    "undo_snapshot_id": s1["id"] if s1 else None
                })

            for p_path in proj_paths_to_qg:
                threading.Thread(target=_run_qg_async, args=(p_path,), daemon=True).start()

            return ok_response(self, {
                "results": results,
                "all_applied": all(r["ok"] for r in results)
            })

        return error_response(self, "rota nao encontrada", 404)

    def log_message(self, format, *args):
        # Silencia logs padrao
        msg = args[0] if args else ""
        if "/api/" in msg or "POST" in msg or "GET / " in msg:
            print(f"  {msg}")
        elif "GET /dashboard.html" in msg or "GET /favicon" in msg:
            pass
        else:
            print(f"  {msg}")


# ─── Main ─────────────────────────────────────────────────

def open_browser():
    time.sleep(0.5)
    url = f"http://localhost:{SERVER_PORT}"
    print(f"\n  Abrindo {url} no navegador...")
    webbrowser.open(url)


def main():
    port = int(os.environ.get("AI_FLOW_PORT", SERVER_PORT))
    server = HTTPServer(("0.0.0.0", port), AIFlowHandler)

    print("+===============================================+")
    print("|        AI-Flow Server                         |")
    print("+===============================================+")
    print(f"|  Local:  http://localhost:{port:<38} |")
    print("|                                               |")
    print("|  Para desligar: Ctrl+C                        |")
    print("+===============================================+")
    print()
    print("  Endpoints disponiveis:")
    print("  GET  /api/projects              - Lista projetos")
    print("  POST /api/projects/add          - Adicionar projeto")
    print("  POST /api/projects/remove       - Remover projeto")
    print("  POST /api/projects/refresh      - Recarregar projetos")
    print("  GET  /api/code/search?query=... - Busca de contexto (TF-IDF)")
    print("  GET  /api/git/status?path=...   - Git status")
    print("  GET  /api/git/diff?path=...     - Git diff")
    print("  GET  /api/git/log?path=...      - Git log")
    print("  GET  /api/git/context?path=...  - Git diff+status+branch")
    print("  POST /api/run/quality-gate      - Rodar quality gate")
    print("  POST /api/run/context-map       - Rodar context map")
    print("  POST /api/run/self-improve      - Rodar auto aprimoramento")
    print("  GET  /api/agents                - Listar agentes")
    print("  GET  /api/agents/load?id=...    - Carregar prompt do agente")
    print("  GET  /api/providers             - Listar providers disponiveis")
    print("  GET  /api/models?provider=...   - Listar modelos do provider")
    print("  POST /api/agent/call            - Chamar LLM (provider+messages)")
    print()

    threading.Thread(target=open_browser, daemon=True).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  Servidor encerrado.")
        server.server_close()


if __name__ == "__main__":
    main()
