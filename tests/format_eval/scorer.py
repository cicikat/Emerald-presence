"""只读的回复分段合规 scorer（Brief 73）。

strict 衡量最终展示文本是否真的含段落空行；loose 与生产侧 S4
``note_segment_collapse_signal`` 的判定边界保持一致：只有超过阈值且完全没有
真实换行的文本才算不合规。scorer 只读取字符串，不改写输入。
"""

from __future__ import annotations

from dataclasses import dataclass
from statistics import fmean
from typing import Iterable, Literal

from core.memory.short_term import DEFAULT_SEGMENT_MIN_LEN

ComplianceMode = Literal["strict", "loose"]


@dataclass(frozen=True)
class ReplyScore:
    strict_compliant: bool
    loose_compliant: bool
    paragraph_count: int
    unsegmented: bool
    text_length: int

    def compliant(self, mode: ComplianceMode) -> bool:
        if mode == "strict":
            return self.strict_compliant
        if mode == "loose":
            return self.loose_compliant
        raise ValueError(f"unknown compliance mode: {mode!r}")


@dataclass(frozen=True)
class FormatMetrics:
    total: int
    compliant_count: int
    compliance_rate: float
    average_paragraph_count: float
    unsegmented_count: int
    unsegmented_ratio: float


def _normalized_body(reply: str) -> str:
    if not isinstance(reply, str):
        raise TypeError("reply must be str")
    # 只在 scorer 的局部副本统一换行编码；不写回、不修改语料。
    return reply.replace("\r\n", "\n").replace("\r", "\n").strip()


def _paragraph_count(body: str) -> int:
    if not body:
        return 0
    return len([part for part in body.split("\n\n") if part.strip()])


def score_reply(
    reply: str,
    *,
    min_len: int = DEFAULT_SEGMENT_MIN_LEN,
) -> ReplyScore:
    """对一条回复同时计算 strict / loose 两档结果。

    loose 刻意复刻当前生产 S4 的 ``len > min_len and "\\n" not in text``
    判据（取反即合规），所以长度恰好等于阈值时也豁免；单个真实换行也足以
    打断 S4 streak。strict 仍只认段落空行 ``\\n\\n``。
    """
    threshold = max(1, int(min_len))
    body = _normalized_body(reply)
    has_paragraph_break = "\n\n" in body
    s4_collapse = bool(body) and len(body) > threshold and "\n" not in body
    return ReplyScore(
        strict_compliant=has_paragraph_break,
        loose_compliant=not s4_collapse,
        paragraph_count=_paragraph_count(body),
        unsegmented=not has_paragraph_break,
        text_length=len(body),
    )


def aggregate_scores(
    scores: Iterable[ReplyScore],
    *,
    mode: ComplianceMode,
) -> FormatMetrics:
    items = list(scores)
    total = len(items)
    compliant_count = sum(item.compliant(mode) for item in items)
    unsegmented_count = sum(item.unsegmented for item in items)
    return FormatMetrics(
        total=total,
        compliant_count=compliant_count,
        compliance_rate=(compliant_count / total if total else 0.0),
        average_paragraph_count=(fmean(item.paragraph_count for item in items) if items else 0.0),
        unsegmented_count=unsegmented_count,
        unsegmented_ratio=(unsegmented_count / total if total else 0.0),
    )


def score_corpus(
    replies: Iterable[str],
    *,
    mode: ComplianceMode,
    min_len: int = DEFAULT_SEGMENT_MIN_LEN,
) -> FormatMetrics:
    return aggregate_scores(
        (score_reply(reply, min_len=min_len) for reply in replies),
        mode=mode,
    )
