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

BASE_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = BASE_DIR.parent

# Valores padrao case nao haja config
DEFAULT_SENSITIVE_PATTERNS = [
    "migrations/",
    ".env",
    ".env.local",
    ".env.production",
    "config/database.yml",
    "docker-compose.yml",
    "secrets/",
]
DEFAULT_BLOCK_EXTENSIONS = [".exe", ".dll", ".so", ".dylib", ".bin"]

SECRET_PATTERNS = [
    r"token\s*=",
    r"api_key\s*=",
    r"secret\s*=",
    r"password\s*=",
    r"private_key",
    r"bearer",
]

FALSE_POSITIVE_KEYWORDS = ["example", "placeholder", "your_token_here", "fake", "dummy"]


def load_config():
    config_path = BASE_DIR / "config.json"
    if not config_path.exists():
        config_path = BASE_DIR / "config.example.json"
    try:
        import json
        with open(config_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        qg = cfg.get("quality_gate", {})
        return {
            "sensitive_patterns": qg.get("sensitive_patterns", DEFAULT_SENSITIVE_PATTERNS),
            "block_extensions": qg.get("block_extensions", DEFAULT_BLOCK_EXTENSIONS),
        }
    except Exception:
        return {
            "sensitive_patterns": DEFAULT_SENSITIVE_PATTERNS,
            "block_extensions": DEFAULT_BLOCK_EXTENSIONS,
        }


def run_cmd(cmd, cwd=None):
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
            encoding="utf-8",
            errors="replace",
            cwd=str(cwd) if cwd else str(REPO_ROOT),
        )
        return result.stdout, result.stderr, result.returncode
    except FileNotFoundError:
        return "", "Comando nao encontrado: " + " ".join(cmd), -1


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
    for idx, line in enumerate(diff_text.splitlines(), 1):
        if line.startswith("+++ b/"):
            last_file = line[6:]
        if idx >= approx_line:
            break
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


def detect_sensitive_files(files, sensitive_patterns=None):
    if sensitive_patterns is None:
        sensitive_patterns = DEFAULT_SENSITIVE_PATTERNS
    alerts = []
    for f in files:
        path = f["path"]
        for pattern in sensitive_patterns:
            if pattern in path:
                alerts.append({
                    "type": "critical",
                    "file": path,
                    "msg": f"Arquivo sensivel detectado: {path} corresponde ao padrao \"{pattern}\"",
                    "lines": f["added"] + f["removed"],
                })
                break
    return alerts


def detect_blocked_extensions(files, block_extensions=None):
    if block_extensions is None:
        block_extensions = DEFAULT_BLOCK_EXTENSIONS
    alerts = []
    for f in files:
        path = f["path"]
        for ext in block_extensions:
            if path.endswith(ext):
                alerts.append({
                    "type": "critical",
                    "file": path,
                    "msg": f"Extensao bloqueada detectada: {path} (extensao: {ext})",
                    "lines": f["added"] + f["removed"],
                })
                break
    return alerts


def detect_possible_secrets(diff_text):
    alerts = []
    current_file = None

    for line in diff_text.splitlines():
        if line.startswith("+++ b/"):
            current_file = line[6:]
        if not line.startswith("+") or line.startswith("+++"):
            continue

        content = line[1:].strip()

        # Ignorar falsos positivos
        if any(kw in content.lower() for kw in FALSE_POSITIVE_KEYWORDS):
            continue

        for pattern in SECRET_PATTERNS:
            match = re.search(pattern, content, re.IGNORECASE)
            if match:
                # Mascarar o valor apos o sinal de igual ou o restante da linha
                masked = _mask_secret_line(content, pattern)
                alerts.append({
                    "type": "critical",
                    "file": current_file or "?",
                    "msg": f"Possivel secret encontrado: {masked}",
                    "lines": 1,
                })
                break
    return alerts


def _mask_secret_line(content, pattern):
    """Mascara o valor de um possivel secret na linha."""
    eq_match = re.search(r"(=)\s*\S+", content)
    if eq_match:
        before_eq = content[:eq_match.start(1) + 1]
        return f"{before_eq}<masked>"
    # Se for private_key ou bearer sem sinal de igual, mascarar a palavra em si
    if re.search(r"(private_key|bearer)\s+\S+", content, re.IGNORECASE):
        return re.sub(r"(private_key|bearer)\s+\S+", r"\1 <masked>", content, flags=re.IGNORECASE)
    return content


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


def looks_like_code_file(path):
    suffix = Path(path).suffix.lower()
    return suffix in {
        ".py", ".js", ".jsx", ".ts", ".tsx", ".java", ".kt", ".cs", ".go", ".rb",
        ".php", ".rs", ".c", ".cc", ".cpp", ".h", ".hpp", ".css", ".scss", ".html",
    }


def looks_like_test_file(path):
    name = Path(path).name.lower()
    path_lower = path.lower().replace("\\", "/")
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
        or "/tests/" in path_lower
        or "/__tests__/" in path_lower
    )


def looks_like_manifest_file(path):
    name = Path(path).name.lower()
    return name in {
        "package.json",
        "package-lock.json",
        "pnpm-lock.yaml",
        "yarn.lock",
        "requirements.txt",
        "pyproject.toml",
        "poetry.lock",
        "pom.xml",
        "build.gradle",
        "build.gradle.kts",
        "cargo.toml",
        "go.mod",
    }


