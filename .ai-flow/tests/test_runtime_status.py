import importlib.util
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parent.parent
SERVER_PATH = ROOT / "server.py"
AI_FLOW_PATH = ROOT / "scripts" / "ai-flow.py"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


server = load_module("ai_flow_server", SERVER_PATH)
ai_flow = load_module("ai_flow_cli", AI_FLOW_PATH)


class TestRunCommand(unittest.TestCase):
    def test_permission_error_is_reported_instead_of_crashing(self):
        with patch.object(ai_flow.subprocess, "run", side_effect=PermissionError("Access is denied")):
            rc, output = ai_flow.run_command(["ollama", "--version"])
        self.assertNotEqual(rc, 0)
        self.assertIn("Access is denied", output)


class TestRuntimeStatus(unittest.TestCase):
    def test_server_run_cmd_handles_permission_error(self):
        with patch.object(server.subprocess, "run", side_effect=PermissionError("Access is denied")):
            stdout, stderr, rc = server.run_cmd(["ollama", "list"])
        self.assertEqual(stdout, "")
        self.assertIn("Access is denied", stderr)
        self.assertLess(rc, 0)

    def test_build_runtime_status_returns_provider_and_task_details(self):
        probes = {
            "ollama": {
                "provider": "ollama",
                "label": "Ollama",
                "available": False,
                "status": "offline",
                "endpoint": "http://127.0.0.1:11434/api/tags",
                "detail": "connection refused",
                "models": [],
                "type": "http",
            },
            "lm_studio": {
                "provider": "lm_studio",
                "label": "LM Studio",
                "available": True,
                "status": "online",
                "endpoint": "http://127.0.0.1:1234/v1/models",
                "detail": "2 modelo(s) encontrados",
                "models": [{"id": "qwen-local", "name": "qwen-local"}],
                "type": "http",
            },
            "ollama_cli": {
                "provider": "ollama_cli",
                "label": "Ollama CLI",
                "available": False,
                "status": "offline",
                "endpoint": "ollama --version",
                "detail": "ollama nao encontrado",
                "models": [],
                "type": "cli",
            },
        }

        with patch.object(server, "load_config", return_value={"api": {"default_provider": "ollama"}}), \
             patch.object(server, "probe_provider_status", side_effect=lambda provider_id: probes[provider_id]), \
             patch.object(server, "get_active_task_summary", return_value={"name": "resgate", "stage": "quality"}):
            status = server.build_runtime_status()

        self.assertEqual(status["server"]["status"], "online")
        self.assertEqual(status["default_provider"], "ollama")
        self.assertEqual(status["providers"]["ollama"]["status"], "offline")
        self.assertEqual(status["providers"]["lm_studio"]["status"], "online")
        self.assertEqual(status["ollama"]["status"], "offline")
        self.assertEqual(status["active_task"]["name"], "resgate")


if __name__ == "__main__":
    unittest.main()
