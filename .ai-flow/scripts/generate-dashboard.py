"""
.ai-flow/scripts/generate-dashboard.py

Dashboard central que lista todos os projetos (auto-descobertos + adicionados).
Suporta --add e --remove para gerenciar a lista manual.

Uso:
  python .ai-flow/scripts/generate-dashboard.py
  python .ai-flow/scripts/generate-dashboard.py --add "C:/Users/joaoh/MeuProjeto"
  python .ai-flow/scripts/generate-dashboard.py --remove "C:/Users/joaoh/MeuProjeto"
  python .ai-flow/scripts/generate-dashboard.py --root "C:/Users/joaoh/Projetos"

Saida: .ai-flow/dashboard.html
"""

import subprocess
import datetime
import html
import os
import sys
import json
import argparse
from pathlib import Path

AI_FLOW_DIR = Path(__file__).resolve().parent.parent
REPORTS_DIR = AI_FLOW_DIR / "reports"
OUTPUT_FILE = AI_FLOW_DIR / "dashboard.html"
PROJECTS_FILE = AI_FLOW_DIR / "projects.json"
DEFAULT_ROOT = AI_FLOW_DIR.parent


def run_cmd(cmd, cwd=None):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, check=False,
                           encoding="utf-8", errors="replace", cwd=cwd)
        return r.stdout.strip(), r.stderr.strip(), r.returncode
    except FileNotFoundError:
        return "", "command not found", -1


def load_projects_json():
    if PROJECTS_FILE.exists():
        try:
            data = json.loads(PROJECTS_FILE.read_text(encoding="utf-8"))
            if isinstance(data, list):
                return [str(p) for p in data if p]
        except (json.JSONDecodeError, Exception):
            pass
    return []


def save_projects_json(paths):
    PROJECTS_FILE.write_text(
        json.dumps([str(p) for p in sorted(set(paths))], indent=2, ensure_ascii=False),
        encoding="utf-8"
    )


def add_project(path):
    resolved = str(Path(path).resolve())
    paths = load_projects_json()
    if resolved not in paths:
        paths.append(resolved)
        save_projects_json(paths)
        print(f"[OK] Projeto adicionado: {resolved}")
    else:
        print(f"[!] Projeto ja esta na lista: {resolved}")
    return paths


def remove_project(path):
    resolved = str(Path(path).resolve())
    paths = load_projects_json()
    if resolved in paths:
        paths.remove(resolved)
        save_projects_json(paths)
        print(f"[OK] Projeto removido: {resolved}")
    else:
        print(f"[!] Projeto nao encontrado na lista: {resolved}")
    return paths


def discover_git_repos(root):
    projects = []
    root = Path(root).resolve()

    if (root / ".git").exists():
        projects.append(root)

    try:
        for entry in sorted(root.iterdir()):
            if entry.is_dir() and not entry.name.startswith("."):
                if (entry / ".git").exists():
                    projects.append(entry)
    except PermissionError:
        pass

    return projects


def get_project_info(project_path):
    name = project_path.name
    rel = str(project_path)

    branch, _, _ = run_cmd(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=project_path)

    last_commit, _, _ = run_cmd(
        ["git", "log", "-1", "--pretty=format:%h|%an|%ar|%s"], cwd=project_path
    )
    commit_data = {"hash": "?", "author": "?", "date": "?", "message": "?"}
    if last_commit:
        parts = last_commit.split("|", 3)
        if len(parts) == 4:
            commit_data = dict(zip(["hash", "author", "date", "message"], parts))

    has_changes = False
    changes_count = 0
    stdout, _, _ = run_cmd(["git", "status", "--porcelain"], cwd=project_path)
    if stdout:
        has_changes = True
        changes_count = len(stdout.strip().split("\n"))

    file_count = 0
    try:
        for f in project_path.rglob("*"):
            if f.is_file() and ".git" not in f.parts:
                file_count += 1
        file_count = min(file_count, 9999)
    except Exception:
        file_count = 0

    last_modified = ""
    stdout2, _, _ = run_cmd(["git", "log", "-1", "--format=%ci", "--", "."], cwd=project_path)
    if stdout2:
        last_modified = stdout2[:10]

    has_aiflow = (project_path / ".ai-flow").exists()
    has_context_map = (project_path / ".ai-flow" / "reports" / "project-context.html").exists()
    has_quality_report = (project_path / ".ai-flow" / "reports" / "quality-gate.html").exists()

    return {
        "name": name,
        "path": rel,
        "branch": branch or "?",
        "commit": commit_data,
        "has_changes": has_changes,
        "changes_count": changes_count,
        "file_count": file_count,
        "last_modified": last_modified,
        "has_aiflow": has_aiflow,
        "has_context_map": has_context_map,
        "has_quality_report": has_quality_report,
    }


