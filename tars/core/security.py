"""
TARS - Security Boundary

Three responsibilities, kept in one place so the rules are auditable:

  1. Path containment. Filesystem tools resolve through resolve_safe_path(),
     which confines them to an explicit set of allowed roots and refuses
     sensitive files (credentials, keys, browser profiles) even inside those
     roots.
  2. Payload classification. Shell and Python payloads are classified
     SAFE / SENSITIVE / BLOCKED. BLOCKED never runs. SENSITIVE runs only after
     the operator confirms at the terminal, and denies itself on timeout.
  3. Audit. Every host action and every gated decision is appended to
     mission_logs/audit.jsonl, so there is a durable record of what ran.

Design note: the original model was a denylist of eleven regexes consulted only
by run_command. run_python bypassed it entirely, aliases (ri, rd, rm) and
pipeline deletes walked straight through, and write_file could stage a .ps1 that
run_command then executed. Denylists are the wrong shape for this job. Path
containment is now an allowlist; the command denylist has been demoted to a
coarse backstop rather than the primary control.
"""
from __future__ import annotations

import ctypes
import fnmatch
import json
import os
import re
import sys
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable, List, Optional, Sequence, Tuple

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
AUDIT_DIR = PROJECT_ROOT / "mission_logs"
AUDIT_FILE = AUDIT_DIR / "audit.jsonl"

# ─── Risk levels ────────────────────────────────────────────────────────────

SAFE = "SAFE"
SENSITIVE = "SENSITIVE"
BLOCKED = "BLOCKED"


@dataclass(frozen=True)
class Verdict:
    """Outcome of classifying a payload."""

    level: str
    reason: str = ""

    @property
    def allowed_outright(self) -> bool:
        return self.level == SAFE

    @property
    def blocked(self) -> bool:
        return self.level == BLOCKED


# ─── Sensitive path rules ───────────────────────────────────────────────────
# Matched case-insensitively against the resolved path. These win even when the
# file sits inside an allowed root: containment and secrecy are separate checks.

_SENSITIVE_FILENAMES = {
    ".env",
    ".flaskenv",
    ".tars_config.json",
    ".git-credentials",
    ".netrc",
    "_netrc",
    ".npmrc",
    ".pypirc",
    ".dockercfg",
    ".htpasswd",
    ".my.cnf",
    "id_rsa",
    "id_dsa",
    "id_ecdsa",
    "id_ed25519",
    "identity",
    "credentials",
    "credentials.json",
    "client_secret.json",
    "service-account.json",
    "secrets.json",
    "secrets.yaml",
    "secrets.yml",
    "ntuser.dat",
    "sam",
    "security",
    "login data",
    "login data for account",
    "cookies",
    "web data",
    "key3.db",
    "key4.db",
    "logins.json",
    "cert9.db",
    "signons.sqlite",
    "shadow",
    "master.key",
}

_SENSITIVE_GLOBS = (
    ".env.*",
    "*.pem",
    "*.key",
    "*.pfx",
    "*.p12",
    "*.jks",
    "*.keystore",
    "*.ppk",
    "*.kdbx",
    "*.asc",
    "*.gpg",
    "*_rsa",
    "*_ed25519",
    "*.ovpn",
    "*token*.json",
    "*secret*.json",
    "*.sqlite-wal",
)

# Any path traversing one of these directory names is refused outright.
_SENSITIVE_DIRS = {
    ".ssh",
    ".aws",
    ".azure",
    ".gnupg",
    ".gpg",
    ".kube",
    ".docker",
    ".password-store",
    "protect",           # DPAPI master keys
    "credentials",
    "microsoft\\crypto",
    "keychains",
}

# Absolute prefixes that are never writable, regardless of configured roots.
_NEVER_WRITABLE_PREFIXES = (
    "c:\\windows",
    "c:\\program files",
    "c:\\program files (x86)",
    "c:\\programdata\\microsoft\\windows",
    "/etc",
    "/bin",
    "/sbin",
    "/usr/bin",
    "/boot",
)

# Files TARS may read but must never overwrite, because doing so corrupts its
# own state or the operator's history.
_WRITE_PROTECTED_NAMES = {
    ".tars_memory.json",
    "audit.jsonl",
}


def _norm(p: Path) -> str:
    return str(p).replace("/", os.sep).lower()


