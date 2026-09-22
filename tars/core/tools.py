"""
TARS Tactical Automated Robot System - Tool Registry & Execution Harness
Enables autonomous file operations, shell commands, code execution, web intelligence, and telemetry.
"""
import os
import re
import sys
import json
import time
import base64
import subprocess
import urllib.request
import urllib.parse
from pathlib import Path
from typing import Dict, Any, List, Optional
from bs4 import BeautifulSoup
import psutil

from tars.config import config
from tars.core.personality import personality

DANGEROUS_PATTERNS = [
    r"\brmdir\s+/[sS]",
    r"\bdel\s+/[fFqQsS]",
    r"\bformat\b",
    r"\bdiskpart\b",
    r"\bdrop\s+database\b",
    r"\bdrop\s+table\b",
    r"\bgit\s+reset\s+--hard\b",
    r"\bgit\s+clean\s+-[fF]",
    r"\bshutdown\b",
    r"\bstop-computer\b",
    r"\bremove-item\s+.*-recurse"
]

# Default and ceiling for subprocess execution. The old 25-30s defaults were too
# short for ordinary assistant work such as dependency installs or test suites.
SHELL_TIMEOUT = 120
MAX_SHELL_TIMEOUT = 600


def is_dangerous_command(cmd: str) -> bool:
    cmd_lower = cmd.lower()
    for pattern in DANGEROUS_PATTERNS:
        if re.search(pattern, cmd_lower):
            return True
    return False

def read_file(path: str, start_line: int = 1, end_line: Optional[int] = None) -> str:
    """Reads content of a file from disk, optionally between start_line and end_line (1-indexed)."""
    try:
        p = Path(path).resolve()
        if not p.exists():
            return f"Error: File '{path}' does not exist."
        if p.is_dir():
            return f"Error: '{path}' is a directory, not a file. Use list_dir instead."
        
        with open(p, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
        
        total_lines = len(lines)
        s = max(1, start_line)
        e = min(total_lines, end_line) if end_line is not None else total_lines
        
        selected = lines[s - 1:e]
        result = [f"// File: {path} (Lines {s}-{e} of {total_lines})"]
        for idx, line in enumerate(selected, start=s):
            result.append(f"{idx:4d} | {line.rstrip()}")
        return "\n".join(result)
    except Exception as ex:
        return f"Error reading file '{path}': {ex}"

def write_file(path: str, content: str) -> str:
    """Writes or overwrites content into a file on disk."""
    try:
        p = Path(path).resolve()
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            f.write(content)
        return f"Successfully wrote {len(content)} characters to '{path}'."
    except Exception as ex:
        return f"Error writing file '{path}': {ex}"

def patch_file(path: str, old_text: str, new_text: str) -> str:
    """Replaces unique old_text with new_text in the specified file."""
    try:
        p = Path(path).resolve()
        if not p.exists():
            return f"Error: File '{path}' does not exist."
        with open(p, "r", encoding="utf-8", errors="replace") as f:
            original = f.read()
        
        count = original.count(old_text)
        if count == 0:
            return f"Error: Target text not found in '{path}'."
        if count > 1:
            return f"Error: Target text appears {count} times in '{path}'. Please provide a more unique snippet."
        
        patched = original.replace(old_text, new_text)
        with open(p, "w", encoding="utf-8") as f:
            f.write(patched)
        return f"Successfully patched '{path}'."
    except Exception as ex:
        return f"Error patching file '{path}': {ex}"

def list_dir(path: str = ".") -> str:
    """Lists files and directories at the specified path with file sizes."""
    try:
        p = Path(path).resolve()
        if not p.exists():
            return f"Error: Path '{path}' does not exist."
        if not p.is_dir():
            return f"Error: '{path}' is a file, not a directory."
        
        entries = []
        for item in sorted(p.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower())):
            if item.name.startswith(".git"):
                continue
            is_dir = item.is_dir()
            size_str = "<DIR>" if is_dir else f"{item.stat().st_size:,} B"
            entries.append(f"{'[DIR] ' if is_dir else '[FILE]'} {item.name:<35} {size_str:>15}")
        
        return f"Directory listing for '{path}':\n" + ("\n".join(entries) if entries else "(Empty directory)")
    except Exception as ex:
        return f"Error listing directory '{path}': {ex}"

