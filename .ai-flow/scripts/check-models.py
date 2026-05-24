import json
import os
import sys
import urllib.request
import urllib.error


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
CONFIG_PATH = os.path.join(ROOT_DIR, "config.json")
REPORT_PATH = os.path.join(ROOT_DIR, "reports", "models-status.json")


def load_config():
    if not os.path.exists(CONFIG_PATH):
        print(f"[WARN] config.json not found at {CONFIG_PATH}")
        return {}
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def probe_models(base_url, timeout=5):
    url = base_url.rstrip("/") + "/models"
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
            data = json.loads(body)
        return "online", data
    except urllib.error.URLError as e:
        return "offline", str(e)
    except urllib.error.HTTPError as e:
        return "error", f"HTTP {e.code}: {e.reason}"
    except Exception as e:
        return "error", str(e)


def parse_lm_studio_models(data):
    models = []
    if isinstance(data, dict):
        raw = data.get("data") or data.get("models") or []
        for m in raw:
            if isinstance(m, dict):
                models.append(m.get("id") or m.get("model") or str(m))
    return models


def parse_ollama_models(data):
    models = []
    if isinstance(data, dict):
        raw = data.get("data") or data.get("models") or []
        for m in raw:
            if isinstance(m, dict):
                models.append(m.get("id") or m.get("name") or m.get("model") or str(m))
    return models


def probe_ollama_tags(base_url, timeout=5):
    url = base_url.rstrip("/").replace("/v1", "") + "/api/tags"
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
            data = json.loads(body)
        models = []
        raw = data.get("models") or []
        for m in raw:
            if isinstance(m, dict):
                models.append(m.get("name") or str(m))
        return "online", models
    except Exception:
        return None, None


def format_status(status, detail, provider_label, models_found, suggestion):
    status_icon = {"online": "[OK]", "offline": "[OFFLINE]", "error": "[ERRO]"}
    icon = status_icon.get(status, "[?]")
    print(f"\n  {icon} {provider_label}")
    print(f"       Status: {status.upper()}")
    if status == "online":
        if models_found:
            print(f"       Modelos ({len(models_found)}):")
            for m in models_found:
                print(f"         - {m}")
        else:
            print("       Nenhum modelo detectado.")
    else:
        print(f"       Detalhe: {detail}")
    if suggestion:
        print(f"       Sugestao: {suggestion}")
    print()
    return {
        "provider": provider_label,
        "status": status,
        "detail": detail if status != "online" else None,
        "models": models_found if status == "online" else None,
        "suggestion": suggestion,
    }


def check_lm_studio(config):
    base_url = (config.get("api", {}) or {}).get(
        "lm_studio_base_url", "http://127.0.0.1:1234/v1"
    )
    suggestion = "Abra o LM Studio e carregue um modelo"
    status, result = probe_models(base_url)
    models = []
    if status == "online":
        models = parse_lm_studio_models(result)
        if not models:
            status = "online"
    return format_status(status, str(result) if status != "online" else "", "LM Studio", models, suggestion)


def check_ollama(config):
    base_url = (config.get("api", {}) or {}).get(
        "ollama_base_url", "http://127.0.0.1:11434/v1"
    )
    suggestion = "Verifique se o Ollama esta rodando (ollama serve)"
    status, result = probe_models(base_url)
    models = []
    if status == "online":
        models = parse_ollama_models(result)
        if not models:
            tags_status, tags_models = probe_ollama_tags(base_url)
            if tags_status == "online" and tags_models:
                models = tags_models
    else:
        tags_status, tags_models = probe_ollama_tags(base_url)
        if tags_status == "online":
            status = "online"
            models = tags_models
    return format_status(status, str(result) if status != "online" else "", "Ollama", models, suggestion)


def build_report(results, status_counts):
    return {
        "report": "models-status",
        "generated_by": "check-models.py",
        "summary": {
            "total_providers": len(results),
            "online": status_counts.get("online", 0),
            "offline": status_counts.get("offline", 0),
            "error": status_counts.get("error", 0),
        },
        "providers": results,
    }


def main():
    print("=" * 56)
    print("  PROVIDER HEALTHCHECK — Verificacao de Provedores/Modelos")
    print("=" * 56)

    config = load_config()

    results = []
    results.append(check_lm_studio(config))
    results.append(check_ollama(config))

    status_counts = {}
    for r in results:
        s = r["status"]
        status_counts[s] = status_counts.get(s, 0) + 1

    print("-" * 56)
    print("  RESUMO")
    print(f"    Online : {status_counts.get('online', 0)}")
    print(f"    Offline: {status_counts.get('offline', 0)}")
    print(f"    Erro   : {status_counts.get('error', 0)}")
    print("-" * 56)

    report = build_report(results, status_counts)
    os.makedirs(os.path.dirname(REPORT_PATH), exist_ok=True)
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"\n  Relatorio salvo em: {os.path.relpath(REPORT_PATH, ROOT_DIR)}")

    return 0 if status_counts.get("online", 0) > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
