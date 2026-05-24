import os
import re
import sys
import ast
import json
import math
import datetime
from pathlib import Path

# Common directories and file extensions to ignore
IGNORE_DIRS = {
    "node_modules", ".git", "__pycache__", ".next", "dist", "build",
    ".cache", "coverage", ".nyc_output", "target", "venv", ".venv", "history"
}
IGNORE_EXT = {
    ".pyc", ".pyo", ".exe", ".dll", ".so", ".dylib", ".bin",
    ".jpg", ".png", ".gif", ".ico", ".svg", ".woff", ".woff2", ".pdf", ".zip", ".tar", ".gz"
}


# ─── Extractor Functions ───────────────────────────────────

def extract_python_symbols(filepath, project_path):
    """Parses a Python file using AST to extract classes, functions, methods, and constants."""
    try:
        content = filepath.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return []

    try:
        tree = ast.parse(content)
    except SyntaxError:
        return []

    symbols = []
    lines = content.splitlines()

    for node in tree.body:
        # Class definitions
        if isinstance(node, ast.ClassDef):
            start_line = node.lineno
            end_line = getattr(node, "end_lineno", start_line + 10)
            snippet = "\n".join(lines[start_line - 1 : end_line])
            docstring = ast.get_docstring(node) or ""

            # Class method parsing
            methods = []
            for child in node.body:
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    is_async = isinstance(child, ast.AsyncFunctionDef)
                    m_start = child.lineno
                    m_end = getattr(child, "end_lineno", m_start + 5)
                    m_snippet = "\n".join(lines[m_start - 1 : m_end])
                    args = [arg.arg for arg in child.args.args]
                    prefix = "async def" if is_async else "def"
                    sig = f"{prefix} {child.name}({', '.join(args)})"
                    m_doc = ast.get_docstring(child) or ""
                    
                    methods.append({
                        "name": f"{node.name}.{child.name}",
                        "type": "method",
                        "line": m_start,
                        "signature": f"{node.name}.{sig}",
                        "docstring": m_doc,
                        "snippet": m_snippet
                    })

            sig = f"class {node.name}"
            symbols.append({
                "name": node.name,
                "type": "class",
                "line": start_line,
                "signature": sig,
                "docstring": docstring,
                "snippet": snippet,
                "methods": methods
            })

        # Function definitions (top-level)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            is_async = isinstance(node, ast.AsyncFunctionDef)
            start_line = node.lineno
            end_line = getattr(node, "end_lineno", start_line + 5)
            snippet = "\n".join(lines[start_line - 1 : end_line])
            args = [arg.arg for arg in node.args.args]
            prefix = "async def" if is_async else "def"
            sig = f"{prefix} {node.name}({', '.join(args)})"
            docstring = ast.get_docstring(node) or ""
            symbols.append({
                "name": node.name,
                "type": "function",
                "line": start_line,
                "signature": sig,
                "docstring": docstring,
                "snippet": snippet
            })

        # Top-level variables and constants
        elif isinstance(node, ast.Assign):
            start_line = node.lineno
            snippet = lines[start_line - 1] if start_line <= len(lines) else ""
            for target in node.targets:
                if isinstance(target, ast.Name):
                    symbols.append({
                        "name": target.id,
                        "type": "variable",
                        "line": start_line,
                        "signature": f"{target.id} = ...",
                        "docstring": "",
                        "snippet": snippet
                    })
    return symbols


