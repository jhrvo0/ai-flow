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
    esc = html.escape
    now_str = scan_time.strftime("%d/%m/%Y %H:%M:%S")
    total = len(projects)
    with_changes = sum(1 for p in projects if p["has_changes"])
    with_aiflow = sum(1 for p in projects if p["has_aiflow"])

    cards_html = ""
    for p in projects:
        if p["has_changes"]:
            dot_color = "#eab308"
            status_label = f"{p['changes_count']} alterado(s)"
        else:
            dot_color = "#22c55e"
            status_label = "Limpo"

        aiflow_badge = ""
        if p["has_aiflow"]:
            aiflow_badge = '<span class="badge badge-aiflow">⚡ AI-Flow</span>'

        p_path = p["path"]
        p_path_esc = esc(p_path.replace("\\", "/"))
        ctx_path = f"{p_path_esc}/.ai-flow/reports/project-context.html"
        qg_path = f"{p_path_esc}/.ai-flow/reports/quality-gate.html"
        wf_path = f"{p_path_esc}/.ai-flow/workflows/feature-flow.md"

        links = [
            f'<a href="#" class="link-btn" onclick="window.location.href=\'file:///{p_path_esc}\'">📂 Abrir</a>',
        ]
        if p["has_context_map"]:
            links.append(f'<a href="file:///{esc(ctx_path)}" class="link-btn" target="_blank">🗺 Contexto</a>')
        else:
            links.append(f'<a href="#" class="link-btn link-disabled" onclick="alert(\'Gere o contexto primeiro\')">🗺 Contexto</a>')
        if p["has_quality_report"]:
            links.append(f'<a href="file:///{esc(qg_path)}" class="link-btn" target="_blank">🛡 Qualidade</a>')
        else:
            links.append(f'<a href="#" class="link-btn link-disabled" onclick="alert(\'Rode o quality gate primeiro\')">🛡 Qualidade</a>')
        links.append(f'<a href="file:///{esc(wf_path)}" class="link-btn" target="_blank">📋 Workflows</a>')

        gen_btn = ""
        if p["has_aiflow"]:
            gen_btn = (
                f'<div class="gen-row">'
                f'<span class="gen-label">Gerar:</span>'
                f'<button class="gen-btn" onclick="navigator.clipboard.writeText(\'cd /d \\"{esc(p_path)}\\" && python .ai-flow\\\\scripts\\\\generate-context-map.py\');showToast(\'Comando copiado! Cole no terminal.\')">🗺 Mapa</button>'
                f'<button class="gen-btn" onclick="navigator.clipboard.writeText(\'cd /d \\"{esc(p_path)}\\" && python .ai-flow\\\\scripts\\\\quality-gate.py\');showToast(\'Comando copiado! Cole no terminal.\')">🛡 Quality Gate</button>'
                f'</div>'
            )

        cards_html += f"""
        <div class="project-card {"card-dirty" if p["has_changes"] else ""}">
            <div class="card-top">
                <div>
                    <div class="card-name">{esc(p["name"])} {aiflow_badge}</div>
                    <div class="card-path">{esc(p_path)}</div>
                </div>
                <div class="card-status" title="{esc(status_label)}">
                    <span class="status-dot" style="background:{dot_color};"></span>
                    <span class="status-label" style="color:{dot_color};">{esc(status_label)}</span>
                </div>
            </div>
            <div class="card-meta">
                <span>🌿 {esc(p["branch"])}</span>
                <span>📄 {p["file_count"]} arquivos</span>
                <span>📅 {esc(p["last_modified"])}</span>
            </div>
            <div class="card-commit">
                <span class="commit-hash">{esc(p["commit"]["hash"])}</span>
                <span class="commit-msg">{esc(p["commit"]["message"][:60])}</span>
                <span class="commit-meta">{esc(p["commit"]["author"])} · {esc(p["commit"]["date"])}</span>
            </div>
            <div class="card-links">{"".join(links)}</div>
            {gen_btn}
        </div>"""

    if not projects:
        cards_html = f"""
        <div class="empty-state">
            <div style="font-size:48px;margin-bottom:16px;">📂</div>
            <div style="font-size:20px;color:#f1f5f9;margin-bottom:8px;">Nenhum projeto ainda</div>
            <div style="color:#64748b;font-size:14px;margin-bottom:20px;">
                Arraste uma pasta para a zona abaixo ou use o terminal:
            </div>
            <div style="background:#0f172a;border:1px solid #1e3a5f;border-radius:8px;padding:10px 16px;font-family:monospace;font-size:13px;color:#60a5fa;display:inline-block;">
                python .ai-flow\\scripts\\generate-dashboard.py --add "C:/caminho/do/seu/projeto"
            </div>
        </div>"""

    html_output = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AI-Flow Dashboard</title>
