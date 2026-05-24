import json
import os
import sys

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "config.json")
MODEL_REGISTRY_PATH = os.path.join(os.path.dirname(__file__), "..", "model-registry.example.json")
MODELS_STATUS_PATH = os.path.join(os.path.dirname(__file__), "..", "reports", "models-status.json")

TASK_MAP = {
    "planner": {
        "config_key": "model_for_planning",
        "default": {
            "model": "huihui-qwen3-4b-instruct-2507",
            "provider": "lm_studio",
            "temperature": 0.3,
            "fallback": "qwen2.5-coder-7b-instruct",
            "reason": "Bom para exploração de ideias e planejamento estruturado com baixa temperatura."
        }
    },
    "coder": {
        "config_key": "model_for_coding",
        "default": {
            "model": "qwen2.5-coder-7b-instruct",
            "provider": "lm_studio",
            "temperature": 0.2,
            "fallback": "llama-3.2-3b-instruct",
            "reason": "Especializado em geração de código com temperatura baixa para consistência."
        }
    },
    "reviewer": {
        "config_key": "model_for_review",
        "default": {
            "model": "qwen2.5-coder-7b-instruct",
            "provider": "lm_studio",
            "temperature": 0.1,
            "fallback": "llama-3.2-3b-instruct",
            "reason": "Revisão exige precisao; temperatura muito baixa para julgamentos consistentes."
        }
    },
    "tester": {
        "config_key": "model_for_tester",
        "default": {
            "model": "llama-3.2-3b-instruct",
            "provider": "lm_studio",
            "temperature": 0.2,
            "fallback": "huihui-qwen3-4b-instruct-2507",
            "reason": "Testes sao tarefas estruturadas. Modelo leve resolve bem."
        }
    },
    "docs": {
        "config_key": "model_for_docs",
        "default": {
            "model": "llama-3.2-3b-instruct",
            "provider": "lm_studio",
            "temperature": 0.3,
            "fallback": "huihui-qwen3-4b-instruct-2507",
            "reason": "Documentacao prefere modelo menor e mais rapido, com temperatura baixa."
        }
    },
    "summarizer": {
        "config_key": "model_for_summary",
        "default": {
            "model": "llama-3.2-3b-instruct",
            "provider": "lm_studio",
            "temperature": 0.3,
            "fallback": "huihui-qwen3-4b-instruct-2507",
            "reason": "Sumarizacao prefere modelo compacto e rapido com temperatura baixa."
        }
    }
}


def load_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def get_temperature_override(config, task_name):
    key_map = {
        "planner": "temperature_planning",
        "coder": "temperature_coding",
        "reviewer": "temperature_review",
    }
    temp_key = key_map.get(task_name)
    if temp_key:
        api = config.get("api", {})
        val = api.get(temp_key)
        if val is not None:
            return val
    return None


def resolve_provider(config):
    api = config.get("api", {})
    return api.get("default_provider", "lm_studio")


def main():
    args = sys.argv[1:]

    if not args or args[0] in ("--help", "-h"):
        print("Uso: python .ai-flow/scripts/select-model.py <tarefa>")
        print("")
        print("Tarefas disponiveis:")
        for task in TASK_MAP:
            print(f"  {task}")
        print("")
        print("Exemplos:")
        print("  python .ai-flow/scripts/select-model.py coder")
        print("  python .ai-flow/scripts/select-model.py reviewer")
        return

    task = args[0].lower()

    if task not in TASK_MAP:
        print(f"Erro: tarefa desconhecida '{task}'.")
        print("Tarefas validas: " + ", ".join(TASK_MAP.keys()))
        sys.exit(1)

    config = load_json(CONFIG_PATH)
    registry = load_json(MODEL_REGISTRY_PATH)
    models_status = load_json(MODELS_STATUS_PATH)

    entry = TASK_MAP[task]
    result = dict(entry["default"])

    config_key = entry["config_key"]
    if config_key:
        configured_model = config.get("models", {}).get(config_key)
        if configured_model:
            result["model"] = configured_model

    temp_override = get_temperature_override(config, task)
    if temp_override is not None:
        result["temperature"] = temp_override

    result["provider"] = resolve_provider(config)

    if models_status and "models" in models_status:
        status_list = models_status["models"]
        available = {m.get("id") or m.get("model") for m in status_list if m.get("available")}
        if result["model"] not in available:
            for candidate in [result["fallback"]] + list(available):
                if candidate:
                    result["fallback_used"] = f"'{result['model']}' indisponivel; usando fallback"
                    result["model"] = candidate
                    break

    print(f"Tarefa:          {task}")
    print(f"Modelo:          {result['model']}")
    print(f"Provedor:        {result['provider']}")
    print(f"Temperatura:     {result['temperature']}")
    print(f"Fallback:        {result['fallback']}")
    print(f"Motivo:          {result['reason']}")
    if result.get("fallback_used"):
        print(f"Observacao:      {result['fallback_used']}")


if __name__ == "__main__":
    main()
