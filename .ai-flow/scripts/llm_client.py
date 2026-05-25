import json
import os
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT_DIR = SCRIPT_DIR.parent
CONFIG_PATH = ROOT_DIR / "config.json"
CONFIG_EXAMPLE_PATH = ROOT_DIR / "config.example.json"


def load_config():
    path = CONFIG_PATH if CONFIG_PATH.exists() else CONFIG_EXAMPLE_PATH
    if not path.exists():
        print(f"[ERRO] Nenhum config encontrado em {CONFIG_PATH} ou {CONFIG_EXAMPLE_PATH}", file=sys.stderr)
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def get_assignment(agent_id, config=None):
    if config is None:
        config = load_config()
    models_cfg = config.get("models", {})
    assignment = models_cfg.get("assignment", {}).get(agent_id)
    if assignment:
        return assignment
    key_map = {
        "planner": "model_for_planning",
        "architect": "model_for_planning",
        "coder": "model_for_coding",
        "patch-applier": "model_for_coding",
        "reviewer": "model_for_review",
        "security": "model_for_review",
        "tester": "model_for_tester",
        "docs": "model_for_docs",
        "summarizer": "model_for_summary",
        "memory": "model_for_summary",
        "orchestrator": "model_for_summary",
        "context-engineer": "model_for_summary",
    }
    flat_key = key_map.get(agent_id)
    model_name = models_cfg.get(flat_key) if flat_key else None
    if model_name:
        return {"model": model_name, "temperature": 0.2, "max_tokens": 2048, "top_p": 0.9}
    return None


def get_provider_config(config=None):
    if config is None:
        config = load_config()
    api = config.get("api", {})
    provider = api.get("default_provider", "ollama")
    base_url_key = f"{provider}_base_url"
    base_url = api.get(base_url_key, "http://127.0.0.1:11434/v1")
    return provider, base_url.rstrip("/")


def test_connection(provider=None, base_url=None, timeout=5):
    if not provider or not base_url:
        config = load_config()
        provider, base_url = get_provider_config(config)
    import urllib.request
    import urllib.error

    urls_to_try = [f"{base_url}/models"]
    if provider == "ollama":
        ollama_base = base_url.replace("/v1", "").rstrip("/")
        urls_to_try.append(f"{ollama_base}/api/tags")

    last_error = ""
    for url in urls_to_try:
        try:
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            models = []
            if isinstance(data, dict):
                raw = data.get("data") or data.get("models") or []
                for m in raw:
                    if isinstance(m, dict):
                        models.append(m.get("id") or m.get("name") or m.get("model") or str(m))
            return {"ok": True, "provider": provider, "base_url": base_url, "models": models}
        except urllib.error.HTTPError as exc:
            if exc.code == 404 and len(urls_to_try) > 1:
                continue
            last_error = f"HTTP {exc.code}: {exc.reason}"
        except Exception as e:
            last_error = str(e)
            continue

    friendly = ""
    if provider == "ollama":
        friendly = ". Verifique se o servidor Ollama esta rodando (ollama serve)"
    return {"ok": False, "provider": provider, "base_url": base_url, "error": last_error + friendly}