def extract_js_ts_symbols(filepath, project_path):
    """Parses JavaScript/TypeScript files using Regex to find classes, functions, routes, and constants."""
    try:
        content = filepath.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return []

    symbols = []
    lines = content.splitlines()

    # Classes: class MyClass [extends BaseClass]
    for m in re.finditer(r'\bclass\s+([A-Za-z0-9_$]+)(?:\s+extends\s+[A-Za-z0-9_$.]+)?', content):
        start_pos = m.start()
        line_num = content[:start_pos].count('\n') + 1
        snippet = "\n".join(lines[line_num - 1 : line_num + 9])
        symbols.append({
            "name": m.group(1),
            "type": "class",
            "line": line_num,
            "signature": m.group(0),
            "docstring": "",
            "snippet": snippet
        })

    # Named functions: function myFunc(a, b) or async function myFunc(a, b)
    for m in re.finditer(r'\b(?:async\s+)?function\s+([A-Za-z0-9_$]+)\s*\(([^)]*)\)', content):
        start_pos = m.start()
        line_num = content[:start_pos].count('\n') + 1
        snippet = "\n".join(lines[line_num - 1 : line_num + 4])
        symbols.append({
            "name": m.group(1),
            "type": "function",
            "line": line_num,
            "signature": f"function {m.group(1)}({m.group(2)})",
            "docstring": "",
            "snippet": snippet
        })

    # Arrow functions assigned to variables: const myFunc = (a, b) => ...
    for m in re.finditer(r'\b(?:const|let|var)\s+([A-Za-z0-9_$]+)\s*=\s*(?:async\s*)?\(([^)]*)\)\s*=>', content):
        start_pos = m.start()
        line_num = content[:start_pos].count('\n') + 1
        snippet = "\n".join(lines[line_num - 1 : line_num + 4])
        symbols.append({
            "name": m.group(1),
            "type": "function",
            "line": line_num,
            "signature": f"const {m.group(1)} = ({m.group(2)}) => ...",
            "docstring": "",
            "snippet": snippet
        })

    # Express-like Route signatures: app.get('/endpoint', ...)
    for m in re.finditer(r'\b(?:app|router|server)\.(get|post|put|delete|patch|use)\s*\(\s*[\'"`]([^\'"`]+)[\'"`]', content):
        start_pos = m.start()
        line_num = content[:start_pos].count('\n') + 1
        snippet = "\n".join(lines[line_num - 1 : line_num + 4])
        symbols.append({
            "name": f"{m.group(1).upper()} {m.group(2)}",
            "type": "route",
            "line": line_num,
            "signature": m.group(0) + "...",
            "docstring": "",
            "snippet": snippet
        })

    # Top-level Constants (indicated by uppercase variable name): const MY_CONSTANT = ...
    for m in re.finditer(r'\bconst\s+([A-Z0-9_$]+)\s*=', content):
        start_pos = m.start()
        line_num = content[:start_pos].count('\n') + 1
        snippet = lines[line_num - 1] if line_num <= len(lines) else ""
        symbols.append({
            "name": m.group(1),
            "type": "constant",
            "line": line_num,
            "signature": f"const {m.group(1)}",
            "docstring": "",
            "snippet": snippet
        })

    return symbols


def extract_html_symbols(filepath, project_path):
    """Parses HTML files using Regex to find IDs, script imports, and style links."""
    try:
        content = filepath.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return []

    symbols = []
    lines = content.splitlines()

    # Elements with IDs: id="my-element"
    for m in re.finditer(r'<[^>]*\bid=["\']([^"\']+)["\']', content):
        start_pos = m.start()
        line_num = content[:start_pos].count('\n') + 1
        snippet = lines[line_num - 1] if line_num <= len(lines) else ""
        symbols.append({
            "name": m.group(1),
            "type": "element_id",
            "line": line_num,
            "signature": f"id=\"{m.group(1)}\"",
            "docstring": "",
            "snippet": snippet
        })

    # Script Imports: <script src="..."></script>
    for m in re.finditer(r'<script\s+[^>]*\bsrc=["\']([^"\']+)["\']', content):
        start_pos = m.start()
        line_num = content[:start_pos].count('\n') + 1
        snippet = lines[line_num - 1] if line_num <= len(lines) else ""
        symbols.append({
            "name": m.group(1),
            "type": "script_import",
            "line": line_num,
            "signature": f"<script src=\"{m.group(1)}\">",
            "docstring": "",
            "snippet": snippet
        })

    # Stylesheet links: <link rel="stylesheet" href="...">
    for m in re.finditer(r'<link\s+[^>]*\bhref=["\']([^"\']+)["\']', content):
        start_pos = m.start()
        line_num = content[:start_pos].count('\n') + 1
        snippet = lines[line_num - 1] if line_num <= len(lines) else ""
        symbols.append({
            "name": m.group(1),
            "type": "stylesheet_link",
            "line": line_num,
            "signature": f"<link href=\"{m.group(1)}\">",
            "docstring": "",
            "snippet": snippet
        })

    return symbols