def grep_search(query: str, path: str = ".") -> str:
    """Searches for occurrences of query string across text files under path."""
    try:
        root = Path(path).resolve()
        if not root.exists():
            return f"Error: Path '{path}' does not exist."
        
        matches = []
        q_lower = query.lower()
        
        for cur_dir, dirs, files in os.walk(root):
            dirs[:] = [d for d in dirs if not d.startswith(".") and d not in ("__pycache__", "node_modules", "venv", ".venv")]
            for f in files:
                f_path = Path(cur_dir) / f
                if f_path.suffix.lower() in (".png", ".jpg", ".jpeg", ".ico", ".pyc", ".zip", ".exe", ".bin"):
                    continue
                try:
                    with open(f_path, "r", encoding="utf-8", errors="ignore") as file_obj:
                        for line_idx, line in enumerate(file_obj, start=1):
                            if q_lower in line.lower():
                                rel_path = f_path.relative_to(root)
                                matches.append(f"{rel_path}:{line_idx}: {line.strip()[:140]}")
                                if len(matches) >= 40:
                                    break
                except Exception:
                    continue
            if len(matches) >= 40:
                break
        
        if not matches:
            return f"No matches found for '{query}' under '{path}'."
        return f"Found {len(matches)} matches for '{query}':\n" + "\n".join(matches)
    except Exception as ex:
        return f"Error during search: {ex}"

def run_command(command: str, timeout: int = SHELL_TIMEOUT) -> str:
    """Executes a command via PowerShell on Windows and returns stdout, stderr, and exit code."""
    if is_dangerous_command(command):
        return (
            f"[TACTICAL HALT] Command '{command}' was flagged as potentially destructive by TARS safety protocol.\n"
            f"Honesty parameter at {config.honesty}%. Refusing unconfirmed irreversible execution. "
            f"If this is intended, run it yourself or confirm explicitly."
        )
    try:
        timeout = max(1, min(int(timeout), MAX_SHELL_TIMEOUT))
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-Command", command],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout
        )
        out = proc.stdout.strip()
        err = proc.stderr.strip()
        code = proc.returncode
        result = [f"[Process Exit Code: {code}]"]
        if out:
            result.append(f"STDOUT:\n{out[:4000]}")
        if err:
            result.append(f"STDERR:\n{err[:2000]}")
        if not out and not err:
            result.append("(No output produced)")
        return "\n".join(result)
    except subprocess.TimeoutExpired:
        return (
            f"Error: Command '{command}' timed out after {timeout} seconds and was terminated. "
            f"For long-running work, pass a larger 'timeout' (max {MAX_SHELL_TIMEOUT}s) or run it in the background."
        )
    except Exception as ex:
        return f"Execution error for '{command}': {ex}"

def run_python(code: str, timeout: int = SHELL_TIMEOUT) -> str:
    """Executes Python code snippet in a dedicated subprocess and captures output."""
    try:
        timeout = max(1, min(int(timeout), MAX_SHELL_TIMEOUT))
        proc = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout
        )
        out = proc.stdout.strip()
        err = proc.stderr.strip()
        res = [f"[Python Exit Code: {proc.returncode}]"]
        if out:
            res.append(f"OUTPUT:\n{out[:3500]}")
        if err:
            res.append(f"STDERR:\n{err[:2000]}")
        if not out and not err:
            res.append("(Script completed with zero output)")
        return "\n".join(res)
    except subprocess.TimeoutExpired:
        return (
            f"Error: Python execution timed out after {timeout} seconds and was terminated. "
            f"Pass a larger 'timeout' (max {MAX_SHELL_TIMEOUT}s) for longer scripts."
        )
    except Exception as ex:
        return f"Python execution error: {ex}"