def collect_git_diff():
    inside, _, rc = run_cmd(["git", "rev-parse", "--is-inside-work-tree"], cwd=REPO_ROOT)
    if rc != 0 or inside.strip().lower() != "true":
        return {
            "branch": "?",
            "last_commit": "?",
            "diff_text": "",
            "numstat_text": "",
            "stat_text": "",
            "source_label": "git indisponivel",
            "git_available": False,
        }

    branch, _, _ = run_cmd(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=REPO_ROOT)
    last_commit, _, _ = run_cmd(["git", "log", "--oneline", "-1"], cwd=REPO_ROOT)

    staged_diff, _, _ = run_cmd(["git", "diff", "--cached"], cwd=REPO_ROOT)
    unstaged_diff, _, _ = run_cmd(["git", "diff"], cwd=REPO_ROOT)
    staged_numstat, _, _ = run_cmd(["git", "diff", "--cached", "--numstat"], cwd=REPO_ROOT)
    unstaged_numstat, _, _ = run_cmd(["git", "diff", "--numstat"], cwd=REPO_ROOT)
    staged_stat, _, _ = run_cmd(["git", "diff", "--cached", "--stat"], cwd=REPO_ROOT)
    unstaged_stat, _, _ = run_cmd(["git", "diff", "--stat"], cwd=REPO_ROOT)

    diff_parts = [part for part in [staged_diff, unstaged_diff] if part.strip()]
    numstat_parts = [part for part in [staged_numstat, unstaged_numstat] if part.strip()]
    stat_parts = [part for part in [staged_stat, unstaged_stat] if part.strip()]

    return {
        "branch": branch.strip() or "?",
        "last_commit": last_commit.strip() or "?",
        "diff_text": "\n".join(diff_parts).strip(),
        "numstat_text": "\n".join(numstat_parts).strip(),
        "stat_text": "\n".join(stat_parts).strip(),
        "source_label": "working tree + staged",
        "git_available": True,
    }


def detect_dangerous_commands(diff_text):
    alerts = []
    patterns = [
        (r"\brm\s+-rf\b", "rm -rf"),
        (r"\brmdir\s+/s\b", "rmdir /s"),
        (r"\bdel\s+/s\b", "del /s"),
        (r"\bformat\s+[a-z]:", "format c:"),
        (r"git\s+push\s+--force", "git push --force"),
        (r"curl\s+.*\|\s*sh", "curl | sh"),
        (r"wget\s+.*\|\s*sh", "wget | sh"),
        (r"invoke-webrequest.*\|.*invoke-expression", "Invoke-WebRequest | Invoke-Expression"),
        (r"\beval\s*\(", "eval()"),
        (r"\bexec\s*\(", "exec()"),
        (r"os\.system\s*\(", "os.system()"),
        (r"shell\s*=\s*True", "shell=True"),
    ]
    current_file = None
    for line in diff_text.splitlines():
        if line.startswith("+++ b/"):
            current_file = line[6:]
        if not line.startswith("+") or line.startswith("+++"):
            continue
        content = line[1:].strip()
        for pattern, label in patterns:
            if re.search(pattern, content, re.IGNORECASE):
                alerts.append({
                    "type": "warning",
                    "file": current_file or "?",
                    "msg": f"Comando potencialmente perigoso detectado: {label}",
                    "lines": 1,
                })
                break
    return alerts


def detect_new_dependencies(files, diff_text):
    alerts = []
    current_file = None
    added_lines = {}
    for line in diff_text.splitlines():
        if line.startswith("+++ b/"):
            current_file = line[6:]
        if line.startswith("+") and not line.startswith("+++"):
            added_lines.setdefault(current_file or "?", []).append(line[1:].strip())

    for file_data in files:
        path = file_data["path"]
        name = Path(path).name.lower()
        if name == "package.json":
            deps = []
            for line in added_lines.get(path, []):
                match = re.match(r'^"([^"]+)"\s*:\s*"([^"]+)"', line)
                if match and match.group(1) not in {"name", "version", "scripts", "dependencies", "devDependencies", "peerDependencies", "optionalDependencies", "workspaces"}:
                    deps.append(f"{match.group(1)}@{match.group(2)}")
            if deps:
                alerts.append({
                    "type": "info",
                    "file": path,
                    "msg": f"Dependencias adicionadas ou alteradas: {', '.join(deps[:6])}",
                    "lines": len(deps),
                })
            elif file_data["added"] + file_data["removed"] > 0:
                alerts.append({
                    "type": "info",
                    "file": path,
                    "msg": "package.json alterado; revise dependencias e scripts",
                    "lines": file_data["added"] + file_data["removed"],
                })
        elif name in {"requirements.txt", "poetry.lock", "go.mod", "pom.xml", "build.gradle", "build.gradle.kts"}:
            if file_data["added"] + file_data["removed"] > 0:
                alerts.append({
                    "type": "info",
                    "file": path,
                    "msg": f"Arquivo de dependencia alterado: {name}",
                    "lines": file_data["added"] + file_data["removed"],
                })
    return alerts


