"""
inbox — 文档投递接口。
用户丢文档 → 存 inbox/ → LLM 生成角色笔记存 notes/ → 更新 notes_index.json
"""
import json
import time
import hashlib
import logging
from pathlib import Path
from fastapi import APIRouter, UploadFile, File, Form

from core.sandbox import get_paths
from core import llm_client
from core.config_loader import _char_name

router = APIRouter()
logger = logging.getLogger(__name__)

_SUPPORTED = {".txt", ".md", ".pdf"}
_MAX_BYTES = 500_000  # 500KB

NOTES_PROMPT = f"""你是{_char_name()}，刚刚读完了一份文档。
用{_char_name()}的视角写下你读完之后的笔记——你记住了什么、觉得有意思的地方、让你想到了什么。
不是摘要，是你真实的阅读印象。控制在300字以内。
只输出笔记本身，不要标题，不要解释。

文档内容：
{{content}}"""


@router.post("/inbox/upload")
async def upload_doc(
    file: UploadFile = File(...),
    title: str = Form(default=""),
):
    # 格式检查
    suffix = Path(file.filename).suffix.lower()
    if suffix not in _SUPPORTED:
        return {"status": "error", "msg": f"不支持的格式，仅支持 {_SUPPORTED}"}

    raw = await file.read()
    if len(raw) > _MAX_BYTES:
        return {"status": "error", "msg": "文件太大，最大500KB"}

    # 生成 doc_id
    doc_id = hashlib.md5(raw).hexdigest()[:12]

    # 存原文
    paths = get_paths()
    doc_path = paths.inbox_dir() / f"{doc_id}{suffix}"
    doc_path.write_bytes(raw)

    # 提取文本
    if suffix == ".pdf":
        try:
            import pdfplumber
            with pdfplumber.open(doc_path) as pdf:
                content = "\n".join(p.extract_text() or "" for p in pdf.pages)
        except Exception as e:
            logger.warning(f"[inbox] PDF提取失败: {e}")
            content = ""
    else:
        content = raw.decode("utf-8", errors="ignore")

    if not content.strip():
        return {"status": "error", "msg": "文档内容为空或无法提取"}

    # 截断防超限
    content = content[:8000]

    # LLM 生成笔记
    prompt = NOTES_PROMPT.replace("{content}", content)
    try:
        note = await llm_client.chat([{"role": "user", "content": prompt}])
        note = note.strip()
    except Exception as e:
        logger.warning(f"[inbox] 笔记生成失败: {e}")
        note = ""

    # 存笔记
    note_path = paths.notes_dir() / f"{doc_id}.md"
    note_path.write_text(note, encoding="utf-8")

    # 更新 notes_index
    index_path = paths.notes_index()
    try:
        index = json.loads(index_path.read_text(encoding="utf-8"))
    except Exception:
        index = []

    index.append({
        "doc_id": doc_id,
        "title": title or file.filename,
        "suffix": suffix,
        "created_at": time.time(),
        "note_path": str(note_path),
        "tags": [],  # 后续可加 tag 抽取
    })
    index_path.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")

    logger.info(f"[inbox] 文档已处理: {doc_id} 笔记{len(note)}字")
    return {"status": "ok", "doc_id": doc_id, "note_preview": note[:100]}


@router.get("/inbox/notes")
async def list_notes():
    """列出所有笔记摘要。"""
    paths = get_paths()
    try:
        index = json.loads(paths.notes_index().read_text(encoding="utf-8"))
    except Exception:
        index = []
    return {"notes": index}
