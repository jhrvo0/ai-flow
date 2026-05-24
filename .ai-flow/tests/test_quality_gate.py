"""
Tests para .ai-flow/scripts/quality-gate.py

Uso: python -m unittest discover .ai-flow/tests
"""

import unittest
import json
import sys
import os
import tempfile
import importlib.util
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
_QG_PATH = _SCRIPTS_DIR / "quality-gate.py"

_spec = importlib.util.spec_from_file_location("quality_gate", _QG_PATH)
quality_gate = importlib.util.module_from_spec(_spec)
sys.modules["quality_gate"] = quality_gate
_spec.loader.exec_module(quality_gate)

parse_numstat = quality_gate.parse_numstat
detect_long_lines = quality_gate.detect_long_lines
detect_long_functions = quality_gate.detect_long_functions
detect_todos_fixmes = quality_gate.detect_todos_fixmes
detect_prints_logs = quality_gate.detect_prints_logs
extract_filename = quality_gate.extract_filename
detect_large_files = quality_gate.detect_large_files
detect_added_comments = quality_gate.detect_added_comments
detect_simple_duplication = quality_gate.detect_simple_duplication
generate_html = quality_gate.generate_html
MAX_LINES_PER_FILE = quality_gate.MAX_LINES_PER_FILE
MAX_FUNCTION_LINES = quality_gate.MAX_FUNCTION_LINES

HAS_SENSITIVE = hasattr(quality_gate, "detect_sensitive_files")
HAS_BLOCKED = hasattr(quality_gate, "detect_blocked_extensions")
if HAS_SENSITIVE:
    detect_sensitive_files = quality_gate.detect_sensitive_files
if HAS_BLOCKED:
    detect_blocked_extensions = quality_gate.detect_blocked_extensions


FIXTURE_NUMSTAT = """10\t5\tsrc/app.py
3\t1\tsrc/utils.py
"""

FIXTURE_NUMSTAT_BINARY = """-\t-\timage.png
10\t5\tsrc/app.py
"""

FIXTURE_DIFF_SMALL = """diff --git a/src/app.py b/src/app.py
--- a/src/app.py
+++ b/src/app.py
@@ -1,3 +1,5 @@
+def new_func():
+    pass
"""

FIXTURE_DIFF_TWO_FILES = """diff --git a/src/app.py b/src/app.py
--- a/src/app.py
+++ b/src/app.py
@@ -1,3 +1,5 @@
+# TODO: refactor this
+print("debug")
diff --git a/src/utils.py b/src/utils.py
--- a/src/utils.py
+++ b/src/utils.py
@@ -1,3 +1,5 @@
+def helper():
+    # FIXME: implement
+    pass
"""


class TestParseNumstat(unittest.TestCase):
    """1. parse_numstat com arquivo normal"""

    def test_parse_numstat_normal(self):
        files = parse_numstat(FIXTURE_NUMSTAT)
        self.assertEqual(len(files), 2)
        self.assertEqual(files[0]["path"], "src/app.py")
        self.assertEqual(files[0]["added"], 10)
        self.assertEqual(files[0]["removed"], 5)
        self.assertEqual(files[1]["path"], "src/utils.py")
        self.assertEqual(files[1]["added"], 3)
        self.assertEqual(files[1]["removed"], 1)

    def test_parse_numstat_binary(self):
        """2. parse_numstat ignorando binario com '-'"""
        files = parse_numstat(FIXTURE_NUMSTAT_BINARY)
        self.assertEqual(len(files), 1)
        self.assertEqual(files[0]["path"], "src/app.py")


class TestConfigDefaults(unittest.TestCase):
    """3. constantes padrao do modulo funcionam como fallback"""

    def test_max_lines_per_file_default(self):
        self.assertEqual(MAX_LINES_PER_FILE, 300)

    def test_max_function_lines_default(self):
        self.assertEqual(MAX_FUNCTION_LINES, 50)

    def test_detect_large_files_uses_module_constant(self):
        files = [{"path": "big.py", "added": 200, "removed": 150}]
        alerts = detect_large_files(files)
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0]["type"], "warning")
        self.assertIn("big.py", alerts[0]["file"])

    def test_detect_large_files_below_threshold(self):
        files = [{"path": "small.py", "added": 10, "removed": 5}]
        alerts = detect_large_files(files)
        self.assertEqual(len(alerts), 0)


class TestDetectLongLines(unittest.TestCase):
    """4. detect_long_lines gera alerta quando diff excede limite"""

    def test_no_alert_for_small_diff(self):
        alerts = detect_long_lines(FIXTURE_DIFF_SMALL, max_lines=300)
        self.assertEqual(len(alerts), 0)

    def test_alert_for_large_diff(self):
        lines = [
            "diff --git a/src/big.py b/src/big.py",
            "--- a/src/big.py",
            "+++ b/src/big.py",
        ]
        for i in range(310):
            lines.append(f"@@ -{i},{i+1} +{i},{i+1} @@")
            lines.append(f"+line {i}")
        diff = "\n".join(lines)
        alerts = detect_long_lines(diff, max_lines=300)
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0]["type"], "warning")
        self.assertIn("src/big.py", alerts[0]["file"])