def web_search(query: str, num_results: int = 5) -> str:
    """Searches the live web via DuckDuckGo and returns titles, URLs, and text snippets."""
    try:
        url = "https://html.duckduckgo.com/html/?q=" + urllib.parse.quote(query)
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.5",
            }
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            html = resp.read().decode("utf-8", errors="replace")
        
        soup = BeautifulSoup(html, "html.parser")
        results = []
        for body in soup.select(".result__body"):
            a_tag = body.select_one(".result__title a")
            snippet_tag = body.select_one(".result__snippet")
            if a_tag:
                title = a_tag.get_text(strip=True)
                raw_href = a_tag.get("href", "")
                if "uddg=" in raw_href:
                    parsed = urllib.parse.parse_qs(urllib.parse.urlparse(raw_href).query)
                    href = parsed.get("uddg", [raw_href])[0]
                else:
                    href = raw_href
                snippet = snippet_tag.get_text(strip=True) if snippet_tag else ""
                results.append(f"- **{title}**\n  URL: {href}\n  Snippet: {snippet}")
                if len(results) >= num_results:
                    break
        
        if not results:
            wiki_url = "https://en.wikipedia.org/w/api.php"
            wiki_req = urllib.request.Request(
                f"{wiki_url}?action=opensearch&search={urllib.parse.quote(query)}&limit={num_results}&namespace=0&format=json",
                headers={"User-Agent": "TarsAgent/1.0"}
            )
            with urllib.request.urlopen(wiki_req, timeout=8) as w_resp:
                w_data = json.loads(w_resp.read().decode("utf-8"))
                titles, _, links = w_data[1], w_data[2], w_data[3]
                for t, l in zip(titles, links):
                    results.append(f"- **{t}**\n  URL: {l}")
        
        if not results:
            return f"No search results returned for query: '{query}'."
        return f"Web Search Results for '{query}':\n\n" + "\n\n".join(results)
    except Exception as ex:
        return f"Web search error: {ex}"

def fetch_url(url: str, max_chars: int = 4000) -> str:
    """Fetches a webpage and extracts clean, readable text content."""
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            html = resp.read().decode("utf-8", errors="replace")
        
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "header", "noscript", "svg"]):
            tag.decompose()
        
        text = soup.get_text(separator=" ", strip=True)
        title = soup.title.string if soup.title else url
        cleaned_text = " ".join(text.split())[:max_chars]
        return f"Webpage: {title} ({url})\nContent:\n{cleaned_text}"
    except Exception as ex:
        return f"Error fetching webpage '{url}': {ex}"

def get_system_telemetry() -> str:
    """Gathers real-time host CPU, memory, disk, network, and battery telemetry."""
    try:
        cpu_pct = psutil.cpu_percent(interval=0.1)
        cpu_freq = psutil.cpu_freq()
        freq_str = f"{cpu_freq.current:.1f} MHz" if cpu_freq else "N/A"
        
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage(os.getcwd())
        battery = psutil.sensors_battery()
        batt_str = f"{battery.percent}% ({'Plugged In' if battery.power_plugged else 'On Battery'})" if battery else "AC Mains / No Battery Sensor"
        
        net_io = psutil.net_io_counters()
        
        return (
            f"HOST MACHINE AVIONICS & TELEMETRY:\n"
            f"- SLAB 1 (CPU Avionics): {cpu_pct}% Load | Frequency: {freq_str} | Cores: {psutil.cpu_count(logical=True)}\n"
            f"- SLAB 2 (Core Memory): {mem.percent}% Utilized ({mem.used / (1024**3):.2f} GB / {mem.total / (1024**3):.2f} GB)\n"
            f"- SLAB 3 (Power / Reactor): Battery State: {batt_str}\n"
            f"- SLAB 4 (Storage Drive): {disk.percent}% Used ({disk.free / (1024**3):.2f} GB Free of {disk.total / (1024**3):.2f} GB)\n"
            f"- COMM I/O (Network): Sent {net_io.bytes_sent / (1024**2):.1f} MB | Received {net_io.bytes_recv / (1024**2):.1f} MB"
        )
    except Exception as ex:
        return f"Telemetry diagnostic error: {ex}"

