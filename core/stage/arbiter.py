"""Pure-rule want-to-speak scoring for Stage turns."""
from __future__ import annotations

import re
from dataclasses import dataclass

from core.character_name_provider import get_char_name
from core.stage.models import Stage, TranscriptEntry

# Bonus applied when a peer (another AI character, not the owner) just spoke.
# Scaled by talkativeness so chatty chars are more eager to reply.
PEER_REPLY_BASE = 0.40
VOCATIVE_SCORE = 0.9
MENTION_SCORE = 0.3
VOCATIVE_QUESTION_BONUS = 0.3
OPEN_QUESTION_BONUS = 0.1


@dataclass(frozen=True)
class CandidateScore:
    char_id: str
    total: float
    parts: dict[str, float]


def addressed_kind(stage: Stage, char_id: str, text: str) -> str:
    """Classify direct address without mistaking third-person mentions for a call."""
    name = get_char_name(char_id)
    aliases = (char_id, name)
    for alias in aliases:
        if re.search(rf"@{re.escape(alias)}(?![\w-])", text):
            return "vocative"
        if re.search(rf"(?:^|[。！？!?]\s*){re.escape(alias)}(?:[，、\s]|你)", text):
            return "vocative"
    return "mention" if any(alias in text for alias in aliases) else "none"


def _is_question(text: str) -> bool:
    return bool(re.search(r"[？?]\s*$|[吗呢么]\s*$|谁|什么|怎么|为什么|多少", text or ""))


def _recency_penalty(char_id: str, transcript: list[TranscriptEntry]) -> float:
    recent = transcript[-6:]
    occurrences = sum(1 for entry in recent if entry.speaker_id == char_id)
    latest_penalty = 0.35 if recent and recent[-1].speaker_id == char_id else 0.0
    return min(0.15 * occurrences + latest_penalty, 0.8)


def _keyword_relevance(stage: Stage, char_id: str, text: str) -> float:
    keywords = stage.settings.keywords.get(char_id, ())
    hits = sum(1 for keyword in keywords if keyword and keyword in text)
    return min(hits * 0.2, 0.6)


def _peer_valence(char_id: str, peer_id: str) -> float:
    """`char_id`'s own fondness of `peer_id`, from the shared relation store.

    Brief 85 §5: characters who like each other are more eager to reply —
    relation participates in arbitration by *modulating* peer_reply eagerness,
    never by gating who is allowed to speak. Fail-open: no relation on file
    (or any lookup error) → 0.0, so the (1 + 0.2 * valence) coefficient
    collapses to 1.0 (no modulation). Never touches owner↔char relations —
    char_relations only ever stores char↔char pairs.
    """
    try:
        from core.stage.char_relations import viewer_summary

        _summary, valence = viewer_summary(char_id, peer_id)
        return valence
    except Exception:
        return 0.0


def score_candidates(
    stage: Stage,
    transcript: list[TranscriptEntry],
    *,
    candidates: list[str] | tuple[str, ...] | None = None,
    derived_keywords: dict[str, tuple[str, ...]] | None = None,
) -> list[CandidateScore]:
    latest_text = transcript[-1].content if transcript else ""
    latest_speaker = transcript[-1].speaker_id if transcript else "owner"
    pool = tuple(candidates) if candidates is not None else stage.roster
    addressed = {char_id: addressed_kind(stage, char_id, latest_text) for char_id in pool}
    vocative = {char_id for char_id, kind in addressed.items() if kind == "vocative"}
    if vocative and stage.settings.addressed_exclusive:
        pool = tuple(char_id for char_id in pool if char_id in vocative)
    question = _is_question(latest_text)

    result: list[CandidateScore] = []
    for char_id in pool:
        talkativeness = min(max(stage.settings.talkativeness.get(char_id, 0.5), 0.0), 1.0)
        # peer_spoke: another AI character (not the human owner, not self) just spoke
        peer_spoke = latest_speaker != "owner" and latest_speaker != char_id
        peer_reply = 0.0
        if peer_spoke:
            # valence ∈ [-1, 1] (char_relations clamps it) → coefficient ∈ [0.8, 1.2].
            valence_coef = 1.0 + 0.2 * _peer_valence(char_id, latest_speaker)
            peer_reply = PEER_REPLY_BASE * talkativeness * valence_coef
        parts = {
            "talkativeness": talkativeness * 0.5,
            "addressed": VOCATIVE_SCORE if addressed[char_id] == "vocative" else MENTION_SCORE if addressed[char_id] == "mention" else 0.0,
            "question": VOCATIVE_QUESTION_BONUS if question and addressed[char_id] == "vocative" else OPEN_QUESTION_BONUS if question and not vocative else 0.0,
            "topic": min(sum(1 for keyword in set(stage.settings.keywords.get(char_id, ())) | set((derived_keywords or {}).get(char_id, ())) if keyword and keyword in latest_text) * 0.2, 0.6),
            "peer_reply": peer_reply,
            "recency_penalty": -_recency_penalty(char_id, transcript),
        }
        total = round(max(0.0, min(sum(parts.values()), 1.5)), 4)
        result.append(CandidateScore(char_id=char_id, total=total, parts=parts))

    result.sort(key=lambda item: (-item.total, stage.roster.index(item.char_id)))
    return result
