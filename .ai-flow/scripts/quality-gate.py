"""
.ai-flow/scripts/quality-gate.py

Gera relatorio HTML de qualidade com base no git diff.
Sem dependencias externas — apenas Python padrao.
"""

import subprocess
import datetime
import html
import os
import re
import sys
import collections
from pathlib import Path

REPORTS_DIR = Path(__file__).resolve().parent.parent / "reports"
OUTPUT_FILE = REPORTS_DIR / "quality-gate.html"
MAX_LINES_PER_FILE = 300
MAX_FUNCTION_LINES = 50


def run_cmd(cmd):
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, check=False, encoding="utf-8", errors="replace"
        )
        return result.stdout, result.stderr, result.returncode
    except FileNotFoundError:
        return "", "Comando nao encontrado: " + " ".join(cmd), -1


def get_git_diff():
    stdout, _, _ = run_cmd(["git", "diff"])
    return stdout


def get_git_diff_stat():
    stdout, _, _ = run_cmd(["git", "diff", "--stat"])
    return stdout


def get_git_numstat():
    stdout, _, _ = run_cmd(["git", "diff", "--numstat"])
    return stdout


def parse_numstat(numstat_text):
    files = []
    for line in numstat_text.strip().splitlines():
        parts = line.split("\t")
        if len(parts) >= 3:
            added, removed, filepath = parts[0], parts[1], parts[2]
            if added != "-":
                files.append({
                    "path": filepath,
                    "added": int(added),
                    "removed": int(removed),
                })
    return files


def detect_long_lines(diff_text, max_lines=MAX_LINES_PER_FILE):
    alerts = []
    current_file = None
    lines_in_current = 0
    added_lines_in_current = 0
    file_changes = {}

    for line in diff_text.splitlines():
        if line.startswith("+++ b/"):
            current_file = line[6:]
            lines_in_current = 0
            added_lines_in_current = 0
        elif line.startswith("diff --git"):
            if current_file and lines_in_current > max_lines:
                alerts.append({
                    "type": "warning",
                    "file": current_file,
                    "msg": f"Arquivo alterado tem {lines_in_current} linhas no diff (limite: {max_lines}). Considere dividir.",
                    "lines": lines_in_current,
                })
            current_file = None
        elif current_file is not None:
            lines_in_current += 1
            if line.startswith("+"):
                added_lines_in_current += 1

    if current_file and lines_in_current > max_lines:
        alerts.append({
            "type": "warning",
            "file": current_file,
            "msg": f"Arquivo alterado tem {lines_in_current} linhas (limite: {max_lines}). Considere dividir.",
            "lines": lines_in_current,
        })
    return alerts


def detect_long_functions(diff_text, max_func_lines=MAX_FUNCTION_LINES):
    alerts = []
    current_file = None
    lines_buffer = []
    in_function = False
    brace_count = 0
    func_start = 0
    func_name = ""

    for line in diff_text.splitlines():
        if line.startswith("+++ b/"):
            current_file = line[6:]
        if not line.startswith("+") and not line.startswith(" "):
            continue

        content = line[1:] if line.startswith("+") else line[1:]

        if re.match(r"^\s*(function\s+\w+|const\s+\w+\s*=\s*(async\s*)?\(|def\s+\w+|export\s+(default\s+)?(function|const))", content):
            in_function = True
            func_start = 0
            brace_count = 0
            func_name = content.strip()[:60]
            lines_buffer = []

        if in_function:
            lines_buffer.append(content)
            brace_count += content.count("{") - content.count("}")
            if brace_count <= 0 and len(lines_buffer) > 0:
                if len(lines_buffer) > max_func_lines:
                    alerts.append({
                        "type": "warning",
                        "file": current_file or "?",
                        "msg": f"Funcao/bloco grande: ~{len(lines_buffer)} linhas (limite: {max_func_lines}). Considere extrair funcoes menores.",
                        "lines": len(lines_buffer),
                        "func": func_name,
                    })
                in_function = False
                lines_buffer = []
    return alerts