def allowed_roots() -> List[Path]:
    """
    Every directory tree the filesystem tools may touch.

    Workspace root plus the system temp directory (screenshots and synthesised
    speech land there), plus anything the operator has explicitly added via
    `config.allowed_fs_roots`. Deliberately does not include the home directory.
    """
    roots = [PROJECT_ROOT, Path(tempfile.gettempdir()).resolve()]
    try:
        from tars.config import config

        for extra in getattr(config, "allowed_fs_roots", []) or []:
            try:
                candidate = Path(os.path.expandvars(os.path.expanduser(str(extra)))).resolve()
            except (OSError, ValueError):
                continue
            if candidate.exists() and candidate.is_dir():
                roots.append(candidate)
    except Exception:
        pass

    # De-duplicate while preserving order.
    seen: set = set()
    unique: List[Path] = []
    for r in roots:
        key = _norm(r)
        if key not in seen:
            seen.add(key)
            unique.append(r)
    return unique


def _within(path: Path, root: Path) -> bool:
    """True when `path` is `root` or sits beneath it. Symlink-resolved already."""
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def is_sensitive_path(path: Path) -> Tuple[bool, str]:
    """
    Returns (sensitive, reason). Checks the filename, its extension pattern, and
    every directory component of the resolved path.
    """
    name = path.name.lower()

    if name in _SENSITIVE_FILENAMES:
        return True, f"'{path.name}' is a credential or secret store"

    for pattern in _SENSITIVE_GLOBS:
        if fnmatch.fnmatch(name, pattern):
            return True, f"'{path.name}' matches protected pattern '{pattern}'"

    lowered_parts = [part.lower() for part in path.parts]
    for part in lowered_parts:
        if part in _SENSITIVE_DIRS:
            return True, f"path traverses protected directory '{part}'"

    joined = _norm(path)
    for frag in ("\\appdata\\local\\google\\chrome\\user data",
                 "\\appdata\\roaming\\mozilla\\firefox\\profiles",
                 "\\appdata\\local\\microsoft\\edge\\user data",
                 "\\appdata\\local\\microsoft\\credentials",
                 "\\appdata\\roaming\\microsoft\\credentials"):
        if frag in joined:
            return True, "path is inside a browser or credential profile store"

    return False, ""


def resolve_safe_path(
    raw_path: str,
    for_write: bool = False,
    must_exist: bool = False,
) -> Tuple[Optional[Path], str]:
    """
    Resolves `raw_path` and validates it against the boundary.

    Returns (path, "") when allowed, or (None, human-readable refusal). Relative
    paths resolve against the workspace root rather than the process CWD, so the
    answer does not depend on where TARS was launched from.
    """
    if not raw_path or not str(raw_path).strip():
        return None, "Error: no path supplied."

    text = str(raw_path).strip().strip('"').strip("'")

    try:
        expanded = os.path.expandvars(os.path.expanduser(text))
        candidate = Path(expanded)
        if not candidate.is_absolute():
            candidate = PROJECT_ROOT / candidate
        # strict=False so we can validate paths that do not exist yet (writes).
        resolved = candidate.resolve()
    except (OSError, ValueError, RuntimeError) as ex:
        return None, f"Error: path '{raw_path}' could not be resolved ({ex})."

    sensitive, why = is_sensitive_path(resolved)
    if sensitive:
        audit_action("filesystem", "path_refused", {"path": str(resolved), "reason": why}, "refused")
        return None, (
            f"[BOUNDARY] Refused: {why}. TARS does not read or write credential "
            f"material. If you need this specific file, open it yourself."
        )

    roots = allowed_roots()
    if not any(_within(resolved, root) for root in roots):
        root_list = "\n".join(f"  - {r}" for r in roots)
        audit_action("filesystem", "path_outside_root", {"path": str(resolved)}, "refused")
        return None, (
            f"[BOUNDARY] Refused: '{resolved}' is outside every allowed root.\n"
            f"Allowed roots:\n{root_list}\n"
            f"Add one with:  roots add <directory>"
        )

    if for_write:
        lowered = _norm(resolved)
        for prefix in _NEVER_WRITABLE_PREFIXES:
            if lowered.startswith(prefix):
                audit_action("filesystem", "write_to_system_path", {"path": str(resolved)}, "refused")
                return None, f"[BOUNDARY] Refused: '{resolved}' is a protected system location."
        if resolved.name.lower() in _WRITE_PROTECTED_NAMES:
            return None, (
                f"[BOUNDARY] Refused: '{resolved.name}' is TARS-managed state and is "
                f"read-only to tools."
            )

    if must_exist and not resolved.exists():
        return None, f"Error: '{raw_path}' does not exist."

    return resolved, ""


