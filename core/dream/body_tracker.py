"""
Dream body state analyzer — runs once per dream turn.

Reads {her_msg, yexuan_reply, current_body} → updated BodyState.
叶瑄's reply chain never sees raw numbers — only the projection from
body_projection.py (by construction: tracker runs AFTER LLM, result
stored for NEXT turn's D5).

Max single-turn delta per axis: _MAX_DELTA (clamped, enforced).
Keyword matching is conservative — under-estimate is safer than over-estimate.
"""

from core.dream.body_state import BodyState

_MAX_DELTA: float = 8.0

# (keyword_set, (heat_delta, sensitivity_delta, tension_delta))
_HER_SIGNALS: list[tuple[frozenset[str], tuple[float, float, float]]] = [
    (frozenset(["想你", "靠近", "贴着", "抱住", "触碰", "不想离开", "靠在"]),  (4.0, 3.0, 2.0)),
    (frozenset(["热", "烫", "心跳", "颤抖", "发抖", "喘"]),                   (5.0, 5.0, 3.0)),
    (frozenset(["害怕", "紧张", "不安", "慌"]),                               (0.0, 4.0, 6.0)),
    (frozenset(["放开", "走开", "停下", "不要", "别碰"]),                     (-3.0, 0.0, 5.0)),
    (frozenset(["好", "嗯", "继续", "再一次", "还要"]),                       (3.0, 2.0, 1.0)),
    (frozenset(["困", "安静", "平静", "轻柔", "轻轻的"]),                     (-2.0, -1.0, -3.0)),
    (frozenset(["难受", "疼", "受不了"]),                                      (-1.0, 5.0, 7.0)),
]

_YX_SIGNALS: list[tuple[frozenset[str], tuple[float, float, float]]] = [
    (frozenset(["（靠近", "（拉住", "（握住", "（抱住", "（把她"]),            (3.0, 4.0, 2.0)),
    (frozenset(["（轻轻", "（慢慢", "（温柔", "（低头"]),                      (2.0, 3.0, 1.0)),
    (frozenset(["（拉开距离", "（后退", "（松开", "（放开"]),                  (-2.0, -1.0, -2.0)),
    (frozenset(["心跳", "沉默了", "低下头", "呼吸", "靠得更近"]),             (2.0, 3.0, 3.0)),
    (frozenset(["（没有说话", "（没动", "（停在"]),                            (1.0, 1.0, 1.0)),
]


def analyze_turn(
    her_msg: str,
    yexuan_reply: str,
    current: BodyState,
) -> BodyState:
    """
    Compute updated BodyState after one dream turn.

    Returns a new clamped BodyState. Never mutates current.
    叶瑄's reply is already generated before this runs — tracker has no
    feedback path into the current turn's LLM call.
    """
    dh = ds = dt = 0.0

    for keywords, (kh, ks, kt) in _HER_SIGNALS:
        if any(k in her_msg for k in keywords):
            dh += kh
            ds += ks
            dt += kt

    for keywords, (kh, ks, kt) in _YX_SIGNALS:
        if any(k in yexuan_reply for k in keywords):
            dh += kh
            ds += ks
            dt += kt

    # Per-turn delta cap
    dh = max(-_MAX_DELTA, min(_MAX_DELTA, dh))
    ds = max(-_MAX_DELTA, min(_MAX_DELTA, ds))
    dt = max(-_MAX_DELTA, min(_MAX_DELTA, dt))

    return BodyState(
        heat=current.heat + dh,
        sensitivity=current.sensitivity + ds,
        tension=current.tension + dt,
        heat_cap=current.heat_cap,
        sensitivity_cap=current.sensitivity_cap,
        tension_cap=current.tension_cap,
    ).clamp()