class TestExtractFilename(unittest.TestCase):
    """extract_filename retorna o arquivo correto baseado na linha"""

    def test_returns_file_before_line(self):
        diff = (
            "+++ b/src/first.py\n"
            "some content\n"
            "+++ b/src/second.py\n"
            "more content\n"
        )
        result = extract_filename(diff, 2)
        self.assertEqual(result, "src/first.py")

    def test_returns_last_file_if_after_all_headers(self):
        diff = (
            "+++ b/src/first.py\n"
            "some content\n"
            "+++ b/src/second.py\n"
        )
        result = extract_filename(diff, 5)
        self.assertEqual(result, "src/second.py")

    def test_returns_question_mark_when_no_header(self):
        diff = "no header here\n"
        result = extract_filename(diff, 1)
        self.assertEqual(result, "?")


class TestDetectTodosFixmes(unittest.TestCase):
    """5. TODO/FIXME associado ao arquivo correto"""

    def test_todo_detected_in_first_file(self):
        alerts = detect_todos_fixmes(FIXTURE_DIFF_TWO_FILES)
        todo_alerts = [a for a in alerts if "TODO" in a["msg"]]
        self.assertGreaterEqual(len(todo_alerts), 1)
        for a in todo_alerts:
            self.assertEqual(a["file"], "src/app.py")

    def test_fixme_detected_in_second_file(self):
        alerts = detect_todos_fixmes(FIXTURE_DIFF_TWO_FILES)
        fixme_alerts = [a for a in alerts if "FIXME" in a["msg"]]
        self.assertGreaterEqual(len(fixme_alerts), 1)
        for a in fixme_alerts:
            self.assertEqual(a["file"], "src/utils.py")

    def test_no_false_positive_on_removed_lines(self):
        diff = "--- a/src/file.py\n-old line with TODO\n"
        alerts = detect_todos_fixmes(diff)
        self.assertEqual(len(alerts), 0)


class TestDetectPrintsLogs(unittest.TestCase):
    """6. print/console.log associado ao arquivo correto"""

    def test_print_detected(self):
        alerts = detect_prints_logs(FIXTURE_DIFF_TWO_FILES)
        print_alerts = [a for a in alerts if "print()" in a["msg"]]
        self.assertGreaterEqual(len(print_alerts), 1)
        for a in print_alerts:
            self.assertEqual(a["file"], "src/app.py")

    def test_console_log_detected(self):
        diff = (
            "+++ b/src/app.js\n"
            "+console.log('test');\n"
        )
        alerts = detect_prints_logs(diff)
        self.assertEqual(len(alerts), 1)
        self.assertIn("console.log", alerts[0]["msg"])

    def test_no_alert_on_removed_lines(self):
        diff = "--- a/src/file.py\n-print('removed')\n"
        alerts = detect_prints_logs(diff)
        self.assertEqual(len(alerts), 0)


class TestDetectLargeFiles(unittest.TestCase):
    """detect_large_files gera alerta critico para arquivo grande"""

    def test_alert_generated(self):
        files = [{"path": "huge.py", "added": 200, "removed": 150}]
        alerts = detect_large_files(files)
        self.assertEqual(len(alerts), 1)
        self.assertIn("huge.py", alerts[0]["file"])

    def test_no_alert_for_small_changes(self):
        files = [{"path": "tiny.py", "added": 1, "removed": 1}]
        alerts = detect_large_files(files)
        self.assertEqual(len(alerts), 0)


class TestDetectSensitiveFiles(unittest.TestCase):
    """7. arquivo sensivel gera alerta critico"""

    def test_env_file_detected(self):
        if not HAS_SENSITIVE:
            self.skipTest("detect_sensitive_files nao implementado")
        files = [{"path": ".env", "added": 5, "removed": 0}]
        alerts = detect_sensitive_files(files)
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0]["type"], "critical")
        self.assertIn(".env", alerts[0]["file"])

    def test_secrets_file_detected(self):
        if not HAS_SENSITIVE:
            self.skipTest("detect_sensitive_files nao implementado")
        files = [{"path": "config/secrets/db.yml", "added": 5, "removed": 0}]
        alerts = detect_sensitive_files(files)
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0]["type"], "critical")

    def test_normal_file_ignored(self):
        if not HAS_SENSITIVE:
            self.skipTest("detect_sensitive_files nao implementado")
        files = [{"path": "src/app.py", "added": 5, "removed": 0}]
        alerts = detect_sensitive_files(files)
        self.assertEqual(len(alerts), 0)


class TestDetectBlockedExtensions(unittest.TestCase):
    """8. extensao bloqueada gera alerta critico"""

    def test_exe_file_detected(self):
        if not HAS_BLOCKED:
            self.skipTest("detect_blocked_extensions nao implementado")
        files = [{"path": "malware.exe", "added": 1, "removed": 0}]
        alerts = detect_blocked_extensions(files)
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0]["type"], "critical")
        self.assertIn("malware.exe", alerts[0]["file"])

    def test_dll_file_detected(self):
        if not HAS_BLOCKED:
            self.skipTest("detect_blocked_extensions nao implementado")
        files = [{"path": "lib.dll", "added": 1, "removed": 0}]
        alerts = detect_blocked_extensions(files)
        self.assertEqual(len(alerts), 1)

    def test_normal_extension_ignored(self):
        if not HAS_BLOCKED:
            self.skipTest("detect_blocked_extensions nao implementado")
        files = [{"path": "src/app.py", "added": 5, "removed": 0}]
        alerts = detect_blocked_extensions(files)
        self.assertEqual(len(alerts), 0)


