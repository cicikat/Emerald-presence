"""
Per-user conversation gate.

This lock is intentionally separate from memory uid_lock:
- conversation_lock serializes full input turns for one user
- uid_lock only protects read-modify-write memory files
"""

import asyncio
from collections import defaultdict

_conversation_locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)


def conversation_lock(uid: str) -> asyncio.Lock:
    return _conversation_locks[str(uid)]