def skip_during_walk(path: Path) -> bool:
    """Cheap predicate for grep_search and other tree walkers."""
    sensitive, _ = is_sensitive_path(path)
    return sensitive


# ─── Payload classification ─────────────────────────────────────────────────
# Kept as a coarse backstop. It is not the primary control -- an explicit shell
# tool is inherently broad -- but it catches the irreversible cases and forces a
# confirmation on the merely dangerous ones.

_BLOCKED_SHELL = [
    (r"\bformat\s+[a-z]:", "disk format"),
    (r"\bdiskpart\b", "raw partition editor"),
    (r"\bbcdedit\b", "boot configuration editor"),
    (r"\bvssadmin\s+delete\b", "shadow copy deletion"),
    (r"\bwbadmin\s+delete\b", "backup deletion"),
    (r"\bcipher\s+/w", "free-space wipe"),
    (r"\bdrop\s+(database|table)\b", "destructive SQL"),
    (r"\bmkfs\b", "filesystem creation"),
    (r"\bdd\s+if=.*\bof=/dev/", "raw device write"),
    (r"set-mppreference\s+.*disablerealtimemonitoring\s*\$?true", "disabling Defender"),
    (r"\bnetsh\s+advfirewall\s+set\b", "firewall reconfiguration"),
    (r"\badd-mppreference\s+-exclusionpath", "Defender exclusion"),
    (r"-encodedcommand\b", "obfuscated PowerShell payload"),
    (r"\bfrombase64string\b.*\biex\b", "obfuscated PowerShell payload"),
    (r"\b(iex|invoke-expression)\b.*\b(downloadstring|invoke-webrequest|curl|wget)\b",
     "remote code execution"),
    (r"\b(downloadstring|downloadfile)\b.*\|\s*(iex|invoke-expression)", "remote code execution"),
    (r"\bstart-process\b.*-verb\s+runas", "privilege elevation"),
    (r"\bsudo\b", "privilege elevation"),
    (r"\bruas\b", "privilege elevation"),
    (r"\bnet\s+user\s+\S+\s+\S+\s+/add", "account creation"),
    (r"\bnet\s+localgroup\s+administrators\b.*\/add", "privilege grant"),
    (r"\breg\s+(add|delete)\b", "registry mutation"),
    (r"\b(new|set|remove)-item(property)?\b.*\bhk(lm|cu|cr|u):", "registry mutation"),
    (r"\bremove-item\b.*\b[a-z]:\\\\?\s*$", "delete at drive root"),
    (r"\brm\s+-rf\s+/(\s|$)", "delete at filesystem root"),
]

_SENSITIVE_SHELL = [
    (r"\b(rmdir|rd)\b.*\s/[sS]", "recursive directory delete"),
    (r"\bdel\b.*\s/[fFqQsS]", "forced delete"),
    (r"\b(remove-item|ri|rm|erase)\b.*-(recurse|r\b)", "recursive delete"),
    (r"\b(remove-item|ri|rm)\b.*-force", "forced delete"),
    (r"\|\s*(remove-item|ri|rm|del)\b", "pipeline delete"),
    (r"\bremove-item\b", "delete"),
    (r"\bshutdown\b", "host shutdown"),
    (r"\b(stop|restart)-computer\b", "host power state change"),
    (r"\b(stop|restart|set)-service\b", "service state change"),
    (r"\btaskkill\b", "process termination"),
    (r"\bstop-process\b", "process termination"),
    (r"\bgit\s+reset\s+--hard\b", "discards uncommitted work"),
    (r"\bgit\s+clean\s+-[a-z]*f", "discards untracked files"),
    (r"\bgit\s+push\b.*(--force|-f\b)", "force push"),
    (r"\bgit\s+branch\s+-D\b", "branch deletion"),
    (r"\b(pip|npm|yarn|pnpm|choco|winget)\s+(install|add|uninstall|remove)\b", "package mutation"),
    (r"\bschtasks\b.*\/create", "scheduled task creation"),
    (r"\bnew-scheduledtask\b", "scheduled task creation"),
    (r"\bset-executionpolicy\b", "execution policy change"),
    (r"\b(icacls|takeown|attrib)\b", "permission change"),
    (r"\bnet\s+(use|share)\b", "network share change"),
]

