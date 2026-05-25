"""
.ai-flow/scripts/generate-context-map.py

Gera um mapa visual interativo do projeto: estrutura de diretorios,
status git, arquivos alterados e quadro de tarefas.

Uso:
  python .ai-flow/scripts/generate-context-map.py

Saida: .ai-flow/reports/project-context.html
"""

import subprocess
import datetime
import html
import json
import os
import re
import sys
from pathlib import Path

REPORTS_DIR = Path(__file__).resolve().parent.parent / "reports"
OUTPUT_FILE = REPORTS_DIR / "project-context.html"
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
IGNORE_DIRS = {"node_modules", ".git", "__pycache__", ".next", "dist", "build",
               ".cache", "coverage", ".nyc_output", "target", "venv", ".venv"}
IGNORE_EXT = {".pyc", ".pyo", ".exe", ".dll", ".so", ".dylib", ".bin",
              ".jpg", ".png", ".gif", ".ico", ".svg", ".woff", ".woff2"}
MAX_TREE_DEPTH = 6
MAX_DIR_ENTRIES = 50


def run_cmd(cmd, cwd=None):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, check=False,
                           encoding="utf-8", errors="replace",
                           cwd=str(cwd) if cwd else str(REPO_ROOT))
        return r.stdout.strip(), r.stderr.strip(), r.returncode
    except FileNotFoundError:
        return "", "command not found", -1


def get_project_root():
    o, _, _ = run_cmd(["git", "rev-parse", "--show-toplevel"])
    return o or str(REPO_ROOT)


def get_git_branch():
    o, _, _ = run_cmd(["git", "rev-parse", "--abbrev-ref", "HEAD"])
    return o or "?"


def get_git_log(limit=10):
    o, _, _ = run_cmd(["git", "log", f"--max-count={limit}",
                       "--pretty=format:%h|%an|%ar|%s"])
    commits = []
    for line in o.split("\n") if o else []:
        parts = line.split("|", 3)
        if len(parts) == 4:
            commits.append({"hash": parts[0], "author": parts[1],
                            "date": parts[2], "message": parts[3]})
    return commits


def get_git_diff_files():
    files = set()
    for cmd in [["git", "diff", "--name-only"],
                ["git", "diff", "--cached", "--name-only"]]:
        o, _, _ = run_cmd(cmd)
        for f in o.split("\n"):
            if f.strip():
                files.add(f.strip())
    return sorted(files)


def get_git_status():
    o, _, _ = run_cmd(["git", "status", "--porcelain"])
    entries = []
    for line in o.split("\n") if o else []:
        if line.strip():
            code = line[:2].strip()
            path = line[3:].strip()
            entries.append({"code": code, "path": path})
    return entries


def build_tree(root, depth=0):
    """Retorna lista de dicts representando a arvore."""
    if depth > MAX_TREE_DEPTH:
        return []
    root_path = Path(root)
    lines = []
    try:
        entries = sorted(
            [e for e in root_path.iterdir()
             if e.name not in IGNORE_DIRS
             and e.suffix not in IGNORE_EXT
             and (not e.name.startswith(".") or e.name in (".env.example", ".gitignore", ".eslintrc"))],
            key=lambda x: (not x.is_dir(), x.name.lower())
        )
    except PermissionError:
        return []
    if len(entries) > MAX_DIR_ENTRIES:
        entries = entries[:MAX_DIR_ENTRIES]
        remaining = len([e for e in root_path.iterdir() if e.name not in IGNORE_DIRS and e.suffix not in IGNORE_EXT])
        if remaining > MAX_DIR_ENTRIES:
            lines.append({"name": f"... (+{remaining - MAX_DIR_ENTRIES} ocultos)", "path": "",
                          "type": "truncated", "size": 0, "depth": depth})
    for entry in entries:
        try:
            size = entry.stat().st_size if entry.is_file() else 0
        except OSError:
            size = 0
        ext = entry.suffix.lower() if entry.is_file() else "dir"
        rel = str(entry.relative_to(root_path)) if entry.is_file() else ""
        lines.append({"name": entry.name, "path": rel, "type": ext, "size": size, "depth": depth})
        if entry.is_dir():
            lines.extend(build_tree(entry, depth + 1))
    return lines


def get_file_icon(ext):
    icons = {"dir": "📁", ".ts": "🔷", ".tsx": "⚛️", ".js": "🟨", ".jsx": "⚛️",
             ".json": "📋", ".css": "🎨", ".scss": "🎨", ".html": "🌐",
             ".md": "📝", ".yml": "⚙️", ".yaml": "⚙️", ".py": "🐍",
             ".env.example": "🔐", ".gitignore": "🙈"}
    return icons.get(ext, "📄")


def format_size(size):
    if size < 1024:
        return f"{size} B"
    elif size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size / (1024 * 1024):.1f} MB"


def should_include_inventory_file(path):
    parts = [part.lower() for part in Path(path).parts]
    if any(part in IGNORE_DIRS for part in parts[:-1]):
        return False
    suffix = Path(path).suffix.lower()
    if suffix in IGNORE_EXT:
        return False
    return True