class TestGenerateHTML(unittest.TestCase):
    """9. geracao de HTML contem campos principais do JSON de resultados"""

    def test_contains_branch(self):
        results = {"branch": "feature/test", "files": [], "critical": [], "warnings": [], "info": [], "diff_preview": ""}
        html = generate_html(results)
        self.assertIn("feature/test", html)

    def test_contains_file_count(self):
        results = {"branch": "main", "files": [{"path": "a.py", "added": 1, "removed": 0}], "critical": [], "warnings": [], "info": [], "diff_preview": ""}
        html = generate_html(results)
        self.assertIn("Arquivos alterados", html)

    def test_contains_critical_section(self):
        results = {"branch": "main", "files": [], "critical": [{"file": "secret.env", "msg": "Arquivo sensivel detectado"}], "warnings": [], "info": [], "diff_preview": ""}
        html = generate_html(results)
        self.assertIn("Alertas criticos", html)
        self.assertIn("secret.env", html)

    def test_contains_warnings_section(self):
        results = {"branch": "main", "files": [], "critical": [], "warnings": [{"file": "big.py", "msg": "Arquivo grande"}], "info": [], "diff_preview": ""}
        html = generate_html(results)
        self.assertIn("Alertas importantes", html)
        self.assertIn("big.py", html)

    def test_contains_info_section(self):
        results = {"branch": "main", "files": [], "critical": [], "warnings": [], "info": [{"file": "app.py", "msg": "TODO encontrado"}], "diff_preview": ""}
        html = generate_html(results)
        self.assertIn("Melhorias opcionais", html)
        self.assertIn("TODO encontrado", html)

    def test_contains_diff_preview_section(self):
        results = {"branch": "main", "files": [], "critical": [], "warnings": [], "info": [], "diff_preview": "diff content"}
        html = generate_html(results)
        self.assertIn("Preview do diff", html)
        self.assertIn("diff content", html)

    def test_contains_quality_gate_title(self):
        results = {"branch": "main", "files": [], "critical": [], "warnings": [], "info": [], "diff_preview": ""}
        html = generate_html(results)
        self.assertIn("Quality Gate Report", html)

    def test_score_zero_when_no_alerts(self):
        results = {"branch": "main", "files": [], "critical": [], "warnings": [], "info": [], "diff_preview": ""}
        html = generate_html(results)
        self.assertIn("10/10", html)


class TestDetectAddedComments(unittest.TestCase):
    """detect_added_comments para muitos comentarios"""

    def test_few_comments_no_alert(self):
        diff = "+++ b/src/app.py\n+# comment\n"
        alerts = detect_added_comments(diff)
        self.assertEqual(len(alerts), 0)

    def test_many_comments_triggers_alert(self):
        lines = ["+++ b/src/app.py"]
        for i in range(25):
            lines.append(f"+# comment {i}")
        diff = "\n".join(lines)
        alerts = detect_added_comments(diff)
        self.assertEqual(len(alerts), 1)
        self.assertIn("Muitos comentarios", alerts[0]["msg"])


class TestDetectSimpleDuplication(unittest.TestCase):
    """detect_simple_duplication para linhas duplicadas"""

    def test_no_duplicates(self):
        diff = "+++ b/src/app.py\n+unique line\n"
        alerts = detect_simple_duplication(diff)
        self.assertEqual(len(alerts), 0)

    def test_duplicates_detected(self):
        lines = ["+++ b/src/app.py"]
        for i in range(5):
            lines.append("+duplicated line with more than 20 chars")
        diff = "\n".join(lines)
        alerts = detect_simple_duplication(diff, threshold=4)
        self.assertEqual(len(alerts), 1)
        self.assertIn("duplicated", alerts[0]["msg"])


class TestContract(unittest.TestCase):
    """Verifica que funcoes retornam contratos esperados"""

    def test_parse_numstat_returns_list(self):
        self.assertIsInstance(parse_numstat(""), [])

    def test_detect_functions_return_list(self):
        for fn in [detect_long_lines, detect_long_functions,
                   detect_todos_fixmes, detect_prints_logs,
                   detect_added_comments, detect_simple_duplication]:
            with self.subTest(fn=fn.__name__):
                result = fn("")
                self.assertIsInstance(result, list)

    def test_generate_html_returns_string(self):
        results = {"branch": "", "files": [], "critical": [], "warnings": [], "info": [], "diff_preview": ""}
        html = generate_html(results)
        self.assertIsInstance(html, str)
        self.assertTrue(html.startswith("<!DOCTYPE html>"))


if __name__ == "__main__":
    unittest.main()
