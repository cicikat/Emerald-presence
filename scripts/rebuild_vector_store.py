"""一次性回填向量库。用法：python scripts/rebuild_vector_store.py [uid] [char_id]
不带参数时遍历 data/runtime/memory/{char_id}/{uid}/ 下所有 (char_id, uid)。"""
import asyncio
import sys
from pathlib import Path

# ensure project root is on sys.path when run from any cwd
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.memory import vector_store as vs
from core.sandbox import get_paths


async def _one(uid: str, char_id: str) -> None:
    n = await vs.rebuild(uid, char_id)
    print(f"[rebuild] char={char_id} uid={uid} -> {n} 条")


async def main() -> None:
    if len(sys.argv) >= 3:
        await _one(sys.argv[1], sys.argv[2])
        return

    # data/runtime/memory root: user_memory_root returns .../memory/{char}/{uid},
    # so .parent.parent gives data/runtime/memory
    root: Path = get_paths().user_memory_root("x", char_id="y").parent.parent
    if not root.exists():
        print(f"[rebuild] memory root not found: {root}")
        return

    for char_dir in sorted(p for p in root.iterdir() if p.is_dir()):
        for uid_dir in sorted(p for p in char_dir.iterdir() if p.is_dir()):
            try:
                await _one(uid_dir.name, char_dir.name)
            except Exception as e:
                print(f"[rebuild][skip] {char_dir.name}/{uid_dir.name}: {e}")


if __name__ == "__main__":
    asyncio.run(main())