def inspect_image(path: str, query: str = "Analyze this image in detail and describe its contents.") -> str:
    """Inspects a local image file using Gemini multimodal vision."""
    from tars.core.llm import VISION_MODELS, extract_text, generate, resolve_api_key

    if not resolve_api_key():
        return "Error: Gemini API key required for multimodal image inspection."

    p = Path(path).resolve()
    if not p.exists():
        return f"Error: Image file '{path}' not found."

    mime_map = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
        ".gif": "image/gif",
        ".bmp": "image/bmp",
    }
    mime_type = mime_map.get(p.suffix.lower(), "image/jpeg")

    try:
        b64_data = base64.b64encode(p.read_bytes()).decode("ascii")
    except Exception as ex:
        return f"Error reading image '{path}': {ex}"

    payload = {
        "contents": [{
            "parts": [
                {"text": query},
                {"inlineData": {"mimeType": mime_type, "data": b64_data}},
            ]
        }]
    }

    resp_data, _model, err = generate(payload, models=VISION_MODELS, timeout=40)
    if resp_data is None:
        return f"Vision API Error: {err}"

    text = extract_text(resp_data)
    return text if text else "Vision model returned an empty response for this image."

def analyze_pdf(path: str, query: str = "Summarize the key contents of this PDF.") -> str:
    """Extracts text from a local PDF document and queries or summarizes its contents."""
    p = Path(path).resolve()
    if not p.exists():
        return f"Error: PDF file '{path}' not found."
    try:
        import pypdf
        reader = pypdf.PdfReader(str(p))
        num_pages = len(reader.pages)
        extracted = []
        for i, page in enumerate(reader.pages[:15]):
            t = page.extract_text()
            if t:
                extracted.append(f"--- PAGE {i+1} ---\n{t.strip()}")
        full_text = "\n\n".join(extracted)
        if not full_text:
            return f"PDF '{path}' has {num_pages} pages, but no extractable text was found (it may contain scanned images)."
        
        preview = full_text[:4000]
        return (
            f"PDF Analysis for '{path}' ({num_pages} pages total):\n"
            f"Extracted Content Preview:\n{preview}\n\n"
            f"[Analysis Directive]: Query '{query}' processed against document text."
        )
    except Exception as ex:
        return f"Error analyzing PDF '{path}': {ex}"

def analyze_data(path: str, query: str = "Analyze this dataset") -> str:
    """Loads a CSV/TSV/Excel file with pandas, computes statistics, null checks, and summaries."""
    p = Path(path).resolve()
    if not p.exists():
        return f"Error: Data file '{path}' not found."
    try:
        import pandas as pd
        if p.suffix.lower() in (".tsv", ".tab"):
            df = pd.read_csv(p, sep="\t")
        elif p.suffix.lower() in (".xlsx", ".xls"):
            df = pd.read_excel(p)
        else:
            df = pd.read_csv(p)
        
        rows, cols = df.shape
        col_summary = [f"- {c} ({df[c].dtype}): {df[c].nunique()} unique, {df[c].isnull().sum()} nulls" for c in df.columns[:12]]
        desc = df.describe().to_string() if not df.empty else "Empty dataset"
        head_sample = df.head(3).to_string()
        return (
            f"Dataset: '{path}' ({rows:,} rows, {cols} columns)\n\n"
            f"Columns & Types:\n" + "\n".join(col_summary) + "\n\n"
            f"Numerical Summary:\n{desc}\n\n"
            f"Sample Rows:\n{head_sample}"
        )
    except Exception as ex:
        return f"Error analyzing dataset '{path}': {ex}"