def extract_css_symbols(filepath, project_path):
    """Parses CSS/SCSS files to extract classes and IDs."""
    try:
        content = filepath.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return []

    symbols = []
    lines = content.splitlines()

    # Class rules: .class-name {
    for m in re.finditer(r'\.([a-zA-Z0-9_-]+)\s*\{', content):
        start_pos = m.start()
        line_num = content[:start_pos].count('\n') + 1
        snippet = "\n".join(lines[line_num - 1 : line_num + 4])
        symbols.append({
            "name": f".{m.group(1)}",
            "type": "css_class",
            "line": line_num,
            "signature": f".{m.group(1)} {{ ... }}",
            "docstring": "",
            "snippet": snippet
        })

    # ID rules: #id-name {
    for m in re.finditer(r'#([a-zA-Z0-9_-]+)\s*\{', content):
        start_pos = m.start()
        line_num = content[:start_pos].count('\n') + 1
        snippet = "\n".join(lines[line_num - 1 : line_num + 4])
        symbols.append({
            "name": f"#{m.group(1)}",
            "type": "css_id",
            "line": line_num,
            "signature": f"#{m.group(1)} {{ ... }}",
            "docstring": "",
            "snippet": snippet
        })

    return symbols


# ─── Search Engine Implementation ──────────────────────────

class CodeSearchEngine:
    def __init__(self, index_data):
        self.index_data = index_data
        self.documents = []  # Flattened list of symbols and methods
        self.df = {}         # Inverse document frequency storage
        self.N = 0           # Total document count

        self._build_documents()
        self._calculate_idf()

    def _tokenize(self, text):
        if not text:
            return []
        # Find alphanumeric words, lowercase
        words = re.findall(r'[a-zA-Z0-9_]+', text.lower())
        stopwords = {
            "the", "a", "of", "and", "to", "in", "is", "for", "on", "that", "this", "with", "as", "by", "an", "it",
            "o", "a", "os", "as", "de", "do", "da", "dos", "das", "em", "um", "uma", "para", "com", "por", "que", "se", "no"
        }
        return [w for w in words if w not in stopwords and len(w) > 1]

    def _build_documents(self):
        for filepath, file_data in self.index_data.get("files", {}).items():
            for sym in file_data.get("symbols", []):
                doc = {
                    "file": filepath,
                    "name": sym.get("name", ""),
                    "type": sym.get("type", ""),
                    "line": sym.get("line", 1),
                    "signature": sym.get("signature", ""),
                    "docstring": sym.get("docstring", ""),
                    "snippet": sym.get("snippet", ""),
                }

                # Tokenize parts
                name_tokens = self._tokenize(doc["name"])
                sig_tokens = self._tokenize(doc["signature"])
                docstring_tokens = self._tokenize(doc["docstring"])
                snippet_tokens = self._tokenize(doc["snippet"])

                # local term frequencies (with boosts for specific fields)
                terms = {}
                for w in name_tokens:
                    terms[w] = terms.get(w, 0.0) + 5.0
                for w in sig_tokens:
                    terms[w] = terms.get(w, 0.0) + 3.0
                for w in docstring_tokens:
                    terms[w] = terms.get(w, 0.0) + 1.5
                for w in snippet_tokens:
                    terms[w] = terms.get(w, 0.0) + 1.0

                doc["terms"] = terms
                doc["length"] = sum(terms.values())
                self.documents.append(doc)

                # Flatten inner class methods
                for method in sym.get("methods", []):
                    m_doc = {
                        "file": filepath,
                        "name": method.get("name", ""),
                        "type": "method",
                        "line": method.get("line", 1),
                        "signature": method.get("signature", ""),
                        "docstring": method.get("docstring", ""),
                        "snippet": method.get("snippet", ""),
                    }
                    m_name_tokens = self._tokenize(m_doc["name"])
                    m_sig_tokens = self._tokenize(m_doc["signature"])
                    m_docstring_tokens = self._tokenize(m_doc["docstring"])
                    m_snippet_tokens = self._tokenize(m_doc["snippet"])

                    m_terms = {}
                    for w in m_name_tokens:
                        m_terms[w] = m_terms.get(w, 0.0) + 5.0
                    for w in m_sig_tokens:
                        m_terms[w] = m_terms.get(w, 0.0) + 3.0
                    for w in m_docstring_tokens:
                        m_terms[w] = m_terms.get(w, 0.0) + 1.5
                    for w in m_snippet_tokens:
                        m_terms[w] = m_terms.get(w, 0.0) + 1.0

                    m_doc["terms"] = m_terms
                    m_doc["length"] = sum(m_terms.values())
                    self.documents.append(m_doc)

        self.N = len(self.documents)

    def _calculate_idf(self):
        for doc in self.documents:
            for term in doc["terms"]:
                self.df[term] = self.df.get(term, 0) + 1

    def search(self, query_str, limit=15):
        query_tokens = self._tokenize(query_str)
        if not query_tokens or self.N == 0:
            return []

        results = []
        for doc in self.documents:
            score = 0.0
            matches = 0
            for term in query_tokens:
                # Direct check
                if term in doc["terms"]:
                    matches += 1
                    tf = doc["terms"][term]
                    df_t = self.df.get(term, 0)
                    idf = math.log(1.0 + self.N / (1.0 + df_t))
                    score += tf * idf * idf
                else:
                    # Soft prefix/substring match check for partial queries (e.g. searching 'run' matching 'run_cmd')
                    # We iterate over terms in doc and see if query term is a substring
                    for doc_term in doc["terms"]:
                        if term in doc_term:
                            matches += 0.5  # Partial match penalty
                            tf = doc["terms"][doc_term] * 0.5
                            df_t = self.df.get(doc_term, 0)
                            idf = math.log(1.0 + self.N / (1.0 + df_t))
                            score += tf * idf * idf
                            break

            if score > 0.0:
                coord_match = matches / len(query_tokens)
                # length normalization + coordinate weight boost
                norm_score = (score / math.sqrt(doc["length"] + 1.0)) * coord_match
                results.append({
                    "file": doc["file"],
                    "name": doc["name"],
                    "type": doc["type"],
                    "line": doc["line"],
                    "signature": doc["signature"],
                    "docstring": doc["docstring"],
                    "snippet": doc["snippet"],
                    "score": round(norm_score, 4)
                })

        # Sort descending by score
        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:limit]


