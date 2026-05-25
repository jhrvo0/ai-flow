import argparse
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = Path(__file__).resolve().parent
AGENTS_DIR = ROOT_DIR / "agents"
ARTIFACTS_DIR = ROOT_DIR / "artifacts"
CONFIG_PATH = ROOT_DIR / "config.json"

sys.path.insert(0, str(SCRIPTS_DIR))

AGENT_FILE_NAMES = {
    "planner": ["planner.md", "02-planner.md"],
    "architect": ["03-architect.md"],
    "coder": ["coder.md", "04-coder.md"],
    "reviewer": ["reviewer-quality-gate.md", "reviewer.md", "06-reviewer.md"],
    "tester": ["tester.md", "07-tester.md"],
    "docs": ["docs-commit.md", "09-docs-commit.md"],
    "orchestrator": ["00-orchestrator.md"],
    "context-engineer": ["01-context-engineer.md"],
    "security": ["08-security.md"],
    "patch-applier": ["05-patch-applier.md"],
    "memory": ["10-memory.md"],
}

AGENT_ASSIGNMENT_MAP = {
    "planner": "planner",
    "architect": "planner",
    "coder": "coder",
    "patch-applier": "coder",
    "reviewer": "reviewer",
    "security": "reviewer",
    "tester": "tester",
    "docs": "docs",
    "summarizer": "summarizer",
    "memory": "docs",
    "orchestrator": "orchestrator",
    "context-engineer": "context-engineer",
}


def find_agent_file(agent_id):
    candidates = AGENT_FILE_NAMES.get(agent_id, [f"{agent_id}.md"])
    for name in candidates:
        path = AGENTS_DIR / name
        if path.exists():
            return path
    for f in AGENTS_DIR.glob("*.md"):
        stem = f.stem.lower()
        if agent_id in stem:
            return f
    return None


def load_agent_prompt(agent_id):
    path = find_agent_file(agent_id)
    if not path:
        return None, f"Arquivo do agente '{agent_id}' nao encontrado em {AGENTS_DIR}"
    try:
        return path.read_text(encoding="utf-8"), None
    except Exception as e:
        return None, str(e)


def get_git_context():
    try:
        diff = subprocess.run(
            ["git", "diff"], capture_output=True, text=True, encoding="utf-8", errors="replace"
        )
        diff_staged = subprocess.run(
            ["git", "diff", "--cached"], capture_output=True, text=True, encoding="utf-8", errors="replace"
        )
        status = subprocess.run(
            ["git", "status", "--porcelain"], capture_output=True, text=True, encoding="utf-8", errors="replace"
        )
        branch = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"], capture_output=True, text=True, encoding="utf-8", errors="replace"
        )
        combined_diff = (diff.stdout or "") + "\n" + (diff_staged.stdout or "")
        return {
            "diff": combined_diff.strip(),
            "status": (status.stdout or "").strip(),
            "branch": (branch.stdout or "").strip() or "unknown",
        }
    except Exception as e:
        return {"diff": "", "status": "", "branch": "unknown", "error": str(e)}


def load_current_task():
    current_task_path = ARTIFACTS_DIR / "current-task.json"
    if current_task_path.exists():
        try:
            data = json.loads(current_task_path.read_text(encoding="utf-8"))
            path = data.get("path")
            if path:
                p = Path(path)
                if p.exists() and p.is_dir():
                    return p
        except Exception:
            pass
    return None


def save_run_metadata(run_dir, agent_id, model, provider, messages, response, git_context_used):
    meta = {
        "agent_id": agent_id,
        "model": model,
        "provider": provider,
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "git_context_used": git_context_used,
        "prompt_saved": True,
        "response_saved": True,
    }
    write_json(run_dir / "metadata.json", meta)


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def run_command(cmd):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
        return r.stdout.strip() + "\n" + r.stderr.strip()
    except Exception as e:
        return str(e)


def build_messages(agent_id, prompt_text, system_extra=None, include_git_context=False):
    messages = []
    agent_prompt, err = load_agent_prompt(agent_id)
    system_content = ""
    if agent_prompt:
        system_content = agent_prompt.strip()
    if system_extra:
        system_content = system_content + "\n\n" + system_extra
    if include_git_context:
        git = get_git_context()
        context_parts = []
        if git.get("branch"):
            context_parts.append(f"Branch atual: {git['branch']}")
        if git.get("status"):
            context_parts.append(f"Status do working tree:\n{git['status']}")
        if git.get("diff"):
            context_parts.append(f"Git diff atual:\n```diff\n{git['diff']}\n```")
        if context_parts:
            system_content = system_content + "\n\n## Contexto do Git\n" + "\n\n".join(context_parts)
    if system_content:
        messages.append({"role": "system", "content": system_content})
    if prompt_text:
        messages.append({"role": "user", "content": prompt_text})
    return messages


def check_provider(config):
    from llm_client import test_connection, get_provider_config
    provider, base_url = get_provider_config(config)
    result = test_connection(provider, base_url)
    return result


