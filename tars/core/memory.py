"""
TARS Tactical Automated Robot System - Persistent Memory & Profile Matrix

Retains operator facts, the people in the operator's life, past missions,
preferences, and long-term context across restarts.

Two things make this more than a list of strings:

  SALIENCE   Every fact carries a weight. A note about a shell alias and a note
             about who the operator loves are not interchangeable, and the
             second must never be evicted by the first. Retrieval and pruning
             both respect the weight.

  PEOPLE     A registry of the humans who matter, each with a relation and a
             status (living / deceased / estranged / unwell). This is what lets
             the unit understand that a name is not a neutral token: mentioning
             a partner is warm, mentioning someone who has died is not.

The schema is additive. Older memory files without salience or people load
cleanly and are classified on first read.
"""
import json
import re
import time
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime

from tars.config import config

import os

# Overridable so a test or a throwaway session can be pointed at a scratch file
# instead of writing into the operator's real memory.
MEMORY_FILE = Path(
    os.environ.get("TARS_MEMORY_FILE")
    or Path(__file__).resolve().parent.parent.parent / ".tars_memory.json"
)

# Facts at or above this weight are never dropped from the prompt or pruned.
PROTECTED_SALIENCE = 6
# Prompt budget: how many facts to surface in a briefing.
BRIEF_FACT_LIMIT = 18
# Disk budget, applied per-tier so weight survives volume.
MAX_FACTS = 400

# ─── Relationship vocabulary ────────────────────────────────────────────────
# Mixed English and common Indian kinship terms, since those are how the
# operator actually refers to family.

RELATION_TERMS: Dict[str, str] = {
    "girlfriend": "girlfriend", "gf": "girlfriend", "boyfriend": "boyfriend",
    "bf": "boyfriend", "partner": "partner", "wife": "wife", "husband": "husband",
    "fiance": "fiance", "fiancee": "fiancee", "fiancé": "fiance",
    "crush": "crush", "ex": "ex-partner",
    "mom": "mother", "mother": "mother", "mum": "mother", "mummy": "mother",
    "amma": "mother", "aai": "mother", "maa": "mother", "ma": "mother",
    "dad": "father", "father": "father", "papa": "father", "baba": "father",
    "appa": "father", "pop": "father",
    "brother": "brother", "bhai": "brother", "bro": "brother",
    "sister": "sister", "didi": "sister", "behen": "sister", "sis": "sister",
    "grandma": "grandmother", "grandmother": "grandmother", "granny": "grandmother",
    "nani": "grandmother", "dadi": "grandmother", "aaji": "grandmother",
    "ammamma": "grandmother", "paati": "grandmother",
    "grandpa": "grandfather", "grandfather": "grandfather", "nana": "grandfather",
    "dada": "grandfather", "ajoba": "grandfather", "thatha": "grandfather",
    "uncle": "uncle", "mama": "uncle", "chacha": "uncle", "kaka": "uncle",
    "aunt": "aunt", "aunty": "aunt", "mami": "aunt", "chachi": "aunt",
    "kaki": "aunt", "mausi": "aunt", "bua": "aunt",
    "son": "son", "daughter": "daughter", "cousin": "cousin",
    "friend": "friend", "bestfriend": "best friend", "roommate": "roommate",
    "boss": "boss", "manager": "manager", "colleague": "colleague",
    "mentor": "mentor", "teacher": "teacher", "professor": "professor",
    "dog": "dog", "cat": "cat", "pet": "pet",
}

# Relations whose mere mention is emotionally loaded.
_BELOVED = {
    "girlfriend", "boyfriend", "partner", "wife", "husband", "fiance",
    "fiancee", "crush",
}

_DEATH_MARKERS = (
    "passed away", "passed on", "no longer with us", "she died", "he died",
    "died", "death", "funeral", "cremation", "burial", "rest in peace",
    "we lost her", "we lost him", "i lost her", "i lost him", "is gone",
    "she's gone", "hes gone", "he's gone", "late ", "deceased", "expired",
)

_ESTRANGED_MARKERS = ("estranged", "not talking", "cut off", "broke up", "no contact")
_UNWELL_MARKERS = ("in hospital", "hospitalised", "hospitalized", "diagnosed",
                   "cancer", "surgery", "icu", "terminally", "chemo")

# ─── Fact classification ────────────────────────────────────────────────────
# category -> (salience, markers). First match wins, highest listed first.