def detect_todos_fixmes(diff_text):
    alerts = []
    for i, line in enumerate(diff_text.splitlines(), 1):
        if line.startswith("+"):
            content = line[1:]
            todo_match = re.search(r"(TODO|FIXME|HACK|XXX|BUG|WORKAROUND)", content, re.IGNORECASE)
            if todo_match:
                alerts.append({
                    "type": "info",
                    "file": extract_filename(diff_text, i),
                    "msg": f"{todo_match.group(1)} encontrado: {content.strip()[:80]}",
                    "lines": 1,
                })
    return alerts


def detect_prints_logs(diff_text):
    alerts = []
    patterns = [
        (r'console\.(log|debug|info|warn|error)\s*\(', "console.log/debug/info/warn/error"),
        (r'print\s*\(', "print()"),
        (r'println!\s*\(', "println! (Rust)"),
        (r'System\.out\.println', "System.out.println (Java)"),
        (r'puts\s+', "puts (Ruby)"),
        (r'console\.log\s*\(', "console.log (JS/TS)"),
    ]

    for i, line in enumerate(diff_text.splitlines(), 1):
        stripped = line.lstrip()
        if stripped.startswith("+"):
            content = line[1:]
            for pattern, label in patterns:
                if re.search(pattern, content):
                    alerts.append({
                        "type": "info",
                        "file": extract_filename(diff_text, i),
                        "msg": f"Possivel debug/log esquecido: {label} -> {content.strip()[:80]}",
                        "lines": 1,
                    })
                    break
    return alerts


def extract_filename(diff_text, approx_line):
    last_file = "?"
    for line in diff_text.splitlines():
        if line.startswith("+++ b/"):
            last_file = line[6:]
    return last_file


def detect_added_comments(diff_text):
    alerts = []
    comment_count = 0
    comment_lines = []
    current_file = None

    for line in diff_text.splitlines():
        if line.startswith("+++ b/"):
            current_file = line[6:]
        if line.startswith("+") and not line.startswith("+++"):
            content = line[1:].strip()
            if content.startswith("//") or content.startswith("#") or content.startswith("/*") or content.startswith("*"):
                comment_count += 1
                comment_lines.append(f"{current_file}: {content[:60]}")

    if comment_count > 20:
        alerts.append({
            "type": "info",
            "file": "(multiplos arquivos)",
            "msg": f"Muitos comentarios adicionados ({comment_count}). Verifique se sao realmente necessarios.",
            "lines": comment_count,
        })
    return alerts


def detect_simple_duplication(diff_text, threshold=4):
    alerts = []
    added_lines = []
    current_file = None
    line_map = []

    for line in diff_text.splitlines():
        if line.startswith("+++ b/"):
            current_file = line[6:]
        if line.startswith("+") and not line.startswith("+++"):
            content = line[1:].strip()
            if len(content) > 20:
                added_lines.append(content)
                line_map.append(current_file or "?")

    dup_counter = collections.Counter(added_lines)
    for line_text, count in dup_counter.items():
        if count >= threshold:
            files_involved = list(set(
                line_map[i] for i, t in enumerate(added_lines) if t == line_text
            ))
            alerts.append({
                "type": "warning",
                "file": ", ".join(files_involved),
                "msg": f"Linha duplicada {count}x: \"{line_text[:60]}\"",
                "lines": count,
            })

    return alerts


def detect_large_files(numstat_files):
    alerts = []
    for f in numstat_files:
        total = f["added"] + f["removed"]
        if total > MAX_LINES_PER_FILE:
            alerts.append({
                "type": "warning",
                "file": f["path"],
                "msg": f"Arquivo muito alterado: +{f['added']}/-{f['removed']} linhas (total: {total}, limite: {MAX_LINES_PER_FILE})",
                "lines": total,
            })
    return alerts