def collect_repository_files(root):
    root_path = Path(root)
    files = []
    try:
        for path in root_path.rglob("*"):
            if path.is_file():
                rel = path.relative_to(root_path)
                rel_text = str(rel).replace("\\", "/")
                if should_include_inventory_file(rel):
                    files.append(rel_text)
    except PermissionError:
        return []
    return sorted(files)


def is_manifest_file(path):
    name = Path(path).name.lower()
    suffix = Path(path).suffix.lower()
    return name in {
        "package.json",
        "package-lock.json",
        "pnpm-lock.yaml",
        "yarn.lock",
        "requirements.txt",
        "pyproject.toml",
        "poetry.lock",
        "setup.py",
        "pom.xml",
        "build.gradle",
        "build.gradle.kts",
        "cargo.toml",
        "go.mod",
    } or suffix in {".csproj", ".fsproj", ".sln"}


def is_script_file(path):
    lowered = path.lower().replace("\\", "/")
    suffix = Path(path).suffix.lower()
    return (
        "/scripts/" in lowered
        or lowered.startswith("scripts/")
        or lowered.startswith(".ai-flow/scripts/")
        or suffix in {".ps1", ".sh", ".bat", ".cmd"}
    )


def is_test_file(path):
    name = Path(path).name.lower()
    lowered = path.lower().replace("\\", "/")
    return (
        name.startswith("test_")
        or name.endswith("_test.py")
        or name.endswith(".test.js")
        or name.endswith(".test.jsx")
        or name.endswith(".test.ts")
        or name.endswith(".test.tsx")
        or name.endswith(".spec.js")
        or name.endswith(".spec.jsx")
        or name.endswith(".spec.ts")
        or name.endswith(".spec.tsx")
        or "/tests/" in lowered
        or "/__tests__/" in lowered
    )


def is_ci_file(path):
    lowered = path.lower().replace("\\", "/")
    return (
        lowered.startswith(".github/workflows/")
        or lowered.startswith(".gitlab-ci")
        or lowered.endswith("azure-pipelines.yml")
        or lowered.endswith(".circleci/config.yml")
        or lowered.endswith("bitbucket-pipelines.yml")
        or lowered.endswith(".drone.yml")
    )


def is_docker_file(path):
    lowered = path.lower().replace("\\", "/")
    name = Path(path).name.lower()
    return (
        name == "dockerfile"
        or name.startswith("dockerfile.")
        or "docker-compose" in name
        or "/docker/" in lowered
        or lowered.startswith("docker/")
    )