def detect_missing_tests(files):
    has_code = any(looks_like_code_file(f["path"]) and not looks_like_test_file(f["path"]) for f in files)
    has_tests = any(looks_like_test_file(f["path"]) for f in files)
    if has_code and not has_tests:
        return [{
            "type": "warning",
            "file": "(multiplos arquivos)",
            "msg": "Codigo alterado sem testes correspondentes no diff.",
            "lines": 1,
        }]
    return []


def build_coder_prompt(results):
    critical = results.get("critical", [])
    warnings = results.get("warnings", [])
    info = results.get("info", [])
    lines = [
        "Atue como **Coder** (arquivo .ai-flow/agents/coder.md).",
        "",
        "Corrija os problemas apontados pelo Quality Gate e pelo Reviewer:",
        "",
        "## Pontos criticos",
    ]
    if critical:
        for item in critical:
            lines.append(f"- {item.get('file', '?')}: {item.get('msg', '')}")
    else:
        lines.append("- nenhum")
    lines.extend(["", "## Pontos importantes"])
    if warnings:
        for item in warnings:
            lines.append(f"- {item.get('file', '?')}: {item.get('msg', '')}")
    else:
        lines.append("- nenhum")
    lines.extend(["", "## Melhorias opcionais"])
    if info:
        for item in info:
            lines.append(f"- {item.get('file', '?')}: {item.get('msg', '')}")
    else:
        lines.append("- nenhum")
    lines.extend([
        "",
        "Regras:",
        "- Mantenha o estilo do projeto",
        "- Nao refatore alem do necessario",
        "- Nao altere arquivos fora do escopo",
        "- Nao faca commit automatico",
        "- Uma mudanca por vez",
    ])
    return "\n".join(lines)


def generate_html(results):
    now = datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    diff_lines = results.get("diff_preview", "").splitlines()
    source_label = results.get("source_label", "working tree")

    def esc(text):
        return html.escape(text)

    def render_alerts(alerts, alert_type):
        if not alerts:
            return '<p class="qg-none">Nenhum alerta.</p>'
        severity_icon = {"critical": "!", "warning": "!", "info": "i"}.get(alert_type, "?")
        items = []
        for a in alerts:
            items.append(f"""<div class="qg-alert qg-alert-{alert_type}">
                <div class="qg-alert-header">
                    <span class="qg-alert-icon qg-icon-{alert_type}">{severity_icon}</span>
                    <span class="qg-alert-badge qg-badge-{alert_type}">{alert_type.upper()}</span>
                    <span class="qg-alert-file">{esc(a.get("file", "?"))}</span>
                </div>
                <div class="qg-alert-body">
                    <p>{esc(a["msg"])}</p>
                </div>
            </div>""")
        return "\n".join(items)

    def render_diff_html(lines, max_lines=200):
        truncated = lines[:max_lines]
        out = []
        for line in truncated:
            if line.startswith("+") and not line.startswith("+++"):
                out.append(f'<span class="qg-diff-add">{esc(line)}</span>')
            elif line.startswith("-") and not line.startswith("---"):
                out.append(f'<span class="qg-diff-remove">{esc(line)}</span>')
            elif line.startswith("@@"):
                out.append(f'<span class="qg-diff-hunk">{esc(line)}</span>')
            else:
                out.append(esc(line))
        result = "\n".join(out)
        if len(lines) > max_lines:
            result += f'\n<div class="qg-diff-omit">... (+{len(lines) - max_lines} linhas omitidas)</div>'
        return result

    critical_items = list(results.get("critical", [])) + list(results.get("dangerous_commands", []))
    warning_items = list(results.get("warnings", [])) + list(results.get("missing_tests", []))
    info_items = list(results.get("info", [])) + list(results.get("new_dependencies", []))

    prompt = results.get("coder_prompt") or build_coder_prompt({
        "critical": critical_items,
        "warnings": warning_items,
        "info": info_items,
    })

    total_critical = len(critical_items)
    total_warnings = len(warning_items)
    total_info = len(info_items)
    total_alerts = total_critical + total_warnings + total_info

    files_data = results.get("files", [])
    total_added = sum(f.get("added", 0) for f in files_data)
    total_removed = sum(f.get("removed", 0) for f in files_data)
    total_files = len(files_data)

    if total_alerts == 0:
        score = 10
        score_class = "qg-score-pass"
        status_label = "Aprovado"
        status_icon = "P"
    elif total_critical == 0 and total_warnings <= 2:
        score = 8
        score_class = "qg-score-pass"
        status_label = "Aprovado"
        status_icon = "P"
    elif total_critical == 0 and total_warnings <= 5:
        score = 6
        score_class = "qg-score-conditional"
        status_label = "Aprovado com ressalvas"
        status_icon = "!"
    elif total_critical <= 2:
        score = 4
        score_class = "qg-score-fail"
        status_label = "Reprovado"
        status_icon = "X"
    else:
        score = 2
        score_class = "qg-score-fail"
        status_label = "Reprovado"
        status_icon = "X"

    def next_steps_html():
        steps = []
        steps.append("<ul class=\"qg-steps\">")
        if score < 5:
            steps.append("<li>Corrija os <strong>alertas criticos</strong> — arquivos muito alterados comprometem a qualidade.</li>")
            steps.append("<li>Refatore arquivos grandes em modulos menores.</li>")
            steps.append("<li>Execute o linter e os testes apos cada correcao.</li>")
            steps.append("<li>Reexecute o Quality Gate para validar a melhoria.</li>")
        elif score < 8:
            steps.append("<li>Analise os <strong>alertas importantes</strong> e reduza duplicacoes.</li>")
            steps.append("<li>Extraia funcoes grandes em unidades menores e reutilizaveis.</li>")
            steps.append("<li>Remova comentarios excessivos e codigo morto.</li>")
            steps.append("<li>Reexecute o Quality Gate apos as correcoes.</li>")
        else:
            steps.append("<li>Qualidade dentro do esperado. Continue mantendo as praticas atuais.</li>")
            steps.append("<li>Revise alertas opcionais para melhoria continua.</li>")
        steps.append("</ul>")
        return "\n".join(steps)

    html_content = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Quality Gate Report {esc(results.get("branch", ""))}</title>