_BLOCKED_PYTHON = [
    (r"\bctypes\b.*\b(windll|cdll)\b.*\b(shell32|advapi32)\b", "privileged Win32 call"),
    (r"\bwinreg\b.*\b(SetValue|DeleteKey|DeleteValue|CreateKey)", "registry mutation"),
    (r"\b__import__\s*\(\s*['\"]winreg", "registry access via dynamic import"),
    (r"\bbase64\b.*\bb64decode\b.*\bexec\s*\(", "obfuscated payload"),
    (r"\bexec\s*\(\s*(requests|urllib)", "remote code execution"),
]

_SENSITIVE_PYTHON = [
    (r"\bshutil\.rmtree\b", "recursive directory delete"),
    (r"\bos\.(remove|unlink|rmdir|removedirs)\b", "file or directory delete"),
    (r"\bPath\([^)]*\)\.unlink\b", "file delete"),
    (r"\.unlink\s*\(", "file delete"),
    (r"\bos\.system\b", "shell escape"),
    (r"\bsubprocess\.(run|call|Popen|check_output|check_call)\b", "shell escape"),
    (r"\bos\.(rename|replace|truncate|chmod|chown)\b", "filesystem mutation"),
    (r"\bopen\s*\([^)]*['\"][wax]", "file write"),
    (r"\bsocket\.(socket|bind|listen)\b", "raw network socket"),
    (r"\bwinreg\b", "registry access"),
]


def _classify(payload: str, blocked: Sequence, sensitive: Sequence) -> Verdict:
    lowered = (payload or "").lower()
    for pattern, reason in blocked:
        if re.search(pattern, lowered):
            return Verdict(BLOCKED, reason)
    for pattern, reason in sensitive:
        if re.search(pattern, lowered):
            return Verdict(SENSITIVE, reason)
    return Verdict(SAFE)


def classify_shell(command: str) -> Verdict:
    """Risk-classifies a shell command string."""
    return _classify(command, _BLOCKED_SHELL, _SENSITIVE_SHELL)


def classify_python(code: str) -> Verdict:
    """Risk-classifies a Python payload. Previously unchecked entirely."""
    return _classify(code, _BLOCKED_PYTHON, _SENSITIVE_PYTHON)


# Retained for backward compatibility with callers that only wanted a boolean.
def is_dangerous_command(cmd: str) -> bool:
    """True when the command is blocked or requires confirmation."""
    return not classify_shell(cmd).allowed_outright


# ─── Operator confirmation ──────────────────────────────────────────────────

def stdin_is_console() -> bool:
    """
    True only when stdin is a real interactive console.

    sys.stdin.isatty() is not sufficient on Windows: the NUL device is a
    character device, so isatty() reports True for `python x.py < NUL` and a
    confirmation prompt would sit there until it timed out. GetConsoleMode
    succeeds only for an actual console handle, which is the distinction we want.
    """
    try:
        if sys.stdin is None or sys.stdin.closed:
            return False
        fileno = sys.stdin.fileno()
    except (OSError, ValueError, AttributeError):
        return False

    if sys.platform != "win32":
        try:
            return bool(sys.stdin.isatty())
        except (OSError, ValueError):
            return False

    try:
        import msvcrt

        handle = msvcrt.get_osfhandle(fileno)
        mode = ctypes.c_ulong()
        return bool(ctypes.windll.kernel32.GetConsoleMode(ctypes.c_void_p(handle), ctypes.byref(mode)))
    except Exception:
        try:
            return bool(sys.stdin.isatty())
        except (OSError, ValueError):
            return False