# ─── Storage and CLI ───────────────────────────────────────

def get_index_path(project_path):
    return Path(project_path) / ".ai-flow" / "project-index.json"


def index_project(project_path):
    """Scans and indexes the project directories for code structures."""
    project_path = Path(project_path).resolve()
    files_data = {}

    for root_dir, dirs, files in os.walk(project_path):
        # Exclude directories in-place to optimize traversal
        dirs[:] = [d for d in dirs if d not in IGNORE_DIRS and (not d.startswith(".") or d == ".ai-flow")]

        for file in files:
            file_path = Path(root_dir) / file
            if file_path.suffix.lower() in IGNORE_EXT:
                continue
            # Ignore hidden files unless they are common configurations
            if file.startswith(".") and file not in (".env.example", ".gitignore"):
                continue

            rel_path = file_path.relative_to(project_path).as_posix()
            ext = file_path.suffix.lower()
            symbols = []

            # Routing based on file extension
            if ext == ".py":
                symbols = extract_python_symbols(file_path, project_path)
            elif ext in (".js", ".ts", ".jsx", ".tsx"):
                symbols = extract_js_ts_symbols(file_path, project_path)
            elif ext in (".html", ".htm"):
                symbols = extract_html_symbols(file_path, project_path)
            elif ext in (".css", ".scss"):
                symbols = extract_css_symbols(file_path, project_path)

            if symbols:
                files_data[rel_path] = {
                    "language": ext[1:] if ext.startswith(".") else ext,
                    "symbols": symbols
                }

    index_data = {
        "project_path": str(project_path),
        "last_indexed": datetime.datetime.now().isoformat(),
        "files": files_data
    }

    index_path = get_index_path(project_path)
    index_path.parent.mkdir(parents=True, exist_ok=True)
    with open(index_path, "w", encoding="utf-8") as f:
        json.dump(index_data, f, indent=2, ensure_ascii=False)

    return index_data


def load_or_build_index(project_path, force_reindex=False):
    """Loads existing index if available, else indices the codebase."""
    index_path = get_index_path(project_path)
    if not force_reindex and index_path.exists():
        try:
            with open(index_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return index_project(project_path)


def search_context(project_path, query_str, force_reindex=False, limit=15):
    """API entry point for querying the code relevance index."""
    index_data = load_or_build_index(project_path, force_reindex)
    engine = CodeSearchEngine(index_data)
    return engine.search(query_str, limit=limit)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="AI-Flow Code Indexer and Context Search")
    parser.add_argument("--index", help="Index the specified project path")
    parser.add_argument("--search", help="Search query string")
    parser.add_argument("--path", help="Project path to search in (defaults to current dir)", default=".")
    parser.add_argument("--reindex", action="store_true", help="Force reindexing before search")
    args = parser.parse_args()

    if args.index:
        print(f"Indexing project: {args.index} ...", end="", flush=True)
        index_project(args.index)
        print(" [OK]")
    elif args.search:
        proj_path = Path(args.path).resolve()
        results = search_context(proj_path, args.search, force_reindex=args.reindex)
        print(json.dumps(results, indent=2, ensure_ascii=False))
    else:
        parser.print_help()