_CLASSIFIERS = (
    ("bereavement", 10, _DEATH_MARKERS + ("grief", "mourning", "anniversary of her death")),
    ("relationship", 9, (
        "girlfriend", "boyfriend", "my partner", "my wife", "my husband",
        "fiance", "i love", "love her", "love him", "my crush", "first love",
        "anniversary", "she likes", "she loves", "her birthday", "his birthday",
        "proposed", "dating",
    )),
    ("family", 8, (
        "my mom", "my mother", "my dad", "my father", "my brother", "my sister",
        "my grandma", "my grandmother", "my grandpa", "my grandfather",
        "my son", "my daughter", "my family", "nani", "dadi", "aaji", "ajoba",
    )),
    ("health", 8, (
        "allergic", "allergy", "asthma", "diabetic", "medication", "surgery",
        "hospital", "diagnosed", "blood group", "can't handle", "cant handle",
        "intolerant",
    )),
    ("milestone", 7, (
        "birthday", "anniversary", "graduated", "got the job", "got selected",
        "wedding", "exam on", "deadline is",
    )),
    ("identity", 7, (
        "my name is", "i am called", "call me", "i study", "i work at",
        "my college", "my school", "my goal", "my dream", "my mission",
        "i want to become",
    )),
    ("preference", 5, (
        "i like", "i prefer", "i love listening", "favourite", "favorite",
        "i hate", "i don't like", "i dont like", "always use", "never use",
    )),
    ("project", 4, (
        "repo", "project", "codebase", "api key", "workspace", "branch",
        "deploy", "stack", "framework",
    )),
)

# Proper nouns only, and deliberately NOT compiled with re.IGNORECASE: under
# that flag [A-Z] also matches lowercase, which happily parsed "my girlfriend
# name is Varsha" into a person called "name is". Case is the only reliable
# signal that a token is a name, so the relation half carries a scoped (?i:)
# instead of flagging the whole pattern.
_NAME_RE = r"([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)?)"

# Words that look like names to the pattern but never are.
_NAME_STOPWORDS = {
    "name", "names", "is", "was", "the", "a", "an", "my", "her", "his", "their",
    "she", "he", "they", "it", "that", "this", "and", "but", "so", "called",
    "birthday", "favourite", "favorite", "fantasy", "allergic", "allergy",
    "trait", "smile", "eyes", "hair", "voice", "best", "first", "love",
    "really", "very", "just", "also", "too", "now", "today", "yesterday",
    "tomorrow", "always", "never", "still", "only", "even", "like", "likes",
}


def _status_note(status: str, fact: str) -> str:
    """
    Keeps the clause that established a non-living status, so the unit has the
    circumstance and not just the flag. 'passed away last night' is a different
    conversation from 'passed away in 2019'.
    """
    if status == "living":
        return ""
    markers = {"deceased": _DEATH_MARKERS,
               "estranged": _ESTRANGED_MARKERS,
               "unwell": _UNWELL_MARKERS}.get(status, ())
    low = fact.lower()
    for marker in markers:
        at = low.find(marker)
        if at < 0:
            continue
        clause = fact[at:at + 90].strip()
        clause = re.split(r"[.!?\n]", clause)[0].strip()
        return clause[:90]
    return ""


def _looks_like_name(candidate: str) -> bool:
    """Rejects sentence fragments that the proper-noun pattern can pick up."""
    parts = [p for p in candidate.strip().split() if p]
    if not parts or len(parts) > 2:
        return False
    for part in parts:
        low = part.lower()
        if low in _NAME_STOPWORDS or low in RELATION_TERMS:
            return False
        if len(part) < 2 or not part[0].isupper() or not part.isalpha():
            return False
    return True


def _classify(fact: str) -> tuple:
    """Returns (category, salience) for a free-text fact."""
    low = fact.lower()
    for category, salience, markers in _CLASSIFIERS:
        if any(m in low for m in markers):
            # A long, first-person, affect-laden statement is a declaration, not
            # a note. Weight it up so it survives everything.
            if category in ("relationship", "bereavement") and len(fact) > 180:
                salience = 10
            return category, salience
    return "general", 3