<style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    background: #0b1120;
    color: #e2e8f0;
    padding: 20px;
    min-height: 100vh;
}}
.container {{ max-width: 1400px; margin: 0 auto; }}

.header {{
    background: linear-gradient(135deg, #1a2333, #0f172a);
    border: 1px solid #1e3a5f;
    border-radius: 16px;
    padding: 24px 28px;
    margin-bottom: 20px;
    display: flex;
    justify-content: space-between;
    align-items: center;
    flex-wrap: wrap;
    gap: 12px;
}}
.header-left {{ display: flex; align-items: center; gap: 16px; }}
.header-icon {{ width:44px;height:44px;background:linear-gradient(135deg,#3b82f6,#a78bfa);border-radius:12px;display:flex;align-items:center;justify-content:center;font-size:22px; }}
.header h1 {{ font-size:24px;background:linear-gradient(135deg,#60a5fa,#a78bfa);-webkit-background-clip:text;-webkit-text-fill-color:transparent; }}
.header .sub {{ color:#64748b;font-size:13px;margin-top:2px; }}
.header-right {{ text-align:right; }}
.header-badge {{ background:#1e3a5f;color:#93c5fd;padding:6px 16px;border-radius:20px;font-size:13px;border:1px solid #3b82f6;display:inline-block; }}
.header-time {{ color:#475569;font-size:11px;margin-top:4px; }}

.stats-bar {{ display:flex;gap:12px;margin-bottom:20px;flex-wrap:wrap; }}
.stat-pill {{ background:#131c31;border:1px solid #1e293b;border-radius:24px;padding:8px 16px;font-size:13px;display:flex;align-items:center;gap:6px; }}
.stat-pill strong {{ color:#60a5fa; }}

/* Drop zone */
.drop-zone {{
    background: #0f172a;
    border: 2px dashed #1e293b;
    border-radius: 12px;
    padding: 24px;
    text-align: center;
    margin-bottom: 20px;
    transition: all .2s;
    cursor: pointer;
}}
.drop-zone:hover, .drop-zone.dragover {{ border-color: #3b82f6; background: rgba(59,130,246,.05); }}
.drop-zone-title {{ font-size: 15px; color: #94a3b8; margin-bottom: 4px; }}
.drop-zone-sub {{ font-size: 12px; color: #475569; }}
.drop-zone-input {{ display: flex; gap: 8px; margin-top: 12px; justify-content: center; flex-wrap: wrap; }}
.drop-input {{
    background: #131c31; border: 1px solid #1e293b; border-radius: 6px;
    padding: 8px 12px; color: #e2e8f0; font-size: 13px; outline: none;
    min-width: 300px; max-width: 100%;
}}
.drop-input:focus {{ border-color: #3b82f6; }}
.add-btn {{
    background: #1e3a5f; border: 1px solid #3b82f6; color: #93c5fd;
    padding: 8px 16px; border-radius: 6px; font-size: 13px; cursor: pointer;
    transition: all .2s;
}}
.add-btn:hover {{ background: #1e4a7a; }}
.drop-result {{
    margin-top: 8px; font-size: 12px; color: #22c55e; min-height: 20px;
}}

/* Filters */
.filter-bar {{ display:flex;gap:8px;margin-bottom:16px;flex-wrap:wrap; }}
.filter-btn {{
    background:#1e293b;border:1px solid #334155;color:#64748b;
    padding:6px 14px;border-radius:6px;font-size:12px;cursor:pointer;transition:all .2s;
}}
.filter-btn:hover {{ background:#334155;color:#e2e8f0; }}
.filter-btn.active {{ background:#1e3a5f;border-color:#3b82f6;color:#93c5fd; }}

/* Grid */
.project-grid {{ display:grid;grid-template-columns:repeat(auto-fill,minmax(380px,1fr));gap:16px; }}
@media(max-width:600px){{ .project-grid{{grid-template-columns:1fr;}} }}

.project-card {{
    background:#131c31;border:1px solid #1e293b;border-radius:12px;
    padding:18px;transition:all .2s;position:relative;overflow:hidden;
}}
.project-card:hover {{ border-color:#334155;transform:translateY(-2px); }}
.project-card.card-dirty {{ border-left:3px solid #eab308; }}

.card-top {{ display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:10px; }}
.card-name {{ font-size:17px;font-weight:700;color:#f1f5f9;display:flex;align-items:center;gap:6px; }}
.card-path {{ font-size:11px;color:#475569;font-family:monospace;margin-top:2px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:280px; }}
.card-status {{ display:flex;align-items:center;gap:6px;flex-shrink:0; }}
.status-dot {{ width:9px;height:9px;border-radius:50%;display:inline-block; }}
.status-label {{ font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:.5px; }}

.badge {{ font-size:10px;padding:2px 8px;border-radius:4px;font-weight:600;text-transform:uppercase;letter-spacing:.5px; }}
.badge-aiflow {{ background:rgba(59,130,246,.15);color:#93c5fd; }}

.card-meta {{ display:flex;gap:14px;font-size:12px;color:#64748b;margin-bottom:8px;flex-wrap:wrap; }}
.card-meta span {{ display:flex;align-items:center;gap:4px; }}

.card-commit {{
    background:#0a0f1e;border-radius:6px;padding:7px 10px;font-size:12px;
    margin-bottom:12px;display:flex;align-items:center;gap:8px;flex-wrap:wrap;
}}
.commit-hash {{ font-family:monospace;color:#60a5fa;font-size:11px;min-width:55px; }}
.commit-msg {{ color:#cbd5e1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;flex:1;min-width:0; }}
.commit-meta {{ color:#475569;font-size:11px;white-space:nowrap; }}

.card-links {{ display:flex;gap:4px;flex-wrap:wrap; }}
.link-btn {{
    background:#1e293b;border:1px solid #334155;color:#94a3b8;
    padding:4px 10px;border-radius:6px;font-size:11px;text-decoration:none;transition:all .2s;cursor:pointer;
}}
.link-btn:hover {{ background:#334155;color:#e2e8f0; }}
.link-disabled {{ opacity:.4;cursor:not-allowed; }}

.gen-row {{ display:flex;align-items:center;gap:8px;margin-top:8px;padding-top:8px;border-top:1px solid #1e293b; }}
.gen-label {{ font-size:11px;color:#475569; }}
.gen-btn {{
    background:#0f172a;border:1px solid #1e3a5f;color:#60a5fa;
    padding:3px 10px;border-radius:4px;font-size:11px;cursor:pointer;transition:all .2s;
}}
.gen-btn:hover {{ background:#1e3a5f; }}

.empty-state {{ grid-column:1/-1;text-align:center;padding:40px 20px; }}

.toast {{
    position:fixed;bottom:20px;right:20px;
    background:#1e293b;border:1px solid #3b82f6;border-radius:8px;
    padding:12px 20px;font-size:13px;color:#e2e8f0;z-index:1000;
    display:none;box-shadow:0 4px 20px rgba(0,0,0,.4);
}}
.toast.show {{ display:block;animation:fadeIn .3s; }}
@keyframes fadeIn {{ from{{opacity:0;transform:translateY(10px)}} to{{opacity:1;transform:translateY(0)}} }}

.footer {{ text-align:center;color:#334155;font-size:12px;padding:24px 0 8px;margin-top:20px; }}
</style>
</head>
<body>
<div class="container">

    <div class="header">
        <div class="header-left">
            <div class="header-icon">⚡</div>
            <div>
                <h1>AI-Flow Dashboard</h1>
                <div class="sub">{total} projetos · {with_changes} com alteracoes · {with_aiflow} com AI-Flow</div>
            </div>
        </div>
        <div class="header-right">
            <div class="header-badge">📡 {esc(str(root_dir))}</div>
            <div class="header-time">Atualizado {esc(now_str)}</div>
        </div>
    </div>

    <div class="stats-bar">
        <div class="stat-pill">📦 <strong>{total}</strong> projetos</div>
        <div class="stat-pill">⚡ <strong>{with_aiflow}</strong> com AI-Flow</div>
        <div class="stat-pill">✏️ <strong>{with_changes}</strong> com alteracoes</div>
        <div class="stat-pill">📂 <strong>{sum(p["file_count"] for p in projects)}</strong> arquivos</div>
    </div>

    <!-- Drop zone + Add project -->
    <div class="drop-zone" id="dropZone">
        <div class="drop-zone-title">📂 Arraste uma pasta de projeto para aqui</div>
        <div class="drop-zone-sub">ou cole o caminho manualmente abaixo</div>
        <div class="drop-zone-input">
            <input type="text" class="drop-input" id="pathInput" placeholder="C:\\Users\\joaoh\\MeuProjeto">
            <button class="add-btn" onclick="addFromInput()">+ Adicionar</button>
        </div>
        <div class="drop-result" id="dropResult"></div>
    </div>

    <div class="filter-bar">
        <input type="text" class="drop-input" id="searchInput" placeholder="Buscar projeto..." oninput="filterProjects()" style="flex:1;min-width:150px;">
        <button class="filter-btn active" id="filterAll" onclick="setFilter('all')">Todos</button>
        <button class="filter-btn" id="filterChanges" onclick="setFilter('changes')">Com alteracoes</button>
        <button class="filter-btn" id="filterAiflow" onclick="setFilter('aiflow')">AI-Flow</button>
        <button class="filter-btn" onclick="window.location.href='file:///{esc(str(AI_FLOW_DIR.resolve()).replace(chr(92), "/"))}/dashboard.html'" title="Atualizar">🔄</button>
    </div>

    <div class="project-grid" id="projectGrid">
        {cards_html}
    </div>

    <div class="footer">
        AI-Flow Dashboard · <a href="#" style="color:#475569;text-decoration:none;" onclick="showToast('Rode no terminal:\\n  python .ai-flow\\\\scripts\\\\generate-dashboard.py');return false;">🔄 Atualizar</a>
    </div>

</div>

<div class="toast" id="toast"></div>

<script>
let currentFilter = 'all';

document.getElementById('dropZone').addEventListener('dragover', function(e) {{
    e.preventDefault();
    this.classList.add('dragover');
}});
document.getElementById('dropZone').addEventListener('dragleave', function(e) {{
    e.preventDefault();
    this.classList.remove('dragover');
}});
document.getElementById('dropZone').addEventListener('drop', function(e) {{
    e.preventDefault();
    this.classList.remove('dragover');
    const files = e.dataTransfer.files;
    if (files.length > 0) {{
        const path = files[0].path || files[0].name;
        document.getElementById('pathInput').value = path;
        const result = document.getElementById('dropResult');
        result.innerHTML = '📁 Pasta detectada: <strong>' + path + '</strong>. Clique em "+ Adicionar" para confirmar.';
        result.style.color = '#22c55e';
    }}
}});

function addFromInput() {{
    const path = document.getElementById('pathInput').value.trim();
    const result = document.getElementById('dropResult');
    if (!path) {{
        result.innerHTML = '⚠ Cole ou arraste um caminho de pasta primeiro.';
        result.style.color = '#eab308';
        return;
    }}
    const cmd = 'python .ai-flow\\\\scripts\\\\generate-dashboard.py --add "' + path + '"';
    navigator.clipboard.writeText(cmd).then(() => {{
        result.innerHTML = '✅ Comando copiado! Cole no terminal e pressione Enter:<br><code style="background:#1e293b;padding:2px 6px;border-radius:3px;font-size:12px;">' + cmd + '</code>';
        result.style.color = '#22c55e';
    }}).catch(() => {{
        result.innerHTML = '⚠ Copie manualmente: ' + cmd;
        result.style.color = '#eab308';
    }});
}}

function filterProjects() {{
    const search = document.getElementById('searchInput').value.toLowerCase();
    document.querySelectorAll('.project-card').forEach(card => {{
        const name = card.querySelector('.card-name').textContent.toLowerCase();
        const matchesSearch = name.includes(search);
        let matchesFilter = true;
        if (currentFilter === 'changes') matchesFilter = card.classList.contains('card-dirty');
        if (currentFilter === 'aiflow') matchesFilter = !!card.querySelector('.badge-aiflow');
        card.style.display = (matchesSearch && matchesFilter) ? '' : 'none';
    }});
}}

function setFilter(filter) {{
    currentFilter = filter;
    document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
    document.getElementById('filter' + filter.charAt(0).toUpperCase() + filter.slice(1)).classList.add('active');
    filterProjects();
}}

function showToast(msg) {{
    const t = document.getElementById('toast');
    t.textContent = msg;
    t.classList.add('show');
    setTimeout(() => t.classList.remove('show'), 4000);
}}
</script>
</body>
</html>"""
    return html_output


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
