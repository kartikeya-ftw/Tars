"""
TARS Tactical Automated Robot System - Persistent Memory & Profile Matrix
Retains operator facts, past missions, preferences, and long-term context across restarts.
"""
import json
import time
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime

from tars.config import config

MEMORY_FILE = Path(__file__).resolve().parent.parent.parent / ".tars_memory.json"

class TarsMemory:
    def __init__(self):
        self.profile: Dict[str, Any] = {
            "operator_callsign": config.operator_callsign,
            "os": "Windows (PowerShell)",
            "primary_workspace": str(Path(__file__).resolve().parent.parent.parent),
            "custom_instructions": []
        }
        self.facts: List[Dict[str, str]] = []
        self.mission_history: List[Dict[str, Any]] = []
        self.load()

    def load(self):
        if MEMORY_FILE.exists():
            try:
                with open(MEMORY_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.profile.update(data.get("profile", {}))
                    self.facts = data.get("facts", [])
                    self.mission_history = data.get("mission_history", [])
            except Exception:
                pass

    def save(self):
        try:
            with open(MEMORY_FILE, "w", encoding="utf-8") as f:
                json.dump({
                    "profile": self.profile,
                    "facts": self.facts[-50:], # Retain up to 50 curated facts
                    "mission_history": self.mission_history[-25:], # Retain recent 25 missions
                    "last_updated": datetime.now().isoformat()
                }, f, indent=2)
        except Exception:
            pass

    def remember_fact(self, fact: str, category: str = "general"):
        """Stores a persistent memory fact about the operator, environment, or projects."""
        cleaned = fact.strip()
        if not cleaned:
            return
        # Prevent exact duplicates
        for item in self.facts:
            if item.get("fact", "").lower() == cleaned.lower():
                return
        self.facts.append({
            "fact": cleaned,
            "category": category,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        })
        self.save()

    def record_mission(self, objective: str, summary: str, success: bool = True):
        """Archives a completed autonomous goal or research mission."""
        self.mission_history.append({
            "objective": objective,
            "summary": summary,
            "success": success,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        })
        self.save()

    def get_memory_context_prompt(self) -> str:
        """Generates a concise memory briefing to inject into LLM system instructions."""
        lines = []
        lines.append(f"Operator: {config.operator_callsign} (OS: {self.profile.get('os', 'Windows')})")
        if self.facts:
            lines.append("Key Persistent Memories & Operator Context:")
            for item in self.facts[-10:]:
                lines.append(f" - {item['fact']}")
        if self.mission_history:
            recent = self.mission_history[-3:]
            lines.append("Recent Missions Completed:")
            for m in recent:
                status = "SUCCESS" if m.get("success") else "FAILED"
                lines.append(f" - [{status}] {m.get('objective')}: {m.get('summary')[:100]}")
        return "\n".join(lines)

    def get_memory_summary(self) -> str:
        """Returns user-facing formatted view of persistent memory."""
        res = [
            f"[bold cyan]OPERATOR PROFILE // {config.operator_callsign.upper()}[/bold cyan]",
            f"Environment: {self.profile.get('os', 'Windows')}",
            f"Primary Workspace: {self.profile.get('primary_workspace', 'N/A')}\n",
            f"[bold cyan]RECORDED FACTS & PREFERENCES ({len(self.facts)} items):[/bold cyan]"
        ]
        if not self.facts:
            res.append(" (No custom facts logged yet. Tell TARS 'remember that <fact>' to persist.)")
        else:
            for idx, f in enumerate(self.facts[-12:], start=1):
                res.append(f"  {idx:2d}. [white]{f['fact']}[/white] [dim]({f.get('timestamp', '')})[/dim]")

        res.append(f"\n[bold cyan]RECENT MISSION LOGS ({len(self.mission_history)} recorded):[/bold cyan]")
        if not self.mission_history:
            res.append(" (No missions executed yet. Run /goal <task> to execute autonomous missions.)")
        else:
            for m in self.mission_history[-5:]:
                st = "[green]✔[/green]" if m.get("success") else "[red]✘[/red]"
                res.append(f"  {st} [bold white]{m['objective']}[/bold white] - [dim]{m['summary'][:80]}...[/dim]")

        return "\n".join(res)

    def clear(self):
        """Clears stored facts and history."""
        self.facts = []
        self.mission_history = []
        self.save()

memory = TarsMemory()