def chat_completion(messages, model=None, agent_id=None, provider=None, temperature=None, max_tokens=None, top_p=None, timeout=120):
    config = load_config()
    if not config:
        return {"ok": False, "error": "config.json nao carregado"}

    if agent_id:
        assignment = get_assignment(agent_id, config)
        if assignment:
            model = model or assignment.get("model", "qwen2.5-coder:7b")
            temperature = temperature if temperature is not None else assignment.get("temperature", 0.2)
            max_tokens = max_tokens or assignment.get("max_tokens", 2048)
            top_p = top_p or assignment.get("top_p", 0.9)
        else:
            model = model or "qwen2.5-coder:7b"
            temperature = temperature if temperature is not None else 0.2
            max_tokens = max_tokens or 2048
            top_p = top_p or 0.9
    else:
        model = model or "qwen2.5-coder:7b"
        temperature = temperature if temperature is not None else 0.2
        max_tokens = max_tokens or 2048
        top_p = top_p or 0.9

    if not provider:
        provider, base_url = get_provider_config(config)
    else:
        api = config.get("api", {})
        base_url_key = f"{provider}_base_url"
        base_url = api.get(base_url_key, "http://127.0.0.1:11434/v1").rstrip("/")

    import urllib.request
    url = f"{base_url}/chat/completions"
    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "top_p": top_p,
        "stream": False,
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            content = result["choices"][0]["message"]["content"]
            return {"ok": True, "response": content, "model": model}
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        error_msg = f"HTTP {exc.code}: {exc.reason}"
        if provider == "ollama" and exc.code == 404:
            error_msg = f"Modelo '{model}' nao encontrado no Ollama. Rode: ollama pull {model}"
        elif exc.code == 503:
            error_msg = f"Ollama esta carregando o modelo. Tente novamente em instantes."
        return {"ok": False, "error": error_msg, "model": model}
    except Exception as e:
        error_msg = str(e)
        if provider == "ollama" and "Connection refused" in error_msg:
            error_msg = "Ollama nao esta rodando. Execute 'ollama serve' ou abra o aplicativo Ollama."
        return {"ok": False, "error": error_msg, "model": model}


def main():
    import argparse
    parser = argparse.ArgumentParser(description="LLM Client - interface unificada para Ollama / LM Studio")
    parser.add_argument("action", nargs="?", default="test", choices=["test", "chat", "models"],
                        help="acao: test (padrao), chat, models")
    parser.add_argument("prompt", nargs="?", default="", help="prompt para chat")
    parser.add_argument("--agent", "-a", help="ID do agente (planner, coder, reviewer, tester, docs)")
    parser.add_argument("--model", "-m", help="nome do modelo (sobrescreve config)")
    parser.add_argument("--provider", "-p", help="provider: ollama ou lm_studio")
    parser.add_argument("--temperature", "-t", type=float, help="temperature")
    parser.add_argument("--max-tokens", type=int, default=2048, help="max tokens")
    parser.add_argument("--system", "-s", help="system prompt")
    parser.add_argument("--json", action="store_true", help="saida em JSON")

    args = parser.parse_args()

    if args.action == "test":
        config = load_config()
        provider, base_url = get_provider_config(config)
        print(f"Provider: {provider}")
        print(f"Base URL: {base_url}")
        result = test_connection(provider, base_url)
        if args.json:
            print(json.dumps(result, indent=2, ensure_ascii=False))
            return 0
        if result["ok"]:
            print(f"Status: CONECTADO")
            models = result.get("models", [])
            if models:
                print(f"Modelos ({len(models)}):")
                for m in models:
                    print(f"  - {m}")
            else:
                print("Nenhum modelo encontrado.")
        else:
            print(f"Status: ERRO")
            print(f"Erro: {result.get('error')}")
        return 0 if result["ok"] else 1

    if args.action == "models":
        config = load_config()
        provider, base_url = get_provider_config(config)
        result = test_connection(provider, base_url)
        if args.json:
            print(json.dumps(result, indent=2, ensure_ascii=False))
            return 0
        if result["ok"]:
            for m in result.get("models", []):
                print(m)
        else:
            print(f"Erro: {result.get('error')}", file=sys.stderr)
            return 1
        return 0

    if args.action == "chat":
        if not args.prompt and not args.system:
            print("Forneca um prompt ou --system", file=sys.stderr)
            return 1
        messages = []
        if args.system:
            messages.append({"role": "system", "content": args.system})
        if args.prompt:
            messages.append({"role": "user", "content": args.prompt})
        result = chat_completion(
            messages=messages,
            model=args.model,
            agent_id=args.agent,
            provider=args.provider,
            temperature=args.temperature,
            max_tokens=args.max_tokens,
        )
        if args.json:
            print(json.dumps(result, indent=2, ensure_ascii=False))
            return 0
        if result["ok"]:
            print(result["response"])
        else:
            print(f"Erro: {result.get('error')}", file=sys.stderr)
            return 1
        return 0


if __name__ == "__main__":
    sys.exit(main())