<link rel="stylesheet" href="../assets/ai-flow-theme.css">
<style>
/* ============================================================
   Quality Gate Report — Visual Improvements
   Built on AI-Flow Theme tokens
   ============================================================ */

/* --- Layout ------------------------------------------------ */
.qg-wrap {{
    max-width: 1100px;
    margin: 0 auto;
    padding: 20px;
}}

/* --- Header ------------------------------------------------ */
.qg-header {{
    background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
    border: 1px solid var(--af-border);
    border-radius: var(--af-radius-lg);
    padding: var(--af-space-xl);
    margin-bottom: var(--af-space-lg);
    position: relative;
    overflow: hidden;
}}
.qg-header::after {{
    content: '';
    position: absolute;
    top: -50%;
    right: -20%;
    width: 300px;
    height: 300px;
    background: radial-gradient(circle, rgba(168,85,247,0.08) 0%, transparent 70%);
    pointer-events: none;
}}
.qg-header-badge {{
    display: inline-flex;
    align-items: center;
    gap: var(--af-space-xs);
    padding: 3px 12px;
    border-radius: var(--af-radius-full);
    font-size: var(--af-text-xs);
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    background: var(--af-primary-glow);
    color: var(--af-primary);
    margin-bottom: var(--af-space-sm);
}}
.qg-header h1 {{
    font-size: var(--af-text-2xl);
    font-weight: 700;
    color: var(--af-text-bright);
    margin-bottom: var(--af-space-xs);
    letter-spacing: -0.02em;
}}
.qg-header-meta {{
    display: flex;
    flex-wrap: wrap;
    gap: var(--af-space-md);
    color: var(--af-text-muted);
    font-size: var(--af-text-sm);
    margin-top: var(--af-space-sm);
}}
.qg-header-meta span {{
    display: inline-flex;
    align-items: center;
    gap: var(--af-space-xs);
}}

/* --- Score + Status ---------------------------------------- */
.qg-score-wrap {{
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: var(--af-space-md);
    margin-bottom: var(--af-space-lg);
}}
@media (max-width: 600px) {{
    .qg-score-wrap {{
        grid-template-columns: 1fr;
    }}
}}
.qg-score-card {{
    background: var(--af-bg-raised);
    border: 1px solid var(--af-border);
    border-radius: var(--af-radius-lg);
    padding: var(--af-space-xl);
    text-align: center;
}}
.qg-score-number {{
    font-size: 72px;
    font-weight: 800;
    line-height: 1;
    color: var(--af-text-bright);
}}
.qg-score-pass .qg-score-number {{ color: var(--af-success); }}
.qg-score-conditional .qg-score-number {{ color: var(--af-warning); }}
.qg-score-fail .qg-score-number {{ color: var(--af-error); }}
.qg-score-label {{
    font-size: var(--af-text-md);
    color: var(--af-text-muted);
    margin-top: var(--af-space-xs);
}}

.qg-status-card {{
    background: var(--af-bg-raised);
    border: 1px solid var(--af-border);
    border-radius: var(--af-radius-lg);
    padding: var(--af-space-xl);
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: var(--af-space-sm);
}}
.qg-status-icon {{
    width: 64px;
    height: 64px;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 28px;
    font-weight: 800;
    line-height: 1;
}}
.qg-status-pass .qg-status-icon {{
    background: var(--af-success-bg);
    color: var(--af-success);
    border: 2px solid var(--af-success);
}}
.qg-status-conditional .qg-status-icon {{
    background: var(--af-warning-bg);
    color: var(--af-warning);
    border: 2px solid var(--af-warning);
}}
.qg-status-fail .qg-status-icon {{
    background: var(--af-error-bg);
    color: var(--af-error);
    border: 2px solid var(--af-error);
}}
.qg-status-label {{
    font-size: var(--af-text-lg);
    font-weight: 600;
    color: var(--af-text-bright);
}}
.qg-status-detail {{
    font-size: var(--af-text-sm);
    color: var(--af-text-muted);
}}

