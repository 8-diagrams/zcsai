"""
fire_policy 集成测试 (every_n_turns / once_per_session / once_per_stage / always)。

用 aiosqlite 内存库代替 MySQL,只验证 _can_fire_by_policy 的查询逻辑;
顺带回归 P2 期发现的 bug:  唯一约束 + INSERT IGNORE 把 every_n_turns 的"上次回合"毒化。
"""
import sys, os
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from database import Base
import models  # noqa: F401  让 ORM 注册到 metadata
from models import SessionRuleFire, ActivityEventRule
from RuleEngine import _can_fire_by_policy


@pytest_asyncio.fixture
async def db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    SessionLocal = async_sessionmaker(engine, expire_on_commit=False)
    async with SessionLocal() as s:
        yield s
    await engine.dispose()


def _rule(rid: str, policy: str) -> ActivityEventRule:
    """构造一个本地 ORM 对象 (不入库, 只是为了把字段塞给 _can_fire_by_policy)。"""
    r = ActivityEventRule(
        id=rid, org_id="org_x", activity_id=None,
        name=rid, priority=0, is_active=True, phase="post_llm",
        conditions={"all": []}, actions=[],
        fire_policy=policy, short_circuit=False,
    )
    return r


async def _record_fire(db: AsyncSession, session_id: str, rule_id: str,
                       total_turn: int, stage: str = "stage_2_solution"):
    db.add(SessionRuleFire(
        session_id=session_id, rule_id=rule_id,
        fired_at_stage=stage,
        fired_at_total_turn=total_turn,
        fired_at_stage_turn=1,
        actions_executed=[],
    ))
    await db.commit()


# ---------------------------------------------------------------------------
# every_n_turns:N
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_every_n_turns_first_time_allowed(db):
    rule = _rule("r_every", "every_n_turns:3")
    ok = await _can_fire_by_policy(
        db, session_id="s1", rule=rule,
        current_stage="stage_2_solution", current_total_turn=3,
    )
    assert ok is True  # 历史空, 允许


@pytest.mark.asyncio
async def test_every_n_turns_not_enough_gap(db):
    rule = _rule("r_every", "every_n_turns:3")
    await _record_fire(db, "s1", rule.id, total_turn=3)
    # 第 5 回合: delta=2 < 3, 不允许
    ok = await _can_fire_by_policy(
        db, session_id="s1", rule=rule,
        current_stage="stage_2_solution", current_total_turn=5,
    )
    assert ok is False


@pytest.mark.asyncio
async def test_every_n_turns_second_time_after_gap(db):
    """关键回归: 第一次记录后, 第二次满 N 回合时仍应允许。
    P2 期 bug: 唯一约束让第二次的 INSERT 被 IGNORE 丢弃,
    但 _can_fire_by_policy 本身的逻辑是对的, 现在去掉唯一约束后第二条能落进表,
    第三次时 last_turn 会正确推进。
    """
    rule = _rule("r_every", "every_n_turns:3")
    await _record_fire(db, "s1", rule.id, total_turn=3)
    # 第 6 回合: 6-3=3 ≥ 3, 允许
    ok1 = await _can_fire_by_policy(
        db, session_id="s1", rule=rule,
        current_stage="stage_2_solution", current_total_turn=6,
    )
    assert ok1 is True
    # 模拟刚才允许后 dispatch_many 把第 6 回合的命中也写入审计
    await _record_fire(db, "s1", rule.id, total_turn=6)
    # 第 7 回合: 7-6=1 < 3, 不允许 (回归: 之前 bug 这里会算成 7-3=4 ≥3 错允)
    ok2 = await _can_fire_by_policy(
        db, session_id="s1", rule=rule,
        current_stage="stage_2_solution", current_total_turn=7,
    )
    assert ok2 is False
    # 第 9 回合: 9-6=3 ≥ 3, 允许
    ok3 = await _can_fire_by_policy(
        db, session_id="s1", rule=rule,
        current_stage="stage_2_solution", current_total_turn=9,
    )
    assert ok3 is True


@pytest.mark.asyncio
async def test_every_n_turns_uses_max_not_min(db):
    """模拟一个时钟乱序: 先插 total_turn=6, 后插 total_turn=3。
    用 MAX(fired_at_total_turn) 才正确, ORDER BY fired_at DESC 在这种情况会出错。
    """
    rule = _rule("r_every", "every_n_turns:3")
    await _record_fire(db, "s1", rule.id, total_turn=6)
    await _record_fire(db, "s1", rule.id, total_turn=3)
    # 第 8 回合: 距 last(=6) delta=2 < 3, 应拒绝
    ok = await _can_fire_by_policy(
        db, session_id="s1", rule=rule,
        current_stage="stage_2_solution", current_total_turn=8,
    )
    assert ok is False


@pytest.mark.asyncio
async def test_every_n_turns_invalid_n(db):
    rule = _rule("r_bad", "every_n_turns:0")
    ok = await _can_fire_by_policy(
        db, session_id="s1", rule=rule,
        current_stage="x", current_total_turn=5,
    )
    assert ok is False
    rule = _rule("r_bad", "every_n_turns:abc")
    ok = await _can_fire_by_policy(
        db, session_id="s1", rule=rule,
        current_stage="x", current_total_turn=5,
    )
    assert ok is False


# ---------------------------------------------------------------------------
# once_per_session
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_once_per_session(db):
    rule = _rule("r_once", "once_per_session")
    ok1 = await _can_fire_by_policy(db, session_id="s1", rule=rule,
                                     current_stage="x", current_total_turn=1)
    assert ok1 is True
    await _record_fire(db, "s1", rule.id, total_turn=1)
    ok2 = await _can_fire_by_policy(db, session_id="s1", rule=rule,
                                     current_stage="x", current_total_turn=2)
    assert ok2 is False
    # 跨 session 不受影响
    ok3 = await _can_fire_by_policy(db, session_id="s2", rule=rule,
                                     current_stage="x", current_total_turn=1)
    assert ok3 is True


# ---------------------------------------------------------------------------
# once_per_stage
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_once_per_stage(db):
    rule = _rule("r_stage", "once_per_stage")
    await _record_fire(db, "s1", rule.id, total_turn=2, stage="stage_2_solution")
    # 同 stage 再触发不允许
    ok1 = await _can_fire_by_policy(db, session_id="s1", rule=rule,
                                     current_stage="stage_2_solution", current_total_turn=3)
    assert ok1 is False
    # 切到其他 stage 后允许
    ok2 = await _can_fire_by_policy(db, session_id="s1", rule=rule,
                                     current_stage="stage_4_push", current_total_turn=4)
    assert ok2 is True


# ---------------------------------------------------------------------------
# always
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_always_never_limits(db):
    rule = _rule("r_always", "always")
    await _record_fire(db, "s1", rule.id, total_turn=1)
    await _record_fire(db, "s1", rule.id, total_turn=2)
    ok = await _can_fire_by_policy(db, session_id="s1", rule=rule,
                                    current_stage="x", current_total_turn=3)
    assert ok is True
