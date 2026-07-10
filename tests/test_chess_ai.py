"""
tests/test_chess_ai.py

chess_ai teaching style bug fix (Brief 43 §F).

T1. _apply_style(teaching) must call board.is_capture(move) BEFORE board.push(move) —
    otherwise the post-push board state makes is_capture() unreliable and the
    capture bonus can land on the wrong move.
"""
from __future__ import annotations

import chess

from core.activity.chess_ai import _apply_style


def test_teaching_style_prefers_capture_over_equal_valued_quiet_move():
    # White pawn e4 can capture black pawn d5; white king e1 can also make a
    # quiet non-capturing move to d1. Both moves are given the same base
    # minimax value so only the teaching-style capture bonus decides ranking.
    board = chess.Board("4k3/8/8/3p4/4P3/8/8/4K3 w - - 0 1")
    capture_move = chess.Move.from_uci("e4d5")
    quiet_move = chess.Move.from_uci("e1d1")
    assert capture_move in board.legal_moves
    assert quiet_move in board.legal_moves

    scored = [(0, quiet_move), (0, capture_move)]
    result = _apply_style(scored, board, chess.WHITE, "teaching")
    assert result == capture_move, "teaching style must rank the capture above an equally-valued quiet move"