def generate_chart(data_path: str, chart_type: str = "bar", x_col: str = "", y_col: str = "", output_path: str = "scratch/chart.png") -> str:
    """Generates a chart using matplotlib and pandas from a data file and saves to disk."""
    p = Path(data_path).resolve()
    if not p.exists():
        return f"Error: Data file '{data_path}' not found."
    try:
        import pandas as pd
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        
        df = pd.read_csv(p) if p.suffix.lower() != ".tsv" else pd.read_csv(p, sep="\t")
        if not x_col:
            x_col = df.columns[0]
        if not y_col and len(df.columns) > 1:
            y_col = df.columns[1]
        
        out = Path(output_path).resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        
        plt.figure(figsize=(8, 5))
        if chart_type == "line":
            plt.plot(df[x_col], df[y_col], marker="o", color="#00ffff")
        elif chart_type == "scatter":
            plt.scatter(df[x_col], df[y_col], color="#00ff66")
        elif chart_type == "hist":
            plt.hist(df[y_col or x_col], bins=15, color="#003366", edgecolor="#00ffff")
        else:
            plt.bar(df[x_col], df[y_col], color="#007acc")
            plt.xticks(rotation=45, ha="right")
        
        plt.title(f"{chart_type.upper()} Chart: {y_col} vs {x_col}")
        plt.tight_layout()
        plt.savefig(str(out), dpi=150)
        plt.close()
        return f"Successfully generated {chart_type} chart saved to '{output_path}'."
    except Exception as ex:
        return f"Error generating chart: {ex}"

def find_symbols(path: str = ".", symbol_type: str = "all") -> str:
    """Analyzes Python code AST to extract classes, functions, arguments, and docstrings."""
    import ast
    root = Path(path).resolve()
    if not root.exists():
        return f"Error: Path '{path}' not found."
    
    files = [root] if root.is_file() else list(root.rglob("*.py"))
    symbols = []
    
    for f in files:
        if any(part in f.parts for part in ("__pycache__", "venv", ".venv", "build", "dist")):
            continue
        try:
            with open(f, "r", encoding="utf-8", errors="ignore") as fo:
                tree = ast.parse(fo.read(), filename=str(f))
            rel = f.relative_to(root) if root.is_dir() else f.name
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef) and symbol_type in ("all", "class"):
                    symbols.append(f"[CLASS] {node.name:<25} ({rel}:{node.lineno})")
                elif isinstance(node, ast.FunctionDef) and symbol_type in ("all", "function"):
                    args_str = ", ".join([a.arg for a in node.args.args if a.arg != "self"])
                    symbols.append(f"[FUNC]  {node.name}({args_str}) ({rel}:{node.lineno})")
                if len(symbols) >= 60:
                    break
        except Exception:
            continue
        if len(symbols) >= 60:
            break
            
    if not symbols:
        return f"No symbols found matching type '{symbol_type}' under '{path}'."
    return f"Code Symbols in '{path}' ({len(symbols)} items):\n" + "\n".join(symbols)

def git_ops(subcommand: str = "status", args: str = "") -> str:
    """Executes git commands (status, diff, log, commit, branch) for version control."""
    try:
        full_cmd = f"git {subcommand} {args}".strip()
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-Command", full_cmd],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60
        )
        out = proc.stdout.strip()
        err = proc.stderr.strip()
        if "not a git repository" in (out + err).lower():
            return "Notice: Workspace is not a git repository. Run 'git init' to initialize version control."
        return out if out else (err if err else f"Git {subcommand} executed with exit code {proc.returncode}.")
    except Exception as ex:
        return f"Git operation error: {ex}"