/* --- Summary Grid ------------------------------------------ */
.qg-summary-grid {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
    gap: var(--af-space-md);
    margin-bottom: var(--af-space-lg);
}}
.qg-summary-card {{
    text-align: center;
    padding: var(--af-space-md);
    background: var(--af-bg-raised);
    border: 1px solid var(--af-border);
    border-radius: var(--af-radius-md);
    transition: border-color var(--af-duration-base) var(--af-ease-out);
}}
.qg-summary-card:hover {{
    border-color: var(--af-border-hover);
}}
.qg-summary-value {{
    font-size: var(--af-text-3xl);
    font-weight: 700;
    line-height: 1.2;
}}
.qg-summary-label {{
    font-size: var(--af-text-sm);
    color: var(--af-text-muted);
    margin-top: var(--af-space-xs);
}}
.qg-summary-card.color-files .qg-summary-value {{ color: var(--af-primary); }}
.qg-summary-card.color-added .qg-summary-value {{ color: var(--af-success); }}
.qg-summary-card.color-removed .qg-summary-value {{ color: var(--af-error); }}
.qg-summary-card.color-critical .qg-summary-value {{ color: var(--af-error); }}
.qg-summary-card.color-warnings .qg-summary-value {{ color: var(--af-warning); }}
.qg-summary-card.color-info .qg-summary-value {{ color: var(--af-info); }}

/* --- Section ------------------------------------------------- */
.qg-section {{
    background: var(--af-bg-raised);
    border: 1px solid var(--af-border);
    border-radius: var(--af-radius-lg);
    padding: var(--af-space-lg);
    margin-bottom: var(--af-space-lg);
}}
.qg-section-title {{
    font-size: var(--af-text-xl);
    font-weight: 600;
    color: var(--af-text-bright);
    padding-bottom: var(--af-space-sm);
    margin-bottom: var(--af-space-md);
    border-bottom: 1px solid var(--af-border);
    display: flex;
    align-items: center;
    gap: var(--af-space-sm);
}}

