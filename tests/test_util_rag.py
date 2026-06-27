import os
import sys
import tempfile
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

os.environ.setdefault("DATABASE_URL", "mysql+aiomysql://test:test@127.0.0.1/test")
os.environ.setdefault("LLM_API_KEY", "test-key")
os.environ.setdefault("LLM_BASE_URL", "http://localhost")
os.environ.setdefault("LLM_EMBEDDING_MODEL", "text-embedding-3-small")
os.environ["QDRANT_DATA_PATH"] = tempfile.mkdtemp(prefix="zcs-qdrant-test-")

import UtilRAG
from models import ActivityKBMount, KnowledgeBase


class _FakeLog:
    def debug(self, *_args, **_kwargs):
        pass

    def info(self, *_args, **_kwargs):
        pass

    def warning(self, *_args, **_kwargs):
        pass

    def error(self, *_args, **_kwargs):
        pass


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _FakeDb:
    def __init__(self, rows):
        self.rows = rows
        self.statement = None

    async def execute(self, statement):
        self.statement = statement
        return _FakeResult(self.rows)


class _FakeQdrant:
    async def query_points(self, **_kwargs):
        return SimpleNamespace(
            points=[
                SimpleNamespace(
                    score=0.81,
                    payload={
                        "text": "新追加但弱相关的片段",
                        "added_at": "2026-06-01T00:00:00+00:00",
                    },
                ),
                SimpleNamespace(
                    score=0.97,
                    payload={
                        "text": "客户提到的知识库核心内容",
                        "added_at": "2024-01-01T00:00:00+00:00",
                    },
                ),
            ]
        )


@pytest.mark.asyncio
async def test_retrieve_rag_uses_activity_mount_and_org_scope(monkeypatch):
    async def fake_embeddings(_client, _texts):
        return [[0.1] * 1536]

    kb = KnowledgeBase(
        id="kb_org_level",
        name="产品知识库",
        usage_guideline="按知识库回答",
        org_id="org_1",
        group_id=None,
        is_shared_to_groups=False,
        vector_collection_name="col_org_1_kb_org_level",
    )
    mount = ActivityKBMount(
        activity_id="act_1",
        kb_id="kb_org_level",
        priority=1,
        mount_guideline=None,
    )
    db = _FakeDb([(kb, mount)])

    monkeypatch.setattr(UtilRAG, "get_embeddings", fake_embeddings)
    monkeypatch.setattr(UtilRAG, "qdrant_client", _FakeQdrant())

    context, instructions = await UtilRAG.retrieve_rag_context(
        db=db,
        activity_id="act_1",
        org_id="org_1",
        group_id="group_1",
        visitor_msg="客户提到了核心内容",
        log=_FakeLog(),
    )

    criteria = "\n".join(str(c) for c in db.statement._where_criteria)
    assert "knowledge_bases.org_id" in criteria
    assert "knowledge_bases.group_id" not in criteria
    assert "knowledge_bases.is_shared_to_groups" not in criteria
    assert context.index("客户提到的知识库核心内容") < context.index("新追加但弱相关的片段")
    assert "按知识库回答" in instructions