def collect_package_scripts(root):
    package_json = Path(root) / "package.json"
    if not package_json.exists():
        return []
    try:
        data = json.loads(package_json.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    scripts = data.get("scripts", {})
    if not isinstance(scripts, dict):
        return []
    return [f"{name}: {cmd}" for name, cmd in sorted(scripts.items())]


def detect_probable_stacks(files, root):
    stacks = []

    def add_stack(name, evidence):
        if evidence:
            stacks.append({"name": name, "evidence": evidence[:4], "confidence": "alta" if len(evidence) > 1 else "media"})

    python_evidence = []
    if any(Path(f).name in {"pyproject.toml", "requirements.txt", "setup.py", "poetry.lock"} for f in files):
        python_evidence.append("manifesto Python detectado")
    if any(f.endswith(".py") for f in files):
        python_evidence.append("arquivos .py encontrados")
    add_stack("Python", python_evidence)

    node_evidence = []
    if any(Path(f).name == "package.json" for f in files):
        node_evidence.append("package.json presente")
    if any(f.endswith((".ts", ".tsx", ".js", ".jsx")) for f in files):
        node_evidence.append("arquivos JavaScript/TypeScript encontrados")
    add_stack("Node.js / TypeScript", node_evidence)

    web_evidence = []
    if any(f.endswith((".html", ".css", ".scss")) for f in files):
        web_evidence.append("artefatos HTML/CSS presentes")
    add_stack("Web / Dashboard", web_evidence)

    java_evidence = []
    if any(Path(f).name in {"pom.xml", "build.gradle", "build.gradle.kts"} for f in files):
        java_evidence.append("manifesto Java detectado")
    if any(f.endswith(".java") for f in files):
        java_evidence.append("arquivos .java encontrados")
    add_stack("Java / JVM", java_evidence)

    go_evidence = []
    if any(Path(f).name == "go.mod" for f in files):
        go_evidence.append("go.mod presente")
    if any(f.endswith(".go") for f in files):
        go_evidence.append("arquivos .go encontrados")
    add_stack("Go", go_evidence)

    rust_evidence = []
    if any(Path(f).name == "Cargo.toml" for f in files):
        rust_evidence.append("Cargo.toml presente")
    if any(f.endswith(".rs") for f in files):
        rust_evidence.append("arquivos .rs encontrados")
    add_stack("Rust", rust_evidence)

    dotnet_evidence = []
    if any(Path(f).suffix.lower() in {".csproj", ".fsproj", ".sln"} for f in files):
        dotnet_evidence.append("projeto .NET detectado")
    if any(f.endswith(".cs") for f in files):
        dotnet_evidence.append("arquivos .cs encontrados")
    add_stack(".NET", dotnet_evidence)

    if not stacks:
        stacks.append({"name": "Nao identificado", "evidence": ["Sem manifestos ou extensoes conclusivas"], "confidence": "baixa"})

    return stacks


def collect_inventory_risks(repo_files, modified_files, porcelain, manifests, tests, ci_files, docker_files):
    risks = []
    code_files = [f for f in repo_files if Path(f).suffix.lower() in {
        ".py", ".js", ".jsx", ".ts", ".tsx", ".java", ".go", ".rb", ".php", ".rs", ".c", ".cc", ".cpp", ".cs"
    }]
    if code_files and not tests:
        risks.append({"severity": "warning", "title": "Sem testes detectados", "details": "Existem arquivos de codigo, mas nenhum teste foi identificado no inventario."})
    if code_files and not ci_files:
        risks.append({"severity": "info", "title": "CI nao detectada", "details": "Nao foram encontrados arquivos de pipeline em .github/workflows, GitLab ou Azure Pipelines."})
    if code_files and not docker_files:
        risks.append({"severity": "info", "title": "Docker nao detectado", "details": "Nenhum Dockerfile ou docker-compose foi encontrado."})
    if not manifests and code_files:
        risks.append({"severity": "warning", "title": "Sem manifestos principais", "details": "O inventario nao encontrou manifestos claros para a stack principal."})
    sensitive_hits = []
    for path in repo_files:
        lowered = path.lower()
        if lowered.endswith(".env") or lowered.startswith(".env") or "/secrets/" in lowered or lowered.startswith("secrets/"):
            if not lowered.endswith(".example") and not lowered.endswith(".sample"):
                sensitive_hits.append(path)
    if sensitive_hits:
        risks.append({"severity": "critical", "title": "Arquivos sensiveis no repositorio", "details": ", ".join(sensitive_hits[:5])})
    if len(modified_files) > 20:
        risks.append({"severity": "info", "title": "Muitas alteracoes em aberto", "details": f"{len(modified_files)} arquivos modificados podem indicar um lote grande demais para revisao rapida."})
    if porcelain and len(porcelain) > 10:
        risks.append({"severity": "info", "title": "Working tree movimentado", "details": f"{len(porcelain)} entradas no status Git merecem uma revisao mais cuidadosa."})
    return risks


def build_repository_inventory(root, tree_data, modified_files, porcelain):
    repo_files = collect_repository_files(root)
    manifests = [f for f in repo_files if is_manifest_file(f)]
    scripts = [f for f in repo_files if is_script_file(f)]
    tests = [f for f in repo_files if is_test_file(f)]
    ci_files = [f for f in repo_files if is_ci_file(f)]
    docker_files = [f for f in repo_files if is_docker_file(f)]
    stacks = detect_probable_stacks(repo_files, root)
    package_scripts = collect_package_scripts(root)
    risks = collect_inventory_risks(repo_files, modified_files, porcelain, manifests, tests, ci_files, docker_files)
    return {
        "files": repo_files,
        "manifests": manifests,
        "scripts": scripts,
        "tests": tests,
        "ci_files": ci_files,
        "docker_files": docker_files,
        "stacks": stacks,
        "package_scripts": package_scripts,
        "risks": risks,
    }


def build_sections(data):
    """Constroi todas as secoes HTML a partir dos dados."""
    stats = data.get("stats", {})
    tree = data.get("tree", [])
    modified_files = data.get("modified_files", [])
    porcelain = data.get("porcelain", [])
    commits = data.get("commits", [])
    arch = data.get("architecture", {})
    inventory = data.get("inventory", {})
    stacks = inventory.get("stacks", [])
    manifests = inventory.get("manifests", [])
    scripts = inventory.get("scripts", [])
    tests = inventory.get("tests", [])
    ci_files = inventory.get("ci_files", [])
    docker_files = inventory.get("docker_files", [])
    package_scripts = inventory.get("package_scripts", [])
    risks = inventory.get("risks", [])

    def render_path_list(items, empty_message, limit=12):
        if not items:
            return f'<p style="color:#64748b;font-size:12px;font-style:italic;">{html.escape(empty_message)}</p>'
        rendered = []
        for item in items[:limit]:
            rendered.append(
                f'<div style="padding:6px 0;border-bottom:1px solid var(--af-border, #1e293b);font-size:12px;color:#cbd5e1;">'
                f'{html.escape(item)}</div>'
            )
        if len(items) > limit:
            rendered.append(
                f'<div style="padding-top:8px;font-size:11px;color:var(--af-text-muted, #64748b);">'
                f'+{len(items) - limit} itens adicionais</div>'
            )
        return "".join(rendered)

    def render_chip_list(items, empty_message):
        if not items:
            return f'<p style="color:#64748b;font-size:12px;font-style:italic;">{html.escape(empty_message)}</p>'
        chips = []
        for item in items:
            chips.append(
                f'<span style="display:inline-flex;align-items:center;gap:6px;padding:6px 10px;border-radius:999px;'
                f'background:rgba(15,23,42,.85);border:1px solid var(--af-border, #1e293b);color:#cbd5e1;'
                f'font-size:12px;margin:0 8px 8px 0;">{html.escape(item)}</span>'
            )
        return f'<div style="display:flex;flex-wrap:wrap;">{"".join(chips)}</div>'

    def render_stack_cards(items):
        if not items:
            return '<p style="color:#64748b;font-size:12px;font-style:italic;">Nao foi possivel inferir a stack principal.</p>'
        cards = []
        for item in items:
            evidence = item.get("evidence", [])
            confidence = item.get("confidence", "media")
            confidence_color = "#22c55e" if confidence == "alta" else "#eab308" if confidence == "media" else "#94a3b8"
            evidence_html = ""
            if evidence:
                evidence_html = '<div style="display:flex;flex-wrap:wrap;gap:6px;margin-top:8px;">' + "".join(
                    f'<span style="background:rgba(96,165,250,.1);border:1px solid rgba(96,165,250,.25);border-radius:999px;padding:4px 8px;font-size:11px;color:#bfdbfe;">{html.escape(e)}</span>'
                    for e in evidence
                ) + '</div>'
            cards.append(
                f'<div style="padding:12px 0;border-bottom:1px solid var(--af-border, #1e293b);">'
                f'<div style="display:flex;justify-content:space-between;gap:12px;align-items:center;">'
                f'<strong style="color:#e2e8f0;font-size:13px;">{html.escape(item.get("name", "Stack"))}</strong>'
                f'<span style="font-size:11px;color:{confidence_color};text-transform:uppercase;letter-spacing:.6px;">{html.escape(confidence)}</span>'
                f'</div>'
                f'{evidence_html}'
                f'</div>'
            )
        return "".join(cards)

    def render_risk_cards(items):
        if not items:
            return '<p style="color:#64748b;font-size:12px;font-style:italic;">Nenhum risco relevante detectado.</p>'
        cards = []
        severity_colors = {"critical": "#ef4444", "warning": "#eab308", "info": "#60a5fa"}
        for item in items:
            severity = item.get("severity", "info")
            color = severity_colors.get(severity, "#60a5fa")
            cards.append(
                f'<div style="padding:10px 12px;border:1px solid rgba(148,163,184,.15);border-left:3px solid {color};border-radius:8px;margin-bottom:10px;background:rgba(15,23,42,.5);">'
                f'<div style="display:flex;justify-content:space-between;gap:12px;align-items:center;margin-bottom:4px;">'
                f'<strong style="font-size:13px;color:#e2e8f0;">{html.escape(item.get("title", "Risco"))}</strong>'
                f'<span style="font-size:11px;color:{color};text-transform:uppercase;letter-spacing:.6px;">{html.escape(severity)}</span>'
                f'</div>'
                f'<div style="font-size:12px;color:#cbd5e1;">{html.escape(item.get("details", ""))}</div>'
                f'</div>'
            )
        return "".join(cards)

    # --- Tree ---
    tree_lines = []
    modified_set = set(modified_files)
    for e in tree:
        icon = get_file_icon(e["type"])
        is_dir = e["type"] == "dir" or e["type"] == "truncated"
        color = "#60a5fa" if is_dir else "#94a3b8"
        pad = e["depth"] * 20
        size_s = f' <span style="color:#475569;font-size:11px;">[{format_size(e["size"])}]</span>' if not is_dir else ""
        hl = ' style="background:rgba(234,179,8,0.08);border-radius:3px;"' if e["name"] in modified_set else ""
        name_display = e["name"]
        tag = ""
        if e["name"] in modified_set:
            name_display = f'<span style="color:#eab308;font-weight:600;">{e["name"]}</span>'
            tag = ' <span style="color:#eab308;font-size:10px;">⬅ modificado</span>'
        tree_lines.append(
            f'<div style="padding-left:{pad}px;{hl}" class="tree-entry">'
            f'{icon} {name_display}{size_s}{tag}</div>'
        )
    tree_section = "\n".join(tree_lines)
    tree_warning = ""
    if len(tree) >= 200:
        tree_warning = '<div class="warning-banner"><strong>⚠ Arvore extensa</strong> · Profundidade maxima de 6 niveis.</div>'

    # --- Extensions ---
    ext_section = ""
    if stats.get("top_ext"):
        items = []
        for ext_name, count in stats["top_ext"]:
            icon = get_file_icon(ext_name)
            items.append(f'{icon} {ext_name} <strong style="color:#60a5fa;">{count}</strong>')
        ext_section = (
            '<div style="margin-top:12px;">'
            '<div style="font-size:12px;color:#94a3b8;margin-bottom:8px;">Top extensoes:</div>'
            '<div style="display:flex;gap:16px;flex-wrap:wrap;">'
            + "".join(f'<span style="font-size:12px;color:#cbd5e1;">{x}</span>' for x in items)
            + "</div></div>"
        )

    # --- Diff ---
    if modified_files:
        diffs = []
        for f in modified_files:
            icon = get_file_icon(Path(f).suffix)
            diffs.append(
                f'<div style="display:flex;align-items:center;gap:6px;padding:4px 0;font-size:12px;color:#cbd5e1;">'
                f'<span class="status-dot" style="background:#eab308;"></span> {icon} {html.escape(f)}</div>'
            )
        diff_section = ('<div style="margin-bottom:8px;"><span style="font-size:12px;color:#eab308;font-weight:600;">'
                        'Arquivos modificados:</span></div>' + "".join(diffs))
    else:
        diff_section = '<p style="color:#64748b;font-size:12px;font-style:italic;">Nenhuma alteracao detectada.</p>'

    # --- Status ---
    code_map = {"M": "Modificado", "A": "Adicionado", "D": "Deletado", "R": "Renomeado", "??": "Nao rastreado"}
    if porcelain:
        status_lines = []
        for e in porcelain:
            label = code_map.get(e["code"], e["code"])
            dc = ("#22c55e" if e["code"] == "??" else "#eab308" if "M" in e["code"]
                  else "#ef4444" if "D" in e["code"] else "#60a5fa")
            status_lines.append(
                f'<div class="porcelain-item">'
                f'<span class="status-dot" style="background:{dc};"></span>'
                f'<span style="font-family:monospace;font-size:11px;color:#64748b;min-width:30px;">{html.escape(e["code"])}</span>'
                f'<span style="font-size:11px;color:#94a3b8;min-width:90px;">{label}</span>'
                f'<span style="color:#cbd5e1;font-family:monospace;font-size:12px;">{html.escape(e["path"])}</span>'
                f'</div>'
            )
        status_section = "".join(status_lines)
    else:
        status_section = '<p style="color:#64748b;font-size:12px;font-style:italic;">Working tree limpo.</p>'

    # --- Commits ---
    if commits:
        commit_lines = []
        for c in commits:
            commit_lines.append(
                f'<div class="commit-item">'
                f'<span style="font-family:monospace;color:#60a5fa;font-size:11px;min-width:60px;">{html.escape(c["hash"])}</span>'
                f'<span style="flex:1;color:#e2e8f0;font-size:12px;">{html.escape(c["message"][:60])}</span>'
                f'<span style="color:#64748b;font-size:11px;white-space:nowrap;">{html.escape(c["author"])} · {html.escape(c["date"])}</span>'
                f'</div>'
            )
        commits_section = "".join(commit_lines)
    else:
        commits_section = '<p style="color:#64748b;font-size:12px;font-style:italic;">Nenhum commit encontrado.</p>'

    # --- Architecture ---
    if arch:
        arch_lines = []
        for label, dirs in arch.items():
            c = "#60a5fa" if "src" in label or "components" in label else (
                "#22c55e" if "pages" in label or "hooks" in label else "#94a3b8")
            arch_lines.append(
                f'<div class="arch-item">'
                f'<span style="color:{c};font-weight:600;font-size:13px;">{html.escape(label)}</span>'
                f'<span style="color:#64748b;font-family:monospace;font-size:12px;">{", ".join(html.escape(d) for d in dirs)}</span>'
                f'</div>'
            )
        arch_section = "".join(arch_lines)
    else:
        arch_section = '<p style="color:#64748b;font-size:12px;font-style:italic;">Projeto sem estrutura de diretorios clara.</p>'

    return {
        "tree_section": tree_section,
        "tree_warning": tree_warning,
        "ext_section": ext_section,
        "diff_section": diff_section,
        "status_section": status_section,
        "commits_section": commits_section,
        "arch_section": arch_section,
        "stack_section": render_stack_cards(stacks),
        "manifest_section": render_path_list(manifests, "Nenhum manifesto detectado."),
        "scripts_section": render_path_list(scripts, "Nenhum script de automacao detectado."),
        "package_scripts_section": render_chip_list(package_scripts, "Nenhum script em package.json detectado."),
        "tests_section": render_path_list(tests, "Nenhum teste detectado."),
        "ci_section": render_path_list(ci_files, "Nenhum pipeline CI detectado."),
        "docker_section": render_path_list(docker_files, "Nenhum arquivo Docker detectado."),
        "risk_section": render_risk_cards(risks),
    }


def get_project_stats(tree_data, root):
    total_files = sum(1 for e in tree_data if e["type"] not in ("dir", "truncated"))
    total_dirs = sum(1 for e in tree_data if e["type"] == "dir")
    total_size = sum(e["size"] for e in tree_data if e["type"] not in ("dir", "truncated"))
    by_ext = {}
    for e in tree_data:
        if e["type"] not in ("dir", "truncated"):
            by_ext[e["type"]] = by_ext.get(e["type"], 0) + 1
    top_ext = sorted(by_ext.items(), key=lambda x: -x[1])[:5]
    return {"total_files": total_files, "total_dirs": total_dirs, "total_size": total_size, "top_ext": top_ext}


def get_architecture_overview(tree_data):
    dirs_1 = {e["name"] for e in tree_data if e["type"] == "dir" and e["depth"] == 1}
    patterns = {
        "src/": {"src", "app", "lib"},
        "components/": {"components", "ui"},
        "pages/": {"pages", "routes"},
        "api/": {"api", "services", "graphql"},
        "hooks/": {"hooks"},
        "styles/": {"styles", "css", "scss"},
        "tests/": {"tests", "__tests__", "spec"},
        "config/": {"config"},
        "types/": {"types", "interfaces"},
        "utils/": {"utils", "helpers", "lib"},
    }
    return {label: sorted(names & dirs_1) for label, names in patterns.items() if names & dirs_1}


def generate_html(data, sections):
    esc = html.escape
    now = datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    stats = data.get("stats", {})

    theme_css = Path(__file__).resolve().parent.parent / "assets" / "ai-flow-theme.css"
    theme_link = ""
    if theme_css.exists():
        rel_path = os.path.relpath(theme_css, REPORTS_DIR)
        theme_link = f'<link rel="stylesheet" href="{esc(rel_path)}">'

    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Project Context Map</title>
{theme_link}
<style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{
  font-family: var(--af-font-sans, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif);
  background: var(--af-bg-base, #0b1120);
  color: var(--af-text, #e2e8f0);
  padding: 20px;
  line-height: 1.5;
}}
.container {{ max-width:1300px; margin:0 auto; }}
.header {{
  background: linear-gradient(135deg, #1a2333, #0f172a);
  border: 1px solid var(--af-border, #1e3a5f);
  border-radius: var(--af-radius-xl, 16px);
  padding: 24px 32px; margin-bottom:24px;
  display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:12px;
}}
.header h1 {{
  font-size:24px;
  background: linear-gradient(135deg, #60a5fa, #a78bfa);
  -webkit-background-clip:text; -webkit-text-fill-color:transparent;
  display:flex; align-items:center; gap:10px;
}}
.header .subtitle {{ color:var(--af-text-muted, #64748b); font-size:13px; margin-top:4px; }}
.header-badge {{
  background: var(--af-bg-element, #1e3a5f);
  color: var(--af-info, #93c5fd);
  padding:6px 16px; border-radius:var(--af-radius-full, 20px);
  font-size:13px; border:1px solid var(--af-info, #3b82f6);
}}
.branch-name {{ font-family:var(--af-font-mono, "SF Mono","Fira Code",monospace); color:var(--af-success, #22c55e); font-size:14px; }}
.card {{
  background: var(--af-bg-raised, #131c31);
  border:1px solid var(--af-border, #1e293b);
  border-radius:var(--af-radius-lg, 12px);
  padding:20px; margin-bottom:20px;
  transition:border-color .2s, transform .2s;
}}
.card:hover {{ border-color:var(--af-border-hover, #1e3a5f); }}
.card-title {{
  font-size:15px; font-weight:700;
  color:var(--af-text-bright, #f1f5f9);
  margin-bottom:14px; padding-bottom:8px;
  border-bottom:1px solid var(--af-border, #1e293b);
  display:flex; align-items:center; gap:8px;
}}
.grid-2 {{ display:grid; grid-template-columns:1fr 1fr; gap:20px; }}
.stat-grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(120px,1fr)); gap:10px; }}
.stat-card {{
  background: var(--af-bg-inset, #0f172a);
  border-radius:var(--af-radius-md, 8px);
  padding:14px; text-align:center;
}}
.stat-value {{ font-size:28px; font-weight:800; color:var(--af-primary, #a855f7); line-height:1.2; }}
.stat-label {{ font-size:11px; color:var(--af-text-muted, #64748b); text-transform:uppercase; letter-spacing:.5px; margin-top:4px; }}
.tree-container {{
  font-family:var(--af-font-mono, "SF Mono","Fira Code","Consolas",monospace);
  font-size:12px; line-height:1.8;
  max-height:500px; overflow-y:auto;
  background:var(--af-bg-inset, #0a0f1e);
  border-radius:var(--af-radius-md, 8px);
  padding:12px;
  -webkit-overflow-scrolling: touch;
}}
.tree-entry {{ white-space:nowrap; transition:background .15s; border-radius:3px; padding:1px 4px; }}
.tree-entry:hover {{ background:rgba(255,255,255,.04); }}
.commit-item {{
  display:flex; align-items:center; gap:12px;
  padding:8px 0;
  border-bottom:1px solid var(--af-border, #1e293b);
  font-size:13px;
}}
.commit-item:last-child {{ border-bottom:none; }}
.status-dot {{ width:8px; height:8px; border-radius:50%; flex-shrink:0; display:inline-block; }}
.porcelain-item {{
  display:flex; align-items:center; gap:10px; padding:6px 0;
  font-size:13px;
  border-bottom:1px solid var(--af-border, #0f172a);
}}
.arch-item {{
  display:flex; justify-content:space-between; align-items:center;
  padding:8px 0;
  border-bottom:1px solid var(--af-border, #1e293b);
  font-size:13px;
}}
.arch-item:last-child {{ border-bottom:none; }}
.warning-banner {{
  background:rgba(234,179,8,.1); border:1px solid rgba(234,179,8,.3);
  border-radius:var(--af-radius-md, 8px);
  padding:10px 14px; font-size:12px; color:#fde047; margin-top:10px;
}}
.task-board {{ display:grid; grid-template-columns:1fr 1fr 1fr; gap:12px; }}
.task-column {{
  background:var(--af-bg-inset, #0a0f1e);
  border-radius:var(--af-radius-md, 8px);
  padding:12px; min-height:100px;
}}
.task-column-title {{
  font-size:12px; font-weight:600; text-transform:uppercase;
  letter-spacing:.5px; margin-bottom:10px; padding-bottom:6px; border-bottom:2px solid;
}}
.task-column.todo .task-column-title {{ color:var(--af-text-muted, #64748b); border-color:var(--af-text-muted, #64748b); }}
.task-column.wip .task-column-title {{ color:var(--af-warning, #eab308); border-color:var(--af-warning, #eab308); }}
.task-column.done .task-column-title {{ color:var(--af-success, #22c55e); border-color:var(--af-success, #22c55e); }}
.task-card {{
  background:var(--af-bg-raised, #131c31);
  border:1px solid var(--af-border, #1e293b);
  border-radius:var(--af-radius-sm, 6px);
  padding:10px; margin-bottom:8px; font-size:12px; color:#cbd5e1;
}}
.task-card .task-label {{
  display:inline-block; font-size:10px; padding:1px 6px; border-radius:3px;
  background:var(--af-bg-element, #1e3a5f);
  color:var(--af-info, #93c5fd);
  margin-bottom:4px;
}}
.task-hint {{ color:var(--af-text-muted, #475569); font-style:italic; font-size:11px; text-align:center; padding:20px 0; }}
.footer {{ text-align:center; color:var(--af-border, #334155); font-size:12px; padding:20px; margin-top:20px; }}
::-webkit-scrollbar {{ width:6px; height:6px; }}
::-webkit-scrollbar-track {{ background:var(--af-bg-inset, #0a0f1e); }}
::-webkit-scrollbar-thumb {{ background:var(--af-border, #1e293b); border-radius:3px; }}

/* Responsive */
@media (max-width: 900px) {{
  .grid-2 {{ grid-template-columns: 1fr; }}
  .task-board {{ grid-template-columns: 1fr; }}
}}
@media (max-width: 768px) {{
  body {{ padding: 12px; }}
  .header {{ padding: 16px; flex-direction: column; text-align: center; }}
  .header h1 {{ font-size: 20px; }}
  .stat-grid {{ grid-template-columns: repeat(auto-fit, minmax(100px, 1fr)); }}
  .stat-value {{ font-size: 22px; }}
}}
@media (max-width: 480px) {{
  body {{ padding: 8px; }}
  .header h1 {{ font-size: 18px; }}
  .card {{ padding: 14px; }}
  .tree-container {{ font-size: 11px; max-height: 350px; }}
  .commit-item {{ flex-wrap: wrap; gap: 4px; }}
}}
</style>
</head>
<body>
<div class="container">
    <div class="header">
        <div>
            <h1>🗺 Project Context Map</h1>
            <div class="subtitle">
                <span class="branch-name">{esc(data.get('branch', '?'))}</span>
                · {stats.get('total_files', 0)} arquivos · {stats.get('total_dirs', 0)} pastas
                · {format_size(stats.get('total_size', 0))}
            </div>
        </div>
        <div style="text-align:right;">
            <div class="header-badge">Atualizado {esc(now)}</div>
        </div>
    </div>

    <div class="card">
        <div class="card-title">📊 Estatisticas do projeto</div>
        <div class="stat-grid">
            <div class="stat-card"><div class="stat-value" style="color:var(--af-info, #60a5fa);">{stats.get('total_dirs', 0)}</div><div class="stat-label">Pastas</div></div>
            <div class="stat-card"><div class="stat-value" style="color:var(--af-info, #60a5fa);">{stats.get('total_files', 0)}</div><div class="stat-label">Arquivos</div></div>
            <div class="stat-card"><div class="stat-value" style="color:var(--af-info, #60a5fa);">{format_size(stats.get('total_size', 0))}</div><div class="stat-label">Tamanho total</div></div>
            <div class="stat-card"><div class="stat-value" style="color:var(--af-info, #60a5fa);">{len(data.get('commits', []))}</div><div class="stat-label">Ultimos commits</div></div>
            <div class="stat-card"><div class="stat-value" style="color:var(--af-warning, #eab308);">{len(data.get('modified_files', []))}</div><div class="stat-label">Modificados</div></div>
            <div class="stat-card"><div class="stat-value" style="color:var(--af-info, #60a5fa);">{len(data.get('porcelain', []))}</div><div class="stat-label">Status entries</div></div>
        </div>
        {sections['ext_section']}
    </div>

    <div class="grid-2" style="margin-bottom:20px;">
        <div class="card" style="margin-bottom:0;">
            <div class="card-title">🧠 Stack provavel e manifestos</div>
            {sections['stack_section']}
            <div style="height:14px;"></div>
            <div style="font-size:12px;color:var(--af-text-muted, #64748b);margin-bottom:8px;">Manifestos detectados</div>
            {sections['manifest_section']}
        </div>
        <div class="card" style="margin-bottom:0;">
            <div class="card-title">🧰 Scripts, testes e infraestrutura</div>
            <div style="font-size:12px;color:var(--af-text-muted, #64748b);margin-bottom:8px;">Scripts de automacao</div>
            {sections['scripts_section']}
            <div style="height:12px;"></div>
            <div style="font-size:12px;color:var(--af-text-muted, #64748b);margin-bottom:8px;">Scripts de package.json</div>
            {sections['package_scripts_section']}
            <div style="height:12px;"></div>
            <div style="font-size:12px;color:var(--af-text-muted, #64748b);margin-bottom:8px;">Testes detectados</div>
            {sections['tests_section']}
            <div style="height:12px;"></div>
            <div style="font-size:12px;color:var(--af-text-muted, #64748b);margin-bottom:8px;">CI / CD</div>
            {sections['ci_section']}
            <div style="height:12px;"></div>
            <div style="font-size:12px;color:var(--af-text-muted, #64748b);margin-bottom:8px;">Docker / ambiente</div>
            {sections['docker_section']}
        </div>
    </div>

    <div class="card" style="margin-bottom:20px;">
        <div class="card-title">⚠ Riscos do contexto atual</div>
        {sections['risk_section']}
    </div>

    <div class="grid-2">
        <div>
            <div class="card" style="margin-bottom:0;">
                <div class="card-title">📂 Estrutura do projeto</div>
                <div class="tree-container">
                    {sections['tree_section']}
                    {sections['tree_warning']}
                </div>
            </div>
        </div>
        <div>
            <div class="card" style="margin-bottom:20px;">
                <div class="card-title">🔀 Git — Branch atual</div>
                <div style="display:flex;align-items:center;gap:10px;margin-bottom:12px;flex-wrap:wrap;">
                    <span class="branch-name" style="font-size:18px;">{esc(data.get('branch', '?'))}</span>
                    <span style="font-size:12px;color:var(--af-text-muted, #64748b);">{stats.get('total_files', 0)} commits</span>
                </div>
                {sections['diff_section']}
            </div>
            <div class="card" style="margin-bottom:20px;">
                <div class="card-title">📋 Status Git</div>
                {sections['status_section']}
            </div>
            <div class="card" style="margin-bottom:0;">
                <div class="card-title">📜 Ultimos commits</div>
                {sections['commits_section']}
            </div>
        </div>
    </div>

    <div class="grid-2" style="margin-top:20px;">
        <div class="card" style="margin-bottom:0;">
            <div class="card-title">🏗 Arquitetura (diretorios-chave)</div>
            {sections['arch_section']}
        </div>
        <div class="card" style="margin-bottom:0;">
            <div class="card-title">📌 Quadro de tarefas (WIP)</div>
            <p style="color:var(--af-text-muted, #64748b);font-size:12px;margin-bottom:12px;">
                Edite manualmente para acompanhar o progresso dos agentes.
            </p>
            <div class="task-board">
                <div class="task-column todo">
                    <div class="task-column-title">A fazer</div>
                    <div class="task-hint">Adicione tarefas aqui</div>
                </div>
                <div class="task-column wip">
                    <div class="task-column-title">Em andamento</div>
                    <div class="task-card wip-card">
                        <div class="task-label">⚡ Coder</div>
                        Implementacao em andamento
                    </div>
                </div>
                <div class="task-column done">
                    <div class="task-column-title">Concluido</div>
                    <div class="task-hint">Tarefas finalizadas</div>
                </div>
            </div>
        </div>
    </div>

    <div class="footer">
        Gerado por .ai-flow/scripts/generate-context-map.py · {esc(now)}
    </div>
</div>
</body>
</html>"""


def main():
    print("=== AI-Flow: Generate Context Map ===\n")

    root = get_project_root()
    if not root:
        print("[!] Projeto nao encontrado. Use este script dentro de um repositorio Git.")
        return 1

    print(f"[1/6] Escaneando projeto em: {root}")
    tree_data = build_tree(root)

    print(f"[2/6] Obtendo informacoes Git...")
    branch = get_git_branch()
    commits = get_git_log()
    modified_files = get_git_diff_files()
    porcelain = get_git_status()

    print(f"[3/6] Classificando stack e inventario tecnico...")
    inventory = build_repository_inventory(root, tree_data, modified_files, porcelain)

    print(f"[4/6] Calculando estatisticas...")
    stats = get_project_stats(tree_data, root)
    arch = get_architecture_overview(tree_data)

    print(f"[5/6] Montando HTML...")
    data = {
        "branch": branch,
        "commits": commits,
        "modified_files": modified_files,
        "porcelain": porcelain,
        "stats": stats,
        "architecture": arch,
        "tree": tree_data,
        "inventory": inventory,
    }
    sections = build_sections(data)
    html_output = generate_html(data, sections)

    print(f"[6/6] Salvando...")
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text(html_output, encoding="utf-8")

    abs_path = OUTPUT_FILE.resolve()
    print(f"\n[OK] Mapa de contexto gerado:")
    print(f"     {abs_path}")
    print(f"\nAbra no navegador ou execute:")
    print(f"  .ai-flow\\scripts\\generate-context-map.ps1")
    return 0


if __name__ == "__main__":
    sys.exit(main())