def generate_html(projects, root_dir, scan_time):
    template_path = AI_FLOW_DIR / "dashboard.html"
    if not template_path.exists():
        return "<html><body><h1>AI-Flow Dashboard</h1><p>Template dashboard.html nao encontrado.</p></body></html>"
    
    html_content = template_path.read_text(encoding="utf-8")
    
    import json
    import re
    
    projects_json = json.dumps(projects, ensure_ascii=False, indent=8)
    
    pattern = r"// BEGIN_STATIC_PROJECTS[\s\S]*?// END_STATIC_PROJECTS"
    replacement = f"""// BEGIN_STATIC_PROJECTS
        // Static fallback data in case server is offline
        const staticProjectsFallback = {projects_json};
        // END_STATIC_PROJECTS"""
        
    match = re.search(pattern, html_content)
    if match:
        new_html = html_content.replace(match.group(0), replacement)
    else:
        new_html = html_content
    return new_html


def main():
    parser = argparse.ArgumentParser(description="Dashboard central AI-Flow")
    parser.add_argument("--root", default=str(DEFAULT_ROOT), help="Diretorio para escanear projetos")
    parser.add_argument("--add", help="Adicionar um projeto pelo caminho")
    parser.add_argument("--remove", help="Remover um projeto pelo caminho")
    args = parser.parse_args()

    # Handle --add and --remove
    if args.add:
        add_project(args.add)
        return 0
    if args.remove:
        remove_project(args.remove)
        return 0

    root_dir = args.root
    scan_time = datetime.datetime.now()

    print("=== AI-Flow: Generate Dashboard ===\n")

    # Auto-discover + merge with projects.json
    print(f"[1/4] Escaneando projetos em: {root_dir}")
    auto_projects = discover_git_repos(root_dir)
    manual_paths = load_projects_json()

    # Merge: all manual paths + auto-discovered
    all_paths = set()
    for p in auto_projects:
        all_paths.add(str(p.resolve()))
    for p in manual_paths:
        all_paths.add(str(Path(p).resolve()))

    # Save merged paths back so json stays in sync
    save_projects_json(sorted(all_paths))

    print(f"[2/4] Coletando informacoes de {len(all_paths)} projeto(s)...")
    projects = []
    for i, p in enumerate(sorted(all_paths), 1):
        pp = Path(p)
        if not pp.exists():
            print(f"    [!] Caminho nao encontrado, ignorando: {p}")
            continue
        name = pp.name
        print(f"    [{i}/{len(all_paths)}] {name}...")
        info = get_project_info(pp)
        projects.append(info)

    print(f"[3/4] Gerando dashboard HTML...")
    html_output = generate_html(projects, root_dir, scan_time)

    print(f"[4/4] Salvando...")
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text(html_output, encoding="utf-8")

    abs_path = OUTPUT_FILE.resolve()
    print(f"\n[OK] Dashboard gerado: {abs_path}")
    print(f"     {len(projects)} projeto(s)")
    print(f"\nPara adicionar um projeto manualmente:")
    print(f"  python .ai-flow\\scripts\\generate-dashboard.py --add \"C:/caminho/do/projeto\"")
    return 0


if __name__ == "__main__":
    sys.exit(main())