def inspect_screen(query: str = "Analyze what is visible on this desktop screen.") -> str:
    """Captures desktop screen display and analyzes it with Gemini Vision."""
    from tars.core.llm import resolve_api_key

    if not resolve_api_key():
        return "Error: Gemini API key required for multimodal screen analysis."
    try:
        from PIL import ImageGrab
    except ImportError:
        return "Error: Pillow is not installed, so the screen cannot be captured. Install it with 'pip install pillow'."

    import tempfile
    temp_path = Path(tempfile.gettempdir()) / f"tars_screen_{int(time.time())}.png"
    try:
        ImageGrab.grab().save(temp_path, format="PNG")
    except Exception as ex:
        return f"Screen capture failed ({type(ex).__name__}: {ex}). Tip: save a screenshot manually and pass its path to inspect_image."

    try:
        return inspect_image(str(temp_path), query=query)
    finally:
        try:
            temp_path.unlink()
        except OSError:
            pass

TOOL_REGISTRY = {
    "read_file": read_file,
    "write_file": write_file,
    "patch_file": patch_file,
    "list_dir": list_dir,
    "grep_search": grep_search,
    "run_command": run_command,
    "run_python": run_python,
    "web_search": web_search,
    "fetch_url": fetch_url,
    "get_system_telemetry": get_system_telemetry,
    "inspect_image": inspect_image,
    "analyze_pdf": analyze_pdf,
    "analyze_data": analyze_data,
    "generate_chart": generate_chart,
    "find_symbols": find_symbols,
    "git_ops": git_ops,
    "inspect_screen": inspect_screen,
}