def get_git_diff_context(diff_text):
    result = []
    for line in diff_text.splitlines():
        if line.startswith("diff --git") or line.startswith("---") or line.startswith("+++"):
            result.append(line)
        elif line.startswith("+") and not line.startswith("+++"):
            result.append(line)
        elif line.startswith("-") and not line.startswith("---"):
            result.append(line)
        elif line.startswith("@@"):
            result.append(line)
    return "\n".join(result)


def generate_html(results):
    now = datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    diff_preview_lines = results.get("diff_preview", "").splitlines()
    diff_preview_truncated = "\n".join(diff_preview_lines[:200])
    if len(diff_preview_lines) > 200:
        diff_preview_truncated += f"\n\n... (+{len(diff_preview_lines) - 200} linhas omitidas)"

    def esc(text):
        return html.escape(text)

    def render_alerts(alerts, alert_type):
        if not alerts:
            return '<p class="none">Nenhum alerta.</p>'
        items = []
        for a in alerts:
            items.append(f"""<div class="alert alert-{alert_type}">
                <div class="alert-header">
                    <span class="alert-badge {alert_type}">{alert_type.upper()}</span>
                    <span class="alert-file">{esc(a.get("file", "?"))}</span>
                </div>
                <div class="alert-body">
                    <p>{esc(a["msg"])}</p>
                </div>
            </div>""")
        return "\n".join(items)

    prompt = """Atue como **Coder** (arquivo .ai-flow/agents/coder.md).

Corrija os problemas apontados pelo Quality Gate e pelo Reviewer:

[INSIRA AQUI OS PROBLEMAS APONTADOS PELO REVIEWER]

Regras:
- Mantenha o estilo do projeto
- Nao refatore alem do necessario
- Nao altere arquivos fora do escopo
- Nao faca commit automatico
- Uma mudanca por vez
"""

    total_critical = len(results.get("critical", []))
    total_warnings = len(results.get("warnings", []))
    total_info = len(results.get("info", []))
    total_alerts = total_critical + total_warnings + total_info

    files_data = results.get("files", [])
    total_added = sum(f.get("added", 0) for f in files_data)
    total_removed = sum(f.get("removed", 0) for f in files_data)
    total_files = len(files_data)

    if total_alerts == 0:
        score = 10
        score_color = "#22c55e"
    elif total_critical == 0 and total_warnings <= 2:
        score = 8
        score_color = "#22c55e"
    elif total_critical == 0 and total_warnings <= 5:
        score = 6
        score_color = "#eab308"
    elif total_critical <= 2:
        score = 4
        score_color = "#f97316"
    else:
        score = 2
        score_color = "#ef4444"

    html_content = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Quality Gate Report</title>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
    background: #0f172a;
    color: #e2e8f0;
    padding: 20px;
    line-height: 1.6;
}}
.container {{ max-width: 1100px; margin: 0 auto; }}
.header {{
    background: linear-gradient(135deg, #1e293b 0%, #334155 100%);
    border-radius: 12px;
    padding: 30px;
    margin-bottom: 24px;
    border: 1px solid #334155;
}}
.header h1 {{
    font-size: 28px;
    color: #f8fafc;
    margin-bottom: 8px;
    display: flex;
    align-items: center;
    gap: 10px;
}}
.header .subtitle {{
    color: #94a3b8;
    font-size: 14px;
}}
.score-card {{
    background: #1e293b;
    border-radius: 12px;
    padding: 24px;
    margin-bottom: 24px;
    border: 1px solid #334155;
    text-align: center;
}}
.score-number {{
    font-size: 64px;
    font-weight: 800;
    color: {score_color};
    line-height: 1;
}}
.score-label {{
    color: #94a3b8;
    font-size: 14px;
    margin-top: 4px;
}}
.summary-grid {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
    gap: 16px;
    margin-bottom: 24px;
}}
.summary-card {{
    background: #1e293b;
    border-radius: 8px;
    padding: 20px;
    border: 1px solid #334155;
    text-align: center;
}}
.summary-card .value {{
    font-size: 36px;
    font-weight: 700;
    color: #60a5fa;
}}
.summary-card .label {{
    color: #94a3b8;
    font-size: 13px;
    margin-top: 4px;
}}
.summary-card.red .value {{ color: #ef4444; }}
.summary-card.yellow .value {{ color: #eab308; }}
.summary-card.green .value {{ color: #22c55e; }}
.summary-card.blue .value {{ color: #60a5fa; }}
.section {{
    background: #1e293b;
    border-radius: 12px;
    padding: 24px;
    margin-bottom: 24px;
    border: 1px solid #334155;
}}
.section h2 {{
    font-size: 20px;
    color: #f8fafc;
    margin-bottom: 16px;
    padding-bottom: 8px;
    border-bottom: 1px solid #334155;
}}
.alert {{
    border-radius: 8px;
    padding: 16px;
    margin-bottom: 12px;
    border-left: 4px solid;
}}
.alert.alert-critical {{
    background: rgba(239, 68, 68, 0.1);
    border-color: #ef4444;
}}
.alert.alert-warning {{
    background: rgba(234, 179, 8, 0.1);
    border-color: #eab308;
}}
.alert.alert-info {{
    background: rgba(96, 165, 250, 0.1);
    border-color: #60a5fa;
}}
.alert-header {{
    display: flex;
    align-items: center;
    gap: 12px;
    margin-bottom: 8px;
}}
.alert-badge {{
    font-size: 11px;
    font-weight: 700;
    padding: 2px 8px;
    border-radius: 4px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}}
.alert-badge.critical {{ background: #ef4444; color: white; }}
.alert-badge.warning {{ background: #eab308; color: #1e293b; }}
.alert-badge.info {{ background: #60a5fa; color: #1e293b; }}
.alert-file {{
    font-size: 13px;
    color: #94a3b8;
    font-family: "SF Mono", "Fira Code", monospace;
}}
.alert-body p {{
    color: #cbd5e1;
    font-size: 14px;
}}
.none {{
    color: #64748b;
    font-style: italic;
    font-size: 14px;
}}
.file-table {{
    width: 100%;
    border-collapse: collapse;
    font-size: 14px;
}}
.file-table th {{
    text-align: left;
    padding: 10px 12px;
    color: #94a3b8;
    font-size: 12px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    border-bottom: 1px solid #334155;
}}
.file-table td {{
    padding: 10px 12px;
    border-bottom: 1px solid #1e293b;
    color: #cbd5e1;
}}
.file-table tr:hover td {{ background: rgba(255,255,255,0.03); }}
.file-table .added {{ color: #22c55e; }}
.file-table .removed {{ color: #ef4444; }}
.diff-preview {{
    background: #0f172a;
    border-radius: 8px;
    padding: 16px;
    overflow-x: auto;
    font-family: "SF Mono", "Fira Code", "Consolas", monospace;
    font-size: 13px;
    line-height: 1.5;
    white-space: pre-wrap;
    word-break: break-all;
    color: #cbd5e1;
    max-height: 400px;
    overflow-y: auto;
}}
.diff-preview .added {{ color: #22c55e; }}
.diff-preview .removed {{ color: #ef4444; }}
.prompt-box {{
    background: #0f172a;
    border-radius: 8px;
    padding: 20px;
    border: 1px solid #60a5fa;
    font-family: "SF Mono", "Fira Code", monospace;
    font-size: 13px;
    white-space: pre-wrap;
    word-break: break-word;
    color: #cbd5e1;
    margin-top: 8px;
    max-height: 300px;
    overflow-y: auto;
}}
.copy-hint {{
    color: #64748b;
    font-size: 12px;
    margin-top: 8px;
    text-align: right;
}}
.footer {{
    text-align: center;
    color: #64748b;
    font-size: 12px;
    padding: 20px;
}}
.bar-chart {{
    display: flex;
    align-items: center;
    gap: 6px;
}}
.bar {{
    height: 6px;
    border-radius: 3px;
    background: #334155;
    flex: 1;
}}
.bar-fill {{
    height: 6px;
    border-radius: 3px;
}}
.bar-fill.green {{ background: #22c55e; }}
.bar-fill.yellow {{ background: #eab308; }}
.bar-fill.red {{ background: #ef4444; }}
</style>
</head>
<body>
<div class="container">

    <div class="header">
        <h1>Quality Gate Report</h1>
        <div class="subtitle">
            Gerado em {esc(now)} |
            Branch: {esc(results.get("branch", "?"))} |
            Ultimo commit: {esc(results.get("last_commit", "?"))[:12]}
        </div>
    </div>

    <div class="score-card">
        <div class="score-number">{score}/10</div>
        <div class="score-label">
            Qualidade geral
            {" - Excelente" if score >= 9 else ""}
            {" - Boa" if 7 <= score < 9 else ""}
            {" - Regular" if 5 <= score < 7 else ""}
            {" - Ruim" if 3 <= score < 5 else ""}
            {" - Critica" if score < 3 else ""}
        </div>
    </div>

    <div class="summary-grid">
        <div class="summary-card blue">
            <div class="value">{total_files}</div>
            <div class="label">Arquivos alterados</div>
        </div>
        <div class="summary-card green">
            <div class="value">+{total_added}</div>
            <div class="label">Linhas adicionadas</div>
        </div>
        <div class="summary-card red">
            <div class="value">{total_removed}</div>
            <div class="label">Linhas removidas</div>
        </div>
        <div class="summary-card red" class="red">
            <div class="value">{total_critical}</div>
            <div class="label">Alertas criticos</div>
        </div>
        <div class="summary-card yellow">
            <div class="value">{total_warnings}</div>
            <div class="label">Alertas importantes</div>
        </div>
        <div class="summary-card blue">
            <div class="value">{total_info}</div>
            <div class="label">Melhorias opcionais</div>
        </div>
    </div>

    <div class="section">
        <h2>Arquivos alterados</h2>
        <table class="file-table">
            <thead>
                <tr>
                    <th>Arquivo</th>
                    <th style="width:80px;text-align:right;">Adicionadas</th>
                    <th style="width:80px;text-align:right;">Removidas</th>
                    <th style="width:150px;">Impacto</th>
                </tr>
            </thead>
            <tbody>
"""
    for f in files_data:
        total_f = f["added"] + f["removed"]
        bar_pct = min(total_f / max(total_f for f2 in files_data) * 100, 100) if files_data else 0
        bar_color = "green" if total_f < 50 else "yellow" if total_f < 150 else "red"
        html_content += f"""
                <tr>
                    <td>{esc(f["path"])}</td>
                    <td style="text-align:right;color:#22c55e;">+{f["added"]}</td>
                    <td style="text-align:right;color:#ef4444;">-{f["removed"]}</td>
                    <td>
                        <div class="bar-chart">
                            <div class="bar">
                                <div class="bar-fill {bar_color}" style="width:{bar_pct}%;"></div>
                            </div>
                            <span style="font-size:12px;color:#94a3b8;">{total_f}</span>
                        </div>
                    </td>
                </tr>"""

    html_content += """
            </tbody>
        </table>
    </div>

    <div class="section">
        <h2>Alertas criticos</h2>
"""
    html_content += render_alerts(results.get("critical", []), "critical")
    html_content += """
    </div>

    <div class="section">
        <h2>Alertas importantes</h2>
"""
    html_content += render_alerts(results.get("warnings", []), "warning")
    html_content += """
    </div>

    <div class="section">
        <h2>Melhorias opcionais</h2>
"""
    html_content += render_alerts(results.get("info", []), "info")
    html_content += """
    </div>

    <div class="section">
        <h2>Preview do diff</h2>
        <div class="diff-preview">
"""
    html_content += esc(diff_preview_truncated)
    html_content += """
        </div>
    </div>

    <div class="section">
        <h2>Prompt para correcao</h2>
        <p style="color:#94a3b8;font-size:14px;margin-bottom:12px;">
            Copie o prompt abaixo e envie ao agente <strong>Coder</strong>
            para corrigir os problemas apontados.
        </p>
        <div class="prompt-box">
"""
    html_content += esc(prompt)
    html_content += """
        </div>
        <div class="copy-hint">Selecione e copie o texto acima</div>
    </div>

    <div class="footer">
        AI-Flow Quality Gate &mdash; .ai-flow/scripts/quality-gate.py
    </div>

</div>
</body>
</html>"""
    return html_content


def main():
    print("=== AI-Flow: Quality Gate ===\n")

    # Branch info
    branch, _, _ = run_cmd(["git", "rev-parse", "--abbrev-ref", "HEAD"])
    branch = branch.strip() or "?"
    last_commit, _, _ = run_cmd(["git", "log", "--oneline", "-1"])
    last_commit = last_commit.strip() or "?" if last_commit.strip() else "?"

    print(f"[1/4] Obtendo git diff...")
    diff_text = get_git_diff()
    numstat_text = get_git_numstat()
    stat_text = get_git_diff_stat()

    if not diff_text.strip():
        print("[!] Nenhuma alteracao no working tree. Tentando diff do ultimo commit...")
        diff_text, _, _ = run_cmd(["git", "diff", "HEAD~1"])
        numstat_text, _, _ = run_cmd(["git", "diff", "--numstat", "HEAD~1"])
        stat_text, _, _ = run_cmd(["git", "diff", "--stat", "HEAD~1"])

        if not diff_text.strip():
            print("[!] Nenhum diff encontrado (nem working tree, nem commit anterior).")
            print("    O relatorio sera gerado vazio.\n")

    print(f"[2/4] Analisando alteracoes...")
    files = parse_numstat(numstat_text)

    all_alerts = {"critical": [], "warnings": [], "info": []}

    # Critical alerts
    all_alerts["critical"].extend(detect_large_files(files))

    # Warning alerts
    all_alerts["warnings"].extend(detect_long_lines(diff_text))
    all_alerts["warnings"].extend(detect_long_functions(diff_text))
    all_alerts["warnings"].extend(detect_simple_duplication(diff_text))

    # Info alerts
    all_alerts["info"].extend(detect_todos_fixmes(diff_text))
    all_alerts["info"].extend(detect_prints_logs(diff_text))
    all_alerts["info"].extend(detect_added_comments(diff_text))

    print(f"   - Arquivos alterados: {len(files)}")
    print(f"   - Alertas criticos: {len(all_alerts['critical'])}")
    print(f"   - Alertas importantes: {len(all_alerts['warnings'])}")
    print(f"   - Melhorias opcionais: {len(all_alerts['info'])}")

    print(f"[3/4] Montando relatorio HTML...")
    diff_preview = get_git_diff_context(diff_text)

    results = {
        "branch": branch,
        "last_commit": last_commit,
        "files": files,
        "critical": all_alerts["critical"],
        "warnings": all_alerts["warnings"],
        "info": all_alerts["info"],
        "diff_preview": diff_preview[:50000],
    }

    html_output = generate_html(results)

    print(f"[4/4] Salvando relatorio...")
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text(html_output, encoding="utf-8")

    abs_path = OUTPUT_FILE.resolve()
    print(f"\n[OK] Relatorio gerado em:")
    print(f"     {abs_path}")
    print(f"\nDica: abra o arquivo no navegador ou execute:")
    print(f"  .ai-flow\\scripts\\run-quality-gate.ps1")

    return 0


if __name__ == "__main__":
    sys.exit(main())