def _read_line_with_timeout(timeout: float) -> Optional[str]:
    """
    Reads a line from the console, returning None on timeout.

    Uses msvcrt on Windows because input() cannot be interrupted there. Falls
    back to a blocking read elsewhere, which is acceptable since the supported
    platform is Windows.
    """
    if sys.platform != "win32":
        try:
            return input()
        except (EOFError, KeyboardInterrupt):
            return None

    try:
        import msvcrt
    except ImportError:
        try:
            return input()
        except (EOFError, KeyboardInterrupt):
            return None

    buf: List[str] = []
    deadline = time.time() + timeout
    while time.time() < deadline:
        if msvcrt.kbhit():
            ch = msvcrt.getwche()
            if ch in ("\r", "\n"):
                sys.stdout.write("\n")
                sys.stdout.flush()
                return "".join(buf)
            if ch == "\b":
                if buf:
                    buf.pop()
            elif ch == "\x03":
                raise KeyboardInterrupt
            else:
                buf.append(ch)
        time.sleep(0.04)
    return None


def confirm(action: str, reason: str, timeout: float = 30.0) -> bool:
    """
    Asks the operator to approve a SENSITIVE action. Denies on timeout, on a
    non-interactive stdin, and on anything that is not an explicit yes.
    """
    try:
        from tars.config import config

        if not getattr(config, "confirm_sensitive", True):
            audit_action("gate", "auto_approved", {"action": action, "reason": reason}, "approved")
            return True
    except Exception:
        pass

    if not stdin_is_console():
        # Nobody can answer, so the answer is no. Failing closed matters more
        # here than convenience: an unattended run must not be able to approve
        # its own destructive operation.
        audit_action("gate", "denied_non_interactive", {"action": action, "reason": reason}, "denied")
        return False

    try:
        from rich.console import Console

        from tars.ui import theme as T

        console = Console()
        console.print()
        console.print(T.warn(f"confirmation required: {reason}"))
        console.print(f"  [{T.TEXT_BRIGHT}]{action[:400]}[/{T.TEXT_BRIGHT}]")
        console.print(T.hint(f"type 'yes' within {int(timeout)}s to allow, anything else to refuse"))
        sys.stdout.write("  › ")
        sys.stdout.flush()
    except Exception:
        sys.stdout.write(f"\nConfirm [{reason}]: {action[:200]}\nType 'yes' to allow: ")
        sys.stdout.flush()

    try:
        answer = _read_line_with_timeout(timeout)
    except KeyboardInterrupt:
        answer = None

    approved = (answer or "").strip().lower() in ("y", "yes", "allow", "confirm")
    audit_action(
        "gate",
        "approved" if approved else "denied",
        {"action": action[:500], "reason": reason, "answer": answer},
        "approved" if approved else "denied",
    )
    return approved


# ─── Audit trail ────────────────────────────────────────────────────────────

def audit_action(category: str, action: str, detail: Optional[dict] = None, result: str = "ok") -> None:
    """
    Appends a single JSON line to mission_logs/audit.jsonl.

    Never raises: an audit failure must not take down the tool that was being
    audited. Values are truncated so a large payload cannot bloat the log.
    """
    try:
        AUDIT_DIR.mkdir(parents=True, exist_ok=True)
        safe_detail = {}
        for key, val in (detail or {}).items():
            text = val if isinstance(val, (int, float, bool, type(None))) else str(val)
            if isinstance(text, str) and len(text) > 600:
                text = text[:600] + "…"
            safe_detail[key] = text
        record = {
            "ts": datetime.now().isoformat(timespec="seconds"),
            "category": category,
            "action": action,
            "result": result,
            "detail": safe_detail,
        }
        with open(AUDIT_FILE, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:
        pass


def read_audit_tail(limit: int = 20) -> List[dict]:
    """Returns the most recent audit records, newest last."""
    if not AUDIT_FILE.exists():
        return []
    try:
        lines = AUDIT_FILE.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    out: List[dict] = []
    for line in lines[-limit:]:
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def describe_boundary() -> List[Tuple[str, str]]:
    """Label/value pairs describing the active boundary, for the CLI readout."""
    from tars.config import config

    roots = allowed_roots()
    return [
        ("workspace root", str(PROJECT_ROOT)),
        ("allowed roots", str(len(roots))),
        ("extra roots", ", ".join(getattr(config, "allowed_fs_roots", []) or []) or "none"),
        ("secret classes", f"{len(_SENSITIVE_FILENAMES)} names, {len(_SENSITIVE_GLOBS)} patterns"),
        ("blocked shell rules", str(len(_BLOCKED_SHELL))),
        ("gated shell rules", str(len(_SENSITIVE_SHELL))),
        ("confirmation gate", "on" if getattr(config, "confirm_sensitive", True) else "off"),
        ("audit log", str(AUDIT_FILE)),
    ]