class TarsMemory:
    def __init__(self):
        self.profile: Dict[str, Any] = {
            "operator_callsign": config.operator_callsign,
            "os": "Windows (PowerShell)",
            "primary_workspace": str(Path(__file__).resolve().parent.parent.parent),
            "custom_instructions": []
        }
        self.facts: List[Dict[str, Any]] = []
        self.mission_history: List[Dict[str, Any]] = []
        # name -> person record
        self.people: Dict[str, Dict[str, Any]] = {}
        self.load()

    # ── persistence ────────────────────────────────────────────────────────

    def load(self):
        if MEMORY_FILE.exists():
            try:
                with open(MEMORY_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.profile.update(data.get("profile", {}))
                    self.facts = data.get("facts", [])
                    self.mission_history = data.get("mission_history", [])
                    people = data.get("people", {})
                    if isinstance(people, dict):
                        self.people = people
            except Exception:
                pass
        self._migrate()

    def _migrate(self):
        """
        Backfills category and salience on facts written before weighting
        existed, and derives the people registry from what is already stored.
        Runs on every load; it is idempotent and cheap.
        """
        dirty = False
        for item in self.facts:
            fact = item.get("fact", "")
            if not fact:
                continue
            if "salience" not in item or item.get("category") in (None, "", "general"):
                category, salience = _classify(fact)
                # Never downgrade a category someone set deliberately.
                if item.get("category") in (None, "", "general"):
                    item["category"] = category
                item.setdefault("salience", salience)
                if item.get("salience") != salience and item.get("category") == category:
                    item["salience"] = max(int(item.get("salience", 0)), salience)
                dirty = True
            found = self._harvest_people(fact)
            dirty = dirty or found
        if self._sanitise_people():
            dirty = True
        if dirty:
            self.save()

    def save(self):
        try:
            with open(MEMORY_FILE, "w", encoding="utf-8") as f:
                json.dump({
                    "profile": self.profile,
                    "facts": self._prune_facts(),
                    "people": self.people,
                    "mission_history": self.mission_history[-25:],
                    "last_updated": datetime.now().isoformat()
                }, f, indent=2)
        except Exception:
            pass

    def _prune_facts(self) -> List[Dict[str, Any]]:
        """
        Caps stored facts without letting volume evict weight. Everything at or
        above PROTECTED_SALIENCE is kept outright; the remainder is tail-sliced.
        A note about a shell flag must not be able to push out who someone loves.
        """
        if len(self.facts) <= MAX_FACTS:
            return self.facts
        protected = [f for f in self.facts if int(f.get("salience", 0)) >= PROTECTED_SALIENCE]
        ordinary = [f for f in self.facts if int(f.get("salience", 0)) < PROTECTED_SALIENCE]
        room = max(0, MAX_FACTS - len(protected))
        kept = protected + ordinary[-room:]
        # Preserve original chronological order.
        order = {id(f): i for i, f in enumerate(self.facts)}
        return sorted(kept, key=lambda f: order.get(id(f), 0))

    # ── facts ──────────────────────────────────────────────────────────────

    def remember_fact(self, fact: str, category: Optional[str] = None,
                      salience: Optional[int] = None) -> Dict[str, Any]:
        """
        Stores a persistent fact about the operator, their people, environment,
        or projects. Category and salience are inferred when not supplied.
        """
        cleaned = (fact or "").strip()
        if not cleaned:
            return {}

        auto_category, auto_salience = _classify(cleaned)
        category = category or auto_category
        salience = auto_salience if salience is None else max(0, min(10, int(salience)))

        for item in self.facts:
            if item.get("fact", "").lower() == cleaned.lower():
                # Re-telling something raises its weight rather than duplicating.
                item["salience"] = max(int(item.get("salience", 0)), salience)
                self.save()
                return item

        record = {
            "fact": cleaned,
            "category": category,
            "salience": salience,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        self.facts.append(record)
        self._harvest_people(cleaned)
        self.save()
        return record

    # ── people ─────────────────────────────────────────────────────────────

    def remember_person(self, name: str = "", relation: str = "",
                        status: str = "living", note: str = "") -> Dict[str, Any]:
        """
        Registers or updates someone who matters to the operator.

        `status` is one of living / deceased / estranged / unwell. It is the
        field that changes how the unit speaks about them, so it is the one
        worth getting right.
        """
        relation = RELATION_TERMS.get(relation.lower().strip(), relation.lower().strip())
        name = (name or "").strip()
        key = (name or relation).lower()
        if not key:
            return {}

        record = self.people.get(key, {
            "name": name or relation.title(),
            "relation": relation,
            "status": "living",
            "note": "",
            "aliases": [],
            "first_seen": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        })
        if name:
            record["name"] = name
        if relation:
            record["relation"] = relation
        if status:
            record["status"] = status.lower().strip()
        if note:
            existing = record.get("note") or ""
            if note.lower() not in existing.lower():
                record["note"] = (existing + " " + note).strip()[:400]

        aliases = set(a.lower() for a in record.get("aliases", []))
        if relation:
            aliases.add(relation)
            for term, canon in RELATION_TERMS.items():
                if canon == relation:
                    aliases.add(term)
        for part in name.split():
            if len(part) >= 3:
                aliases.add(part.lower())
        record["aliases"] = sorted(aliases)
        record["updated"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        self.people[key] = record
        self.save()
        return record

    def _harvest_people(self, fact: str) -> bool:
        """
        Pulls relationships out of a free-text fact so the operator never has to
        fill in a form. Returns True if the registry changed.

        Handles the shapes people actually type:
          "my girlfriend name is Varsha Priya"
          "my girlfriend's name is Varsha"
          "my grandma Sudha passed away"
          "my grandmother passed away last year"
        """
        changed = False
        low = fact.lower()
        terms = "|".join(sorted(RELATION_TERMS, key=len, reverse=True))
        rel = rf"((?i:{terms}))"
        my = r"(?i:my)"

        status = "living"
        if any(m in low for m in _DEATH_MARKERS):
            status = "deceased"
        elif any(m in low for m in _ESTRANGED_MARKERS):
            status = "estranged"
        elif any(m in low for m in _UNWELL_MARKERS):
            status = "unwell"

        patterns = (
            rf"\b{my}\s+{rel}(?:'s|s)?\s+(?i:name)\s+(?i:is)\s+{_NAME_RE}",
            rf"\b{my}\s+{rel}\s+(?i:is)\s+(?:(?i:called)\s+)?{_NAME_RE}",
            rf"\b{my}\s+{rel},?\s+{_NAME_RE}\b",
            rf"{_NAME_RE}\s+(?i:is\s+my)\s+{rel}\b",
        )

        for idx, pattern in enumerate(patterns):
            for match in re.finditer(pattern, fact):
                if idx == 3:
                    name, relation = match.group(1), match.group(2)
                else:
                    relation, name = match.group(1), match.group(2)
                if not _looks_like_name(name):
                    continue
                relation = RELATION_TERMS.get(relation.lower(), relation.lower())
                key = (name or relation).lower()
                before = json.dumps(self.people.get(key), sort_keys=True)
                self.remember_person(name=name.strip(), relation=relation, status=status)
                if json.dumps(self.people.get(key), sort_keys=True) != before:
                    changed = True

        # A bare relation with no name still deserves a record, because status
        # is the part that actually matters: "my grandmother passed away" has to
        # be retained even though no name was ever given.
        for match in re.finditer(rf"\b{my}\s+{rel}\b", fact):
            relation = RELATION_TERMS.get(match.group(1).lower(), match.group(1).lower())
            existing = self._find_by_relation(relation)
            if existing:
                if status != "living" and existing.get("status") != status:
                    self.remember_person(name=existing.get("name", ""),
                                         relation=relation, status=status,
                                         note=_status_note(status, fact))
                    changed = True
            elif status != "living" or relation in _BELOVED:
                self.remember_person(relation=relation, status=status,
                                     note=_status_note(status, fact))
                changed = True
        return changed

    def observe(self, text: str) -> bool:
        """
        Harvests relationships out of ordinary conversation, without storing the
        turn itself as a fact.

        This is what closes the loop the operator actually cares about: saying
        "my grandma passed away" once, in passing, is enough for the unit to
        know forever after that she is gone. Requiring an explicit
        "remember that ..." for something like that would be its own kind of
        coldness.
        """
        if not (text or "").strip():
            return False
        try:
            return self._harvest_people(text)
        except Exception:
            return False

    def _sanitise_people(self) -> bool:
        """Drops records created by earlier, looser name parsing."""
        bad = [
            key for key, record in self.people.items()
            if not key.strip()
            or any(w in _NAME_STOPWORDS for w in key.split())
            or (record.get("name", "").lower().split() and
                any(w in _NAME_STOPWORDS for w in record.get("name", "").lower().split()))
        ]
        for key in bad:
            del self.people[key]
        return bool(bad)

    def _find_by_relation(self, relation: str) -> Optional[Dict[str, Any]]:
        for record in self.people.values():
            if record.get("relation") == relation:
                return record
        return None

    def resolve_people(self, text: str) -> List[Dict[str, Any]]:
        """
        Returns the registered people this text appears to be about, matched on
        name, name parts, relation, and relation synonyms.
        """
        if not text or not self.people:
            return []
        low = text.lower()
        hits: List[Dict[str, Any]] = []
        for record in self.people.values():
            needles = set(record.get("aliases", []))
            name = (record.get("name") or "").lower()
            if name:
                needles.add(name)
                needles.update(p for p in name.split() if len(p) >= 3)
            relation = record.get("relation") or ""
            if relation:
                needles.add(relation)
            for needle in needles:
                if not needle or len(needle) < 3:
                    continue
                if re.search(rf"\b{re.escape(needle)}\b", low):
                    hits.append(record)
                    break
        return hits

    def forget_person(self, key: str) -> bool:
        key = key.lower().strip()
        for candidate in list(self.people):
            record = self.people[candidate]
            if candidate == key or (record.get("name", "").lower() == key):
                del self.people[candidate]
                self.save()
                return True
        return False

    # ── missions ───────────────────────────────────────────────────────────

    def record_mission(self, objective: str, summary: str, success: bool = True):
        """Archives a completed autonomous goal or research mission."""
        self.mission_history.append({
            "objective": objective,
            "summary": summary,
            "success": success,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        })
        self.save()

    # ── retrieval ──────────────────────────────────────────────────────────

    def relevant_facts(self, focus: str = "", limit: int = BRIEF_FACT_LIMIT) -> List[Dict[str, Any]]:
        """
        Picks the facts worth putting in front of the model this turn.

        Scored on three things: how much the fact weighs, whether it overlaps
        with what the operator just said, and how recently it was recorded. The
        old behaviour -- a blind tail slice -- meant two trivial notes could
        silently evict who the operator loves.
        """
        if not self.facts:
            return []

        focus_words = {w for w in re.findall(r"[a-z']{3,}", (focus or "").lower())}
        people_names = set()
        for record in self.resolve_people(focus):
            people_names.update(a for a in record.get("aliases", []) if len(a) >= 3)
            people_names.add((record.get("name") or "").lower())

        total = len(self.facts)
        scored = []
        for index, item in enumerate(self.facts):
            fact = item.get("fact", "")
            low = fact.lower()
            salience = int(item.get("salience", 3))
            score = float(salience)

            if focus_words:
                fact_words = {w for w in re.findall(r"[a-z']{3,}", low)}
                overlap = len(focus_words & fact_words)
                if overlap:
                    score += min(6.0, overlap * 1.2)
            if any(n and n in low for n in people_names):
                score += 5.0
            # Recency, worth at most ~2 points.
            score += 2.0 * (index / max(1, total - 1))

            scored.append((score, index, item))

        scored.sort(key=lambda t: (-t[0], -t[1]))
        chosen = [item for _s, _i, item in scored[:limit]]
        # Present in chronological order so narrative facts still read in sequence.
        order = {id(f): i for i, f in enumerate(self.facts)}
        return sorted(chosen, key=lambda f: order.get(id(f), 0))

    def people_brief(self) -> str:
        """The relational roster, formatted for the system prompt."""
        if not self.people:
            return ""
        lines = []
        for record in sorted(self.people.values(),
                             key=lambda r: 0 if r.get("relation") in _BELOVED else 1):
            name = record.get("name") or "(unnamed)"
            relation = record.get("relation") or "someone"
            status = (record.get("status") or "living").lower()
            bit = f" - {name}: {relation}"
            if status == "deceased":
                bit += " | HAS DIED. The operator is bereaved. Past tense, and with care."
            elif status == "estranged":
                bit += " | currently estranged."
            elif status == "unwell":
                bit += " | currently unwell."
            note = record.get("note")
            if note:
                bit += f" | {note[:160]}"
            lines.append(bit)
        return "\n".join(lines)

    def get_memory_context_prompt(self, focus: str = "") -> str:
        """
        Generates the memory briefing injected into LLM system instructions.
        `focus` is the operator's current turn, used to pull relevant history
        forward rather than always showing the most recent entries.
        """
        lines = [f"Operator: {config.operator_callsign} (OS: {self.profile.get('os', 'Windows')})"]

        roster = self.people_brief()
        if roster:
            lines.append("")
            lines.append("PEOPLE WHO MATTER TO THE OPERATOR")
            lines.append(roster)
            lines.append(
                "Use their names. These are not database rows; they are the people "
                "the operator has chosen to tell you about."
            )

        selected = self.relevant_facts(focus)
        if selected:
            lines.append("")
            lines.append("WHAT YOU KNOW ABOUT THE OPERATOR")
            for item in selected:
                marker = " *" if int(item.get("salience", 0)) >= PROTECTED_SALIENCE else ""
                lines.append(f" - {item['fact']}{marker}")
            lines.append("Entries marked * are the ones that carry weight. Recall them specifically.")

        custom = self.profile.get("custom_instructions") or []
        if custom:
            lines.append("")
            lines.append("STANDING INSTRUCTIONS FROM THE OPERATOR")
            for entry in custom[-6:]:
                lines.append(f" - {entry}")

        if self.mission_history:
            lines.append("")
            lines.append("Recent missions:")
            for m in self.mission_history[-3:]:
                status = "SUCCESS" if m.get("success") else "FAILED"
                lines.append(f" - [{status}] {m.get('objective')}: {str(m.get('summary'))[:100]}")

        return "\n".join(lines)

    def add_instruction(self, text: str) -> bool:
        """Stores a standing preference about how the operator wants to be treated."""
        cleaned = (text or "").strip()
        if not cleaned:
            return False
        bucket = self.profile.setdefault("custom_instructions", [])
        if cleaned.lower() in [b.lower() for b in bucket]:
            return False
        bucket.append(cleaned)
        self.save()
        return True

    # ── operator-facing views ──────────────────────────────────────────────

    def get_memory_summary(self) -> str:
        """Returns user-facing formatted view of persistent memory."""
        res = [
            f"[bold cyan]OPERATOR PROFILE // {config.operator_callsign.upper()}[/bold cyan]",
            f"Environment: {self.profile.get('os', 'Windows')}",
            f"Primary Workspace: {self.profile.get('primary_workspace', 'N/A')}\n",
        ]

        res.append(f"[bold cyan]PEOPLE ({len(self.people)} registered):[/bold cyan]")
        if not self.people:
            res.append(" (Nobody registered yet. Mention someone and TARS will keep track.)")
        else:
            for record in self.people.values():
                status = (record.get("status") or "living").lower()
                tone = {"deceased": "magenta", "estranged": "yellow", "unwell": "yellow"}.get(status, "green")
                res.append(
                    f"  [white]{record.get('name')}[/white] "
                    f"[dim]({record.get('relation')})[/dim] [{tone}]{status}[/{tone}]"
                )

        res.append(f"\n[bold cyan]RECORDED FACTS & PREFERENCES ({len(self.facts)} items):[/bold cyan]")
        if not self.facts:
            res.append(" (No custom facts logged yet. Tell TARS 'remember that <fact>' to persist.)")
        else:
            ranked = sorted(self.facts, key=lambda f: -int(f.get("salience", 0)))[:14]
            for idx, f in enumerate(ranked, start=1):
                weight = int(f.get("salience", 3))
                tag = f"[dim]{f.get('category', 'general')} w{weight}[/dim]"
                body = f["fact"] if len(f["fact"]) <= 150 else f["fact"][:147] + "..."
                res.append(f"  {idx:2d}. [white]{body}[/white] {tag}")

        res.append(f"\n[bold cyan]RECENT MISSION LOGS ({len(self.mission_history)} recorded):[/bold cyan]")
        if not self.mission_history:
            res.append(" (No missions executed yet. Run /goal <task> to execute autonomous missions.)")
        else:
            for m in self.mission_history[-5:]:
                st = "[green]OK[/green]" if m.get("success") else "[red]X[/red]"
                res.append(f"  {st} [bold white]{m['objective']}[/bold white] - [dim]{str(m['summary'])[:80]}...[/dim]")

        return "\n".join(res)

    def clear(self):
        """Clears stored facts, people, and history."""
        self.facts = []
        self.mission_history = []
        self.people = {}
        self.save()

memory = TarsMemory()