def main():
    parser = argparse.ArgumentParser(description="Run Agent - executa um agente via LLM local (Ollama padrao)")
    parser.add_argument("agent_id", nargs="?", default="", help="ID do agente: planner, coder, reviewer, tester, docs, architect, security, orchestrator")
    parser.add_argument("prompt", nargs="?", default="", help="Prompt ou descricao da tarefa")
    parser.add_argument("--system", "-s", help="Conteudo extra para system prompt")
    parser.add_argument("--model", "-m", help="Nome do modelo (sobrescreve config)")
    parser.add_argument("--provider", "-p", help="Provider: ollama (padrao) ou lm_studio")
    parser.add_argument("--temperature", "-t", type=float, help="Temperature")
    parser.add_argument("--max-tokens", type=int, default=4096, help="Max tokens")
    parser.add_argument("--git-context", "-g", action="store_true", help="Incluir git diff/status no contexto")
    parser.add_argument("--save", action="store_true", help="Salvar resposta em artifacts/runs/")
    parser.add_argument("--json", action="store_true", help="Saida em JSON")
    parser.add_argument("--list-agents", action="store_true", help="Listar agentes disponiveis")
    parser.add_argument("--cmd", help="Comando para executar (ex: 'npm test'). Saida sera adicionada ao prompt.")

    args, _ = parser.parse_known_args()

    if args.list_agents:
        print("Agentes disponiveis:")
        for agent_id in AGENT_FILE_NAMES:
            path = find_agent_file(agent_id)
            status = "[OK]" if path else "[arquivo nao encontrado]"
            assignment = AGENT_ASSIGNMENT_MAP.get(agent_id, agent_id)
            print(f"  {agent_id:20s} {status:30s} (mapeia para config: {assignment})")
        return 0

    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8")) if CONFIG_PATH.exists() else {}

    if args.agent_id == "check":
        result = check_provider(config)
        if args.json:
            print(json.dumps(result, indent=2, ensure_ascii=False))
        elif result.get("ok"):
            print(f"[OK] {result['provider']} conectado em {result['base_url']}")
            for m in result.get("models", []):
                print(f"     - {m}")
        else:
            error = result.get("error", "Provider offline")
            if "ollama" in result.get("provider", ""):
                error += "\n[Sugestao] Execute 'ollama serve' ou abra o aplicativo Ollama."
            print(f"[ERRO] {error}")
        return 0 if result.get("ok") else 1

    if not args.agent_id:
        print("Forneca um ID de agente. Use --list-agents para ver os disponiveis.", file=sys.stderr)
        return 1

    if not args.prompt and not args.system:
        print(f"Forneca um prompt ou --system para o agente '{args.agent_id}'", file=sys.stderr)
        return 1

    cmd_output = None
    if args.cmd:
        print(f"Executando comando: {args.cmd}", file=sys.stderr)
        cmd_output = run_command(args.cmd)
        print(f"Saida do comando:\n{cmd_output}", file=sys.stderr)

    prompt_text = args.prompt
    if cmd_output:
        prompt_text = (prompt_text + f"\n\n## Saida do comando executado\n```\n{cmd_output}\n```").strip()

    messages = build_messages(
        agent_id=args.agent_id,
        prompt_text=prompt_text,
        system_extra=args.system,
        include_git_context=args.git_context,
    )

    from llm_client import chat_completion, load_config as llm_load_config

    cfg = llm_load_config()
    resolved_agent = AGENT_ASSIGNMENT_MAP.get(args.agent_id, args.agent_id)
    result = chat_completion(
        messages=messages,
        model=args.model,
        agent_id=resolved_agent,
        provider=args.provider,
        temperature=args.temperature,
        max_tokens=args.max_tokens,
    )

    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0 if result.get("ok") else 1

    if not result.get("ok"):
        print(f"[ERRO] {result.get('error')}", file=sys.stderr)
        return 1

    response = result["response"]
    print(response)

    if args.save:
        run_id = datetime.now().strftime("%Y%m%d_%H%M%S")

        # Try to save inside active task if exists
        task_dir = load_current_task()
        if task_dir:
            run_subdir = task_dir / "runs" / f"{run_id}-{args.agent_id}"
        else:
            run_subdir = ARTIFACTS_DIR / "runs" / f"{run_id}-{args.agent_id}"

        run_subdir.mkdir(parents=True, exist_ok=True)

        model_used = result.get("model", args.model or "unknown")
        provider_used = args.provider or config.get("api", {}).get("default_provider", "ollama")

        save_run_metadata(run_subdir, args.agent_id, model_used, provider_used, messages, response, args.git_context)

        (run_subdir / "prompt.md").write_text(
            f"# Agent: {args.agent_id}\n\n## Messages\n\n" + json.dumps(messages, indent=2, ensure_ascii=False),
            encoding="utf-8"
        )
        (run_subdir / "response.md").write_text(response, encoding="utf-8")
        print(f"\n--- Salvo em: {run_subdir}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