/* --- Alerts -------------------------------------------------- */
.qg-alert {{
    border-radius: var(--af-radius-md);
    padding: var(--af-space-md);
    margin-bottom: var(--af-space-sm);
    border-left: 4px solid;
}}
.qg-alert-critical {{
    background: var(--af-error-bg);
    border-color: var(--af-error);
}}
.qg-alert-warning {{
    background: var(--af-warning-bg);
    border-color: var(--af-warning);
}}
.qg-alert-info {{
    background: var(--af-info-bg);
    border-color: var(--af-info);
}}
.qg-alert-header {{
    display: flex;
    align-items: center;
    gap: var(--af-space-sm);
    margin-bottom: var(--af-space-xs);
}}
.qg-alert-icon {{
    width: 20px;
    height: 20px;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 11px;
    font-weight: 700;
    flex-shrink: 0;
}}
.qg-icon-critical {{ background: var(--af-error); color: #fff; }}
.qg-icon-warning {{ background: var(--af-warning); color: #1e293b; }}
.qg-icon-info {{ background: var(--af-info); color: #1e293b; }}
.qg-alert-badge {{
    display: inline-flex;
    padding: 2px 8px;
    border-radius: var(--af-radius-full);
    font-size: var(--af-text-xs);
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}}
.qg-badge-critical {{ background: var(--af-error); color: #fff; }}
.qg-badge-warning {{ background: var(--af-warning); color: #1e293b; }}
.qg-badge-info {{ background: var(--af-info); color: #1e293b; }}
.qg-alert-file {{
    font-size: var(--af-text-sm);
    color: var(--af-text-muted);
    font-family: var(--af-font-mono);
    margin-left: auto;
    text-align: right;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    max-width: 40%;
}}
.qg-alert-body p {{
    color: var(--af-text);
    font-size: var(--af-text-base);
    padding-left: calc(20px + var(--af-space-sm));
}}
.qg-none {{
    color: var(--af-text-muted);
    font-style: italic;
    font-size: var(--af-text-base);
    padding: var(--af-space-sm) 0;
}}

/* --- File Table -------------------------------------------- */
.qg-table-wrap {{
    overflow-x: auto;
    border: 1px solid var(--af-border);
    border-radius: var(--af-radius-md);
}}
.qg-table {{
    width: 100%;
    border-collapse: collapse;
    font-size: var(--af-text-base);
}}
.qg-table thead {{
    background: var(--af-bg-inset);
}}
.qg-table th {{
    text-align: left;
    padding: var(--af-space-sm) var(--af-space-md);
    font-size: var(--af-text-xs);
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    color: var(--af-text-muted);
    border-bottom: 1px solid var(--af-border);
    white-space: nowrap;
}}
.qg-table td {{
    padding: var(--af-space-sm) var(--af-space-md);
    color: var(--af-text);
    border-bottom: 1px solid var(--af-border);
}}
.qg-table tbody tr {{
    transition: background var(--af-duration-fast) var(--af-ease-out);
}}
.qg-table tbody tr:hover {{
    background: var(--af-bg-hover);
}}
.qg-table tbody tr:last-child td {{
    border-bottom: none;
}}
.qg-table .qg-file-path {{
    font-family: var(--af-font-mono);
    font-size: var(--af-text-sm);
    color: var(--af-text-bright);
}}
.qg-table .qg-cell-added {{
    text-align: right;
    color: var(--af-success);
    font-family: var(--af-font-mono);
    font-size: var(--af-text-sm);
}}
.qg-table .qg-cell-removed {{
    text-align: right;
    color: var(--af-error);
    font-family: var(--af-font-mono);
    font-size: var(--af-text-sm);
}}
.qg-table .qg-cell-impact {{
    min-width: 140px;
}}
.qg-bar {{
    display: flex;
    align-items: center;
    gap: var(--af-space-sm);
}}
.qg-bar-track {{
    flex: 1;
    height: 6px;
    border-radius: 3px;
    background: var(--af-bg-element);
    overflow: hidden;
}}
.qg-bar-fill {{
    height: 100%;
    border-radius: 3px;
    transition: width var(--af-duration-slow) var(--af-ease-out);
}}
.qg-bar-fill-green {{ background: var(--af-success); }}
.qg-bar-fill-yellow {{ background: var(--af-warning); }}
.qg-bar-fill-red {{ background: var(--af-error); }}
.qg-bar-label {{
    font-size: var(--af-text-xs);
    color: var(--af-text-muted);
    min-width: 32px;
    text-align: right;
}}

/* --- Diff Preview ------------------------------------------ */
.qg-diff-block {{
    background: var(--af-bg-inset);
    border: 1px solid var(--af-border);
    border-radius: var(--af-radius-lg);
    overflow: hidden;
}}
.qg-diff-header {{
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: var(--af-space-xs) var(--af-space-md);
    background: var(--af-bg-surface);
    border-bottom: 1px solid var(--af-border);
    font-size: var(--af-text-xs);
    color: var(--af-text-muted);
}}
.qg-diff-content {{
    padding: var(--af-space-md);
    overflow-x: auto;
    font-family: var(--af-font-mono);
    font-size: var(--af-text-sm);
    line-height: 1.6;
    white-space: pre-wrap;
    word-break: break-all;
    max-height: 400px;
    overflow-y: auto;
}}
.qg-diff-add {{
    display: block;
    background: rgba(16, 185, 129, 0.08);
    color: #6ee7b7;
    border-left: 3px solid var(--af-success);
    padding: 1px 0 1px 8px;
    margin: 0 -16px;
}}
.qg-diff-remove {{
    display: block;
    background: rgba(239, 68, 68, 0.08);
    color: #fca5a5;
    border-left: 3px solid var(--af-error);
    padding: 1px 0 1px 8px;
    margin: 0 -16px;
}}
.qg-diff-hunk {{
    display: block;
    color: var(--af-primary);
    font-weight: 600;
    padding: 1px 0;
    margin: 0 -16px;
}}
.qg-diff-omit {{
    color: var(--af-text-muted);
    font-style: italic;
    font-size: var(--af-text-xs);
    padding: var(--af-space-sm) 0;
    text-align: center;
    border-top: 1px solid var(--af-border);
    margin-top: var(--af-space-sm);
}}

/* --- Prompt Box -------------------------------------------- */
.qg-prompt-box {{
    background: var(--af-bg-inset);
    border: 1px solid var(--af-primary);
    border-radius: var(--af-radius-lg);
    font-family: var(--af-font-mono);
    font-size: var(--af-text-sm);
    white-space: pre-wrap;
    word-break: break-word;
    color: var(--af-text);
    max-height: 320px;
    overflow-y: auto;
}}
.qg-prompt-header {{
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: var(--af-space-xs) var(--af-space-md);
    background: linear-gradient(135deg, rgba(168,85,247,0.12), rgba(99,102,241,0.12));
    border-bottom: 1px solid var(--af-primary-glow);
    font-size: var(--af-text-xs);
    color: var(--af-primary);
    font-family: var(--af-font-sans);
    font-weight: 500;
}}
.qg-prompt-body {{
    padding: var(--af-space-md);
}}
.qg-copy-hint {{
    color: var(--af-text-muted);
    font-size: var(--af-text-xs);
    margin-top: var(--af-space-sm);
    text-align: right;
    font-family: var(--af-font-sans);
}}

/* --- Next Steps -------------------------------------------- */
.qg-steps {{
    list-style: none;
    padding: 0;
    margin: 0;
}}
.qg-steps li {{
    position: relative;
    padding: var(--af-space-sm) 0 var(--af-space-sm) 24px;
    color: var(--af-text);
    font-size: var(--af-text-base);
    border-bottom: 1px solid var(--af-border);
}}
.qg-steps li:last-child {{
    border-bottom: none;
}}
.qg-steps li::before {{
    content: '';
    position: absolute;
    left: 0;
    top: 14px;
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: var(--af-primary);
}}

/* --- Footer ------------------------------------------------- */
.qg-footer {{
    text-align: center;
    color: var(--af-text-muted);
    font-size: var(--af-text-xs);
    padding: var(--af-space-lg);
    border-top: 1px solid var(--af-border);
}}
</style>
</head>
<body class="af-theme">
<div class="qg-wrap">

    <!-- ===== HEADER ===== -->
    <div class="qg-header">
        <div class="qg-header-badge">&bull; Quality Gate</div>
        <h1>Relatorio de Qualidade</h1>
        <div class="qg-header-meta">
            <span>&#128197; {esc(now)}</span>
            <span>&#128279; {esc(results.get("branch", "?"))}</span>
            <span>&#128196; {esc(results.get("last_commit", "?"))[:60]}</span>
            <span>&#128269; {esc(source_label)}</span>
        </div>
    </div>

    <!-- ===== SCORE + STATUS ===== -->
    <div class="qg-score-wrap">
        <div class="qg-score-card {score_class}">
            <div class="qg-score-number">{score}/10</div>
            <div class="qg-score-label">Qualidade geral</div>
        </div>
        <div class="qg-status-card qg-status-{score_class.replace('qg-score-', '')}">
            <div class="qg-status-icon">{status_icon}</div>
            <div class="qg-status-label">{status_label}</div>
            <div class="qg-status-detail">
                {total_critical} criticos, {total_warnings} importantes, {total_info} opcionais
            </div>
        </div>
    </div>

    <!-- ===== SUMMARY ===== -->
    <div class="qg-summary-grid">
        <div class="qg-summary-card color-files">
            <div class="qg-summary-value">{total_files}</div>
            <div class="qg-summary-label">Arquivos alterados</div>
        </div>
        <div class="qg-summary-card color-added">
            <div class="qg-summary-value">+{total_added}</div>
            <div class="qg-summary-label">Linhas adicionadas</div>
        </div>
        <div class="qg-summary-card color-removed">
            <div class="qg-summary-value">{total_removed}</div>
            <div class="qg-summary-label">Linhas removidas</div>
        </div>
        <div class="qg-summary-card color-critical">
            <div class="qg-summary-value">{total_critical}</div>
            <div class="qg-summary-label">Alertas criticos</div>
        </div>
        <div class="qg-summary-card color-warnings">
            <div class="qg-summary-value">{total_warnings}</div>
            <div class="qg-summary-label">Alertas importantes</div>
        </div>
        <div class="qg-summary-card color-info">
            <div class="qg-summary-value">{total_info}</div>
            <div class="qg-summary-label">Melhorias opcionais</div>
        </div>
    </div>

    <!-- ===== FILES TABLE ===== -->
    <div class="qg-section">
        <div class="qg-section-title">Arquivos alterados</div>
        <div class="qg-table-wrap">
        <table class="qg-table">
            <thead>
                <tr>
                    <th>Arquivo</th>
                    <th style="text-align:right;">+</th>
                    <th style="text-align:right;">-</th>
                    <th>Impacto</th>
                </tr>
            </thead>
            <tbody>
"""
    max_total = max((f["added"] + f["removed"]) for f in files_data) if files_data else 1
    for f in files_data:
        total_f = f["added"] + f["removed"]
        bar_pct = min(total_f / max_total * 100, 100)
        bar_color = "green" if total_f < 50 else "yellow" if total_f < 150 else "red"
        html_content += f"""
                <tr>
                    <td><span class="qg-file-path">{esc(f['path'])}</span></td>
                    <td class="qg-cell-added">+{f['added']}</td>
                    <td class="qg-cell-removed">-{f['removed']}</td>
                    <td class="qg-cell-impact">
                        <div class="qg-bar">
                            <div class="qg-bar-track">
                                <div class="qg-bar-fill qg-bar-fill-{bar_color}" style="width:{bar_pct}%;"></div>
                            </div>
                            <span class="qg-bar-label">{total_f}</span>
                        </div>
                    </td>
                </tr>"""

    html_content += """
            </tbody>
        </table>
        </div>
    </div>

    <!-- ===== CRITICAL ===== -->
    <div class="qg-section">
        <div class="qg-section-title">Alertas criticos</div>
"""
    html_content += render_alerts(critical_items, "critical")
    html_content += """
    </div>

    <!-- ===== WARNINGS ===== -->
    <div class="qg-section">
        <div class="qg-section-title">Alertas importantes</div>
"""
    html_content += render_alerts(warning_items, "warning")
    html_content += """
    </div>

    <!-- ===== INFO ===== -->
    <div class="qg-section">
        <div class="qg-section-title">Melhorias opcionais</div>
"""
    html_content += render_alerts(info_items, "info")
    html_content += """
    </div>

    <!-- ===== DEPENDENCIES ===== -->
    <div class="qg-section">
        <div class="qg-section-title">Dependencias novas</div>
"""
    html_content += render_alerts(results.get("new_dependencies", []), "info")
    html_content += """
    </div>

    <!-- ===== DANGEROUS COMMANDS ===== -->
    <div class="qg-section">
        <div class="qg-section-title">Comandos perigosos</div>
"""
    html_content += render_alerts(results.get("dangerous_commands", []), "critical")
    html_content += """
    </div>

    <!-- ===== TESTS ===== -->
    <div class="qg-section">
        <div class="qg-section-title">Ausencia de testes</div>
"""
    html_content += render_alerts(results.get("missing_tests", []), "warning")
    html_content += """
    </div>

    <!-- ===== DIFF PREVIEW ===== -->
    <div class="qg-section">
        <div class="qg-section-title">Preview do diff</div>
        <div class="qg-diff-block">
            <div class="qg-diff-header">
                <span>Diff completo do working tree</span>
                <span>+{total_added} / -{total_removed} linhas</span>
            </div>
            <div class="qg-diff-content">
"""
    html_content += render_diff_html(diff_lines, 200)
    html_content += """
            </div>
        </div>
    </div>

    <!-- ===== PROMPT ===== -->
    <div class="qg-section">
        <div class="qg-section-title">Prompt para correcao</div>
        <p style="color:var(--af-text-muted);font-size:var(--af-text-md);margin-bottom:var(--af-space-md);">
            Copie o prompt abaixo e envie ao agente <strong style="color:var(--af-text-bright);">Coder</strong>
            para corrigir os problemas apontados.
        </p>
        <div class="qg-prompt-box">
            <div class="qg-prompt-header">
                <span>&#9997; Prompt &mdash; Coder Agent</span>
                <span>selecione e copie</span>
            </div>
            <div class="qg-prompt-body">
"""
    html_content += esc(prompt)
    html_content += """
            </div>
        </div>
        <div class="qg-copy-hint">Selecione todo o texto acima e copie (Ctrl+C / Cmd+C)</div>
    </div>

    <!-- ===== NEXT STEPS ===== -->
    <div class="qg-section">
        <div class="qg-section-title">Proximos passos</div>
"""
    html_content += next_steps_html()
    html_content += """
    </div>

    <!-- ===== FOOTER ===== -->
    <div class="qg-footer">
        AI-Flow Quality Gate &mdash; .ai-flow/scripts/quality-gate.py &mdash; Gerado automaticamente
    </div>

</div>
</body>
</html>"""
    return html_content


def main():
    print("=== AI-Flow: Quality Gate ===\n")

    print(f"[1/4] Coletando diff atual do working tree...")
    git_ctx = collect_git_diff()
    branch = git_ctx["branch"]
    last_commit = git_ctx["last_commit"]
    diff_text = git_ctx["diff_text"]
    numstat_text = git_ctx["numstat_text"]
    stat_text = git_ctx["stat_text"]
    source_label = git_ctx["source_label"]

    if not git_ctx.get("git_available"):
        print("[!] Git nao disponivel. O relatorio sera gerado com diff vazio.")
    elif not diff_text.strip():
        print("[!] Nenhuma alteracao encontrada no working tree ou staged.")

    print(f"[2/4] Analisando alteracoes ({source_label})...")
    files = parse_numstat(numstat_text)

    # Carregar config para regras de seguranca
    config = load_config()
    sensitive_patterns = config["sensitive_patterns"]
    block_extensions = config["block_extensions"]

    all_alerts = {"critical": [], "warnings": [], "info": []}

    # Critical alerts
    all_alerts["critical"].extend(detect_large_files(files))
    all_alerts["critical"].extend(detect_sensitive_files(files, sensitive_patterns))
    all_alerts["critical"].extend(detect_blocked_extensions(files, block_extensions))
    all_alerts["critical"].extend(detect_possible_secrets(diff_text))
    dangerous_commands = detect_dangerous_commands(diff_text)

    # Warning alerts
    all_alerts["warnings"].extend(detect_long_lines(diff_text))
    all_alerts["warnings"].extend(detect_long_functions(diff_text))
    all_alerts["warnings"].extend(detect_simple_duplication(diff_text))
    missing_tests = detect_missing_tests(files)

    # Info alerts
    all_alerts["info"].extend(detect_todos_fixmes(diff_text))
    all_alerts["info"].extend(detect_prints_logs(diff_text))
    all_alerts["info"].extend(detect_added_comments(diff_text))
    new_dependencies = detect_new_dependencies(files, diff_text)

    print(f"   - Arquivos alterados: {len(files)}")
    print(f"   - Alertas criticos: {len(all_alerts['critical'])}")
    print(f"   - Alertas importantes: {len(all_alerts['warnings'])}")
    print(f"   - Melhorias opcionais: {len(all_alerts['info'])}")
    print(f"   - Comandos perigosos: {len(dangerous_commands)}")
    print(f"   - Dependencias novas: {len(new_dependencies)}")
    print(f"   - Ausencia de testes: {len(missing_tests)}")
    print(f"   - Seguranca: {len(sensitive_patterns)} padroes de arquivos sensiveis, {len(block_extensions)} extensoes bloqueadas, {len(SECRET_PATTERNS)} padroes de secrets")

    print(f"[3/4] Montando relatorio HTML...")
    diff_preview = get_git_diff_context(diff_text)

    results = {
        "branch": branch,
        "last_commit": last_commit,
        "source_label": source_label,
        "files": files,
        "critical": all_alerts["critical"],
        "warnings": all_alerts["warnings"],
        "info": all_alerts["info"],
        "diff_preview": diff_preview[:50000],
        "dangerous_commands": dangerous_commands,
        "new_dependencies": new_dependencies,
        "missing_tests": missing_tests,
        "coder_prompt": build_coder_prompt({
            "critical": all_alerts["critical"] + dangerous_commands,
            "warnings": all_alerts["warnings"] + missing_tests,
            "info": all_alerts["info"] + new_dependencies,
        }),
    }

    html_output = generate_html(results)

    print(f"[4/4] Salvando relatorio...")
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text(html_output, encoding="utf-8")

    abs_path = OUTPUT_FILE.resolve()
    print(f"\n[OK] Relatorio gerado em:")
    print(f"     {abs_path}")
    print(f"     origem: {source_label}")
    print(f"\nDica: abra o arquivo no navegador ou execute:")
    print(f"  .ai-flow\\scripts\\run-quality-gate.ps1")

    print(f"\n--- Resumo de seguranca ---")
    print(f"Padroes de arquivos sensiveis monitorados:")
    for p in sensitive_patterns:
        print(f"  - {p}")
    print(f"Extensoes bloqueadas:")
    for e in block_extensions:
        print(f"  - {e}")
    print(f"Padroes de secrets detectados (valores sempre mascarados):")
    for s in SECRET_PATTERNS:
        print(f"  - {s}")
    print(f"Falsos positivos ignorados: {', '.join(FALSE_POSITIVE_KEYWORDS)}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