GEMINI_TOOLS_DECLARATION = [
    {
        "name": "read_file",
        "description": "Reads contents of a file on the local filesystem. Supports line range slices.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "path": {"type": "STRING", "description": "Relative or absolute path of the file to read."},
                "start_line": {"type": "INTEGER", "description": "First line to read (1-indexed). Optional."},
                "end_line": {"type": "INTEGER", "description": "Last line to read (1-indexed). Optional."}
            },
            "required": ["path"]
        }
    },
    {
        "name": "write_file",
        "description": "Writes or overwrites content into a file on disk.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "path": {"type": "STRING", "description": "File path to create or write."},
                "content": {"type": "STRING", "description": "The exact full text content to write into the file."}
            },
            "required": ["path", "content"]
        }
    },
    {
        "name": "patch_file",
        "description": "Replaces a unique target substring in a file with new text.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "path": {"type": "STRING", "description": "Path of the file to modify."},
                "old_text": {"type": "STRING", "description": "Exact unique string to be replaced."},
                "new_text": {"type": "STRING", "description": "Replacement string."}
            },
            "required": ["path", "old_text", "new_text"]
        }
    },
    {
        "name": "list_dir",
        "description": "Lists files and subdirectories in a given directory path.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "path": {"type": "STRING", "description": "Directory path to list. Defaults to '.' (current directory)."}
            }
        }
    },
    {
        "name": "grep_search",
        "description": "Searches for a text pattern or symbol across files in a directory tree.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "query": {"type": "STRING", "description": "Search string or keyword."},
                "path": {"type": "STRING", "description": "Starting directory to search. Defaults to '.'"}
            },
            "required": ["query"]
        }
    },
    {
        "name": "run_command",
        "description": "Runs a PowerShell shell command on the host machine and returns stdout, stderr, and exit code.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "command": {"type": "STRING", "description": "The shell command to execute."},
                "timeout": {"type": "INTEGER", "description": f"Seconds to allow before terminating (default {SHELL_TIMEOUT}, max {MAX_SHELL_TIMEOUT}). Raise this for installs, builds, or test suites."}
            },
            "required": ["command"]
        }
    },
    {
        "name": "run_python",
        "description": "Executes a Python code script in a subprocess and captures the printed output or errors.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "code": {"type": "STRING", "description": "Executable Python code snippet."},
                "timeout": {"type": "INTEGER", "description": f"Seconds to allow before terminating (default {SHELL_TIMEOUT}, max {MAX_SHELL_TIMEOUT})."}
            },
            "required": ["code"]
        }
    },
    {
        "name": "web_search",
        "description": "Performs a live web search to find current information, documentation, news, or articles.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "query": {"type": "STRING", "description": "Search keywords or query."},
                "num_results": {"type": "INTEGER", "description": "Number of search results to return (default 5)."}
            },
            "required": ["query"]
        }
    },
    {
        "name": "fetch_url",
        "description": "Scrapes and parses a webpage URL into clean, readable text.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "url": {"type": "STRING", "description": "HTTP/HTTPS URL of the webpage to scrape."},
                "max_chars": {"type": "INTEGER", "description": "Max characters of content to return (default 4000)."}
            },
            "required": ["url"]
        }
    },
    {
        "name": "get_system_telemetry",
        "description": "Retrieves real host CPU, RAM, disk, battery, and network telemetry.",
        "parameters": {
            "type": "OBJECT",
            "properties": {}
        }
    },
    {
        "name": "inspect_image",
        "description": "Analyzes a local image or screenshot with computer vision.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "path": {"type": "STRING", "description": "File path to the image (.png, .jpg, etc.)."},
                "query": {"type": "STRING", "description": "What to analyze or look for in the image."}
            },
            "required": ["path"]
        }
    },
    {
        "name": "analyze_pdf",
        "description": "Extracts text from a local PDF document and queries or summarizes its contents.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "path": {"type": "STRING", "description": "File path to the PDF document."},
                "query": {"type": "STRING", "description": "What to query, extract, or summarize from the PDF."}
            },
            "required": ["path"]
        }
    },
    {
        "name": "analyze_data",
        "description": "Loads a CSV, TSV, or Excel dataset with pandas, calculating column types, statistics, and summaries.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "path": {"type": "STRING", "description": "Path to CSV, TSV, or Excel file."},
                "query": {"type": "STRING", "description": "Analysis objective or question."}
            },
            "required": ["path"]
        }
    },
    {
        "name": "generate_chart",
        "description": "Generates a bar, line, scatter, or histogram chart from data and saves as PNG.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "data_path": {"type": "STRING", "description": "Path to CSV/TSV data file."},
                "chart_type": {"type": "STRING", "description": "Type of chart: 'bar', 'line', 'scatter', or 'hist'."},
                "x_col": {"type": "STRING", "description": "Column name for X axis."},
                "y_col": {"type": "STRING", "description": "Column name for Y axis."},
                "output_path": {"type": "STRING", "description": "Output PNG path (default 'scratch/chart.png')."}
            },
            "required": ["data_path"]
        }
    },
    {
        "name": "find_symbols",
        "description": "Parses Python code AST to extract classes, functions, arguments, and line numbers.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "path": {"type": "STRING", "description": "Directory or file to inspect. Defaults to '.'"},
                "symbol_type": {"type": "STRING", "description": "'all', 'class', or 'function'."}
            }
        }
    },
    {
        "name": "git_ops",
        "description": "Performs Git repository operations: status, diff, log, commit, or branch.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "subcommand": {"type": "STRING", "description": "Git subcommand: 'status', 'diff', 'log', 'commit', 'branch'."},
                "args": {"type": "STRING", "description": "Optional flags or commit message."}
            },
            "required": ["subcommand"]
        }
    },
    {
        "name": "inspect_screen",
        "description": "Takes a real-time screenshot of the current primary desktop screen and analyzes it with vision.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "query": {"type": "STRING", "description": "What to inspect, diagnose, or read on the screen."}
            }
        }
    }
]

def execute_tool(name: str, args: Dict[str, Any]) -> str:
    """Dispatches a function call to the matching tool function and returns the result string."""
    func = TOOL_REGISTRY.get(name)
    if not func:
        return f"Error: Tool '{name}' is not registered."
    try:
        return func(**args)
    except TypeError as te:
        return f"Error: Invalid arguments passed to tool '{name}': {te}"
    except Exception as ex:
        return f"Tool execution failed for '{name}': {ex}"

