"""
RuleEngine.py
=============
P2 高维联合规则引擎。

设计要点
--------
- 纯函数 + dict 上下文,业务逻辑可单测(`tests/test_rule_engine.py`)。
- 字段/操作符白名单(`ALLOWED_FIELDS`/`ALLOWED_OPS`)防止配置注入。
- 评估分两个 phase:
    * `pre_llm`  : LLM 调用前,主要做拦截类(转人工、关键词阻断、block_llm)
    * `post_llm` : LLM 调用后,做增强类(发素材/支付链接/webhook、override_reply)
- fire_policy 防"复读机":
    * once_per_session : DB 唯一约束兜底 + 本批 already_fired_rule_ids 集合
    * once_per_stage   : 查 session_rule_fires WHERE session_id AND rule_id AND fired_at_stage=本 stage
    * every_n_turns:N  : 上次 fire 距今 total_turn_count 差值 >= N
    * always           : 不限
- 动作执行使用 dispatch_many() 串行执行(同一规则内 action 顺序敏感:文本→链接→webhook)。
"""
from __future__ import annotations

import asyncio
from typing import Optional

import httpx
from loguru import logger
from sqlalchemy import select, insert, desc
from sqlalchemy.ext.asyncio import AsyncSession

from models import (
    ActivityEventRule,
    SessionRuleFire,
    AgentNotification,
    WebhookDeadLetter,
    Message,
    SessionRecord,
    Employee,
)


# =============================================================================
# 1. 条件 DSL 白名单与匹配
# =============================================================================
ALLOWED_FIELDS = {
    "new_emotion", "prev_emotion",
    "new_stage", "prev_stage",
    "stage_flipped", "stage_flipped_to",
    "total_turn_count", "stage_turn_count",
    "extracted_tags",
    "emotion_degraded",       # 计算字段: 上一轮非负向 -> 这一轮变负向
    "detected_language",
}
ALLOWED_OPS = {
    "eq", "neq", "in", "not_in",
    "gte", "gt", "lte", "lt",
    "contains", "not_contains",
}

NEGATIVE_EMOTIONS = {"hesitation", "impatience", "anger"}


def build_context_post_llm(
    *,
    prev_stage: str,
    prev_emotion: str,
    new_total_turn: int,
    new_stage_turn: int,
    llm_decision: dict,
) -> dict:
    """LLM 跑完之后组装的评估上下文。"""
    new_emotion = llm_decision.get("customer_emotion", prev_emotion)
    new_stage = llm_decision.get("next_stage", prev_stage)
    return {
        "prev_emotion": prev_emotion,
        "new_emotion": new_emotion,
        "prev_stage": prev_stage,
        "new_stage": new_stage,
        "stage_flipped": new_stage != prev_stage,
        "stage_flipped_to": new_stage if new_stage != prev_stage else None,
        "total_turn_count": new_total_turn,
        "stage_turn_count": new_stage_turn,
        "extracted_tags": llm_decision.get("extracted_tags", []) or [],
        "detected_language": llm_decision.get("detected_language", "unknown"),
        "emotion_degraded": (
            prev_emotion not in NEGATIVE_EMOTIONS and new_emotion in NEGATIVE_EMOTIONS
        ),
    }


def build_context_pre_llm(
    *,
    cur_stage: str,
    cur_emotion: str,
    total_turn: int,
    stage_turn: int,
) -> dict:
    """LLM 调用前上下文:还没拿到 LLM 输出,语种/tags 为空。"""
    return {
        "prev_emotion": cur_emotion,
        "new_emotion": cur_emotion,
        "prev_stage": cur_stage,
        "new_stage": cur_stage,
        "stage_flipped": False,
        "stage_flipped_to": None,
        "total_turn_count": total_turn,
        "stage_turn_count": stage_turn,
        "extracted_tags": [],
        "detected_language": "unknown",
        "emotion_degraded": False,
    }


def _match_one(cond: dict, ctx: dict) -> bool:
    field = cond.get("field")
    op = cond.get("op")
    val = cond.get("value")
    if field not in ALLOWED_FIELDS or op not in ALLOWED_OPS:
        logger.warning(f"[RuleEngine] 非法条件 field={field!r} op={op!r},按 False 处理")
        return False
    actual = ctx.get(field)
    if op == "eq":           return actual == val
    if op == "neq":          return actual != val
    if op == "in":           return actual in (val or [])
    if op == "not_in":       return actual not in (val or [])
    # 数值类: 若 val 为 None 视为非法配置, 直接 False(避免 0>=None 报错)
    if op in ("gte", "gt", "lte", "lt"):
        if val is None:
            return False
        a = actual if isinstance(actual, (int, float)) else 0
        if op == "gte": return a >= val
        if op == "gt":  return a >  val
        if op == "lte": return a <= val
        if op == "lt":  return a <  val
    if op == "contains":
        if val is None: return False
        haystack = actual if isinstance(actual, (list, str, tuple, set)) else []
        return val in haystack
    if op == "not_contains":
        if val is None: return True
        haystack = actual if isinstance(actual, (list, str, tuple, set)) else []
        return val not in haystack
    return False


def match_rule(rule_conditions: dict, ctx: dict) -> bool:
    """
    rule_conditions = {"all": [...], "any": [...]}
    - 同时有 all 和 any: 必须全 all 通过 且 至少一个 any 通过
    - 只有 all: 全 all 通过
    - 只有 any: 至少一个 any 通过
    - 都为空: 永不命中(防止 "空条件 = 全命中" 误配置)
    """
    all_conds = rule_conditions.get("all") or []
    any_conds = rule_conditions.get("any") or []
    if not all_conds and not any_conds:
        return False
    if all_conds and not all(_match_one(c, ctx) for c in all_conds):
        return False
    if any_conds and not any(_match_one(c, ctx) for c in any_conds):
        return False
    return True


# =============================================================================
# 2. 规则加载 + fire policy 过滤
# =============================================================================
async def load_active_rules(
    db: AsyncSession, *, org_id: str, activity_id: Optional[str], phase: str,
) -> list[ActivityEventRule]:
    """读取该 org + 该 activity(或全 org 共用)的启用规则,按 priority desc 排序。"""
    stmt = (
        select(ActivityEventRule)
        .where(ActivityEventRule.org_id == org_id)
        .where(ActivityEventRule.is_active.is_(True))
        .where(ActivityEventRule.phase == phase)
    )
    # activity_id IS NULL 是 "该 org 全部 activity 共用",所以要 OR
    if activity_id:
        stmt = stmt.where(
            (ActivityEventRule.activity_id == activity_id)
            | (ActivityEventRule.activity_id.is_(None))
        )
    else:
        stmt = stmt.where(ActivityEventRule.activity_id.is_(None))
    stmt = stmt.order_by(desc(ActivityEventRule.priority))
    res = await db.execute(stmt)
    return list(res.scalars().all())


async def _can_fire_by_policy(
    db: AsyncSession,
    *,
    session_id: str,
    rule: ActivityEventRule,
    current_stage: str,
    current_total_turn: int,
) -> bool:
    """根据 fire_policy 判断本轮是否允许触发。"""
    policy = (rule.fire_policy or "once_per_session").strip()

    if policy == "always":
        return True

    if policy == "once_per_session":
        # 唯一约束已经兜底; 这里查一下避免无谓 INSERT 报错日志
        r = await db.execute(
            select(SessionRuleFire.id)
            .where(SessionRuleFire.session_id == session_id)
            .where(SessionRuleFire.rule_id == rule.id)
            .limit(1)
        )
        return r.scalar_one_or_none() is None

    if policy == "once_per_stage":
        r = await db.execute(
            select(SessionRuleFire.id)
            .where(SessionRuleFire.session_id == session_id)
            .where(SessionRuleFire.rule_id == rule.id)
            .where(SessionRuleFire.fired_at_stage == current_stage)
            .limit(1)
        )
        return r.scalar_one_or_none() is None

    if policy.startswith("every_n_turns:"):
        try:
            n = int(policy.split(":", 1)[1])
        except Exception:
            logger.warning(f"[RuleEngine] 非法 fire_policy: {policy}, 默认拒绝")
            return False
        r = await db.execute(
            select(SessionRuleFire.fired_at_total_turn)
            .where(SessionRuleFire.session_id == session_id)
            .where(SessionRuleFire.rule_id == rule.id)
            .order_by(desc(SessionRuleFire.fired_at)).limit(1)
        )
        last = r.scalar_one_or_none()
        if last is None:
            return True
        return (current_total_turn - int(last)) >= n

    logger.warning(f"[RuleEngine] 未知 fire_policy={policy!r}, 默认拒绝")
    return False


async def evaluate(
    rules: list[ActivityEventRule],
    ctx: dict,
    db: AsyncSession,
    *,
    session_id: str,
    current_stage: str,
    current_total_turn: int,
) -> list[ActivityEventRule]:
    """返回本轮应触发的规则列表 (按 priority desc; short_circuit 命中后停)。"""
    hits: list[ActivityEventRule] = []
    for rule in rules:
        if not match_rule(rule.conditions or {}, ctx):
            continue
        if not await _can_fire_by_policy(
            db,
            session_id=session_id,
            rule=rule,
            current_stage=current_stage,
            current_total_turn=current_total_turn,
        ):
            continue
        hits.append(rule)
        if rule.short_circuit:
            break
    return hits


# =============================================================================
# 3. 动作执行
# =============================================================================
class DispatchResult:
    """规则评估 + 派发的聚合结果, 主流程根据这个决定后续是否阻塞/覆盖/转人工。"""

    def __init__(self):
        self.blocked_llm: bool = False        # pre_llm 阶段是否要直接 return
        self.override_reply: Optional[str] = None  # 覆盖 LLM 即将生成/已生成的回复
        self.extra_visitor_payloads: list[dict] = []   # 要追加发给访客的 WS payload
        self.transfer_to_human: bool = False  # 是否要把 session 标记 takeover
        self.transfer_target_employee_id: Optional[str] = None
        self.transfer_reason: Optional[str] = None
        self.fired_rule_ids: list[str] = []   # 本轮成功触发的 rule_id, 用于写审计


async def dispatch_many(
    rules: list[ActivityEventRule],
    ctx: dict,
    *,
    db: AsyncSession,
    sess: SessionRecord,
    visitor_conn_id: str,
    visitor_manager,
    agent_manager,
    log,
) -> DispatchResult:
    out = DispatchResult()
    for rule in rules:
        action_results: list[dict] = []
        try:
            await _dispatch_one(
                rule, ctx,
                db=db, sess=sess,
                visitor_conn_id=visitor_conn_id,
                visitor_manager=visitor_manager,
                agent_manager=agent_manager,
                out=out, action_results=action_results,
                log=log,
            )
        except Exception as e:
            log.exception(f"[RuleEngine] 规则 {rule.id} ({rule.name}) 执行异常: {e}")
            action_results.append({"error": str(e)})

        # 写一行审计
        try:
            await db.execute(
                insert(SessionRuleFire).prefix_with("IGNORE").values(
                    session_id=sess.id,
                    rule_id=rule.id,
                    fired_at_stage=sess.current_stage,
                    fired_at_total_turn=sess.total_turn_count,
                    fired_at_stage_turn=sess.stage_turn_count,
                    actions_executed=action_results,
                )
            )
            await db.commit()
            out.fired_rule_ids.append(rule.id)
            log.info(f"[RuleEngine] ⚡ 命中规则 [{rule.name}] (id={rule.id}, policy={rule.fire_policy})")
        except Exception as e:
            log.warning(f"[RuleEngine] 写审计 session_rule_fires 失败: {e}")
            await db.rollback()

    return out


async def _dispatch_one(
    rule: ActivityEventRule,
    ctx: dict,
    *,
    db: AsyncSession,
    sess: SessionRecord,
    visitor_conn_id: str,
    visitor_manager,
    agent_manager,
    out: DispatchResult,
    action_results: list[dict],
    log,
):
    """串行执行单条规则的 action 列表。"""
    for action in (rule.actions or []):
        atype = action.get("type")
        try:
            if atype == "send_text":
                content = action.get("content", "")
                await _persist_rule_message(
                    db, sess, content=content, kind="text", rule_id=rule.id,
                )
                await visitor_manager.send_to_client(visitor_conn_id, {
                    "action": "inject_reply",
                    "data": {"session_id": sess.id, "text": content, "simulate_typing": True,
                             "fired_by_rule_id": rule.id},
                })
                action_results.append({"type": atype, "ok": True})

            elif atype in ("send_link", "send_image", "send_video", "send_payment_link"):
                kind_map = {
                    "send_link": "link",
                    "send_image": "image",
                    "send_video": "video",
                    "send_payment_link": "payment",
                }
                payload = {
                    "kind": kind_map[atype],
                    "url": action.get("url"),
                    "label": action.get("label"),
                    "caption": action.get("caption"),
                    "amount": action.get("amount"),
                    "currency": action.get("currency"),
                }
                payload = {k: v for k, v in payload.items() if v is not None}
                # 写 Message: content 字段用 url, 便于历史回放; 富媒体细节存 llm_decision_raw 同款 JSON
                await _persist_rule_message(
                    db, sess,
                    content=action.get("url") or "",
                    kind=kind_map[atype],
                    rule_id=rule.id,
                    payload=payload,
                )
                await visitor_manager.send_to_client(visitor_conn_id, {
                    "action": "inject_media",
                    "data": {"session_id": sess.id, **payload,
                             "fired_by_rule_id": rule.id},
                })
                action_results.append({"type": atype, "ok": True})

            elif atype == "send_material":
                # 素材库本期不实现, 留 TODO; 仅写 system message 记录意图便于后续补
                mid = action.get("material_id")
                log.warning(f"[RuleEngine] send_material(material_id={mid}) 暂未实现, 跳过 (rule={rule.id})")
                action_results.append({"type": atype, "ok": False, "reason": "not_implemented"})

            elif atype == "transfer_to_human":
                target_eid = action.get("target_employee_id")
                target_group = action.get("target_group_id")
                reason = action.get("reason") or f"规则[{rule.name}]触发"
                out.transfer_to_human = True
                out.transfer_target_employee_id = target_eid
                out.transfer_reason = reason
                await _do_transfer_to_human(
                    db, sess,
                    target_employee_id=target_eid,
                    target_group_id=target_group,
                    rule=rule, reason=reason,
                    agent_manager=agent_manager,
                    log=log,
                )
                action_results.append({"type": atype, "ok": True,
                                       "target_employee_id": target_eid,
                                       "target_group_id": target_group})

            elif atype == "system_notify":
                noti = AgentNotification(
                    org_id=sess.org_id,
                    group_id=sess.group_id,
                    target_employee_id=action.get("target_employee_id"),
                    session_id=sess.id,
                    rule_id=rule.id,
                    level=action.get("level", "info"),
                    title=action.get("title") or f"规则[{rule.name}]提醒",
                    body=action.get("body"),
                )
                db.add(noti)
                await db.commit()
                # 推到员工 WS
                if action.get("target_employee_id"):
                    await agent_manager.push(action["target_employee_id"], {
                        "action": "notification",
                        "data": {"level": noti.level, "title": noti.title,
                                 "body": noti.body, "session_id": sess.id, "rule_id": rule.id},
                    })
                action_results.append({"type": atype, "ok": True})

            elif atype == "webhook":
                # body 自动拼上 session/ctx, 下游消费者能直接看 session_id/stage/emotion 等
                user_body = action.get("body") or {}
                merged_body = {
                    "session_id": sess.id,
                    "rule_id": rule.id,
                    "rule_name": rule.name,
                    "ctx": ctx,
                    "user_body": user_body,
                }
                asyncio.create_task(_fire_webhook(
                    session_id=sess.id, rule_id=rule.id,
                    url=action.get("url"), method=action.get("method", "POST"),
                    body=merged_body, headers=action.get("headers") or {},
                    log=log,
                ))
                action_results.append({"type": atype, "ok": True, "dispatched_async": True})

            elif atype == "override_reply":
                out.override_reply = action.get("content", "")
                action_results.append({"type": atype, "ok": True})

            elif atype == "block_llm":
                out.blocked_llm = True
                action_results.append({"type": atype, "ok": True})

            elif atype == "set_tag":
                # P2 不加 sessions.tags 列, 仅日志; P3 再做
                log.info(f"[RuleEngine] set_tag {action.get('tag')!r} (P3 实现)")
                action_results.append({"type": atype, "ok": False, "reason": "not_implemented"})

            else:
                log.warning(f"[RuleEngine] 未知 action.type={atype!r} (rule={rule.id})")
                action_results.append({"type": atype, "ok": False, "reason": "unknown_type"})

        except Exception as e:
            log.exception(f"[RuleEngine] action {atype} 执行异常: {e}")
            action_results.append({"type": atype, "ok": False, "error": str(e)})


# =============================================================================
# 4. 辅助: 写 Message / 转人工 / Webhook
# =============================================================================
async def _persist_rule_message(
    db: AsyncSession,
    sess: SessionRecord,
    *,
    content: str,
    kind: str,
    rule_id: str,
    payload: Optional[dict] = None,
):
    """规则触发的消息按 sender_type=system 入库, 携带 fired_by_rule_id 便于检索。"""
    msg = Message(
        session_id=sess.id,
        org_id=sess.org_id,
        group_id=sess.group_id,
        activity_id=sess.activity_id,
        sender_type="system",
        sender_id=None,
        content=content if content else f"[{kind}]",
        stage_at_send=sess.current_stage,
        emotion_at_send=sess.current_emotion,
        llm_decision_raw=payload,
        fired_by_rule_id=rule_id,
    )
    db.add(msg)
    await db.commit()


async def _do_transfer_to_human(
    db: AsyncSession,
    sess: SessionRecord,
    *,
    target_employee_id: Optional[str],
    target_group_id: Optional[str],
    rule: ActivityEventRule,
    reason: str,
    agent_manager,
    log,
):
    """把 session 标为 takeover, 写一条 system 消息, 把通知 push 给目标员工(或同组所有员工)。"""
    from datetime import datetime as _dt
    sess.is_human_takeover = True
    sess.human_takeover_at = _dt.utcnow()
    sess.human_takeover_by = target_employee_id  # 若广播则留 NULL, 由接管员工 takeover API 时再补
    if target_employee_id:
        sess.employee_id = target_employee_id

    db.add(Message(
        session_id=sess.id,
        org_id=sess.org_id,
        group_id=sess.group_id,
        activity_id=sess.activity_id,
        sender_type="system",
        sender_id=None,
        content=f"[系统] 会话已转人工: {reason}",
        stage_at_send=sess.current_stage,
        emotion_at_send=sess.current_emotion,
        fired_by_rule_id=rule.id,
    ))

    # 通知接收人: 优先定向, 否则同组广播
    notif_targets: list[Optional[str]] = []
    if target_employee_id:
        notif_targets = [target_employee_id]
    else:
        # 同组所有 online 真人员工(is_ai=False)
        gid = target_group_id or sess.group_id
        if gid:
            r = await db.execute(
                select(Employee.id).where(
                    Employee.group_id == gid,
                    Employee.is_ai.is_(False),
                    Employee.status == "online",
                )
            )
            notif_targets = list(r.scalars().all()) or [None]
        else:
            notif_targets = [None]

    for eid in notif_targets:
        db.add(AgentNotification(
            org_id=sess.org_id,
            group_id=sess.group_id,
            target_employee_id=eid,
            session_id=sess.id,
            rule_id=rule.id,
            level="urgent",
            title=f"客户需人工跟进 [{reason[:40]}]",
            body=f"session_id={sess.id} stage={sess.current_stage} emotion={sess.current_emotion}",
        ))
    await db.commit()

    # WS push
    for eid in notif_targets:
        if eid:
            await agent_manager.push(eid, {
                "action": "takeover_invite",
                "data": {
                    "session_id": sess.id,
                    "stage": sess.current_stage,
                    "emotion": sess.current_emotion,
                    "reason": reason,
                    "rule_id": rule.id,
                },
            })

    log.warning(f"[RuleEngine] 🚨 session {sess.id} 已转人工 -> targets={notif_targets}")


_WEBHOOK_TIMEOUT_S = 5.0
_WEBHOOK_RETRY_DELAYS = (0.5, 1.5)  # 总共 3 次尝试


async def _fire_webhook(
    *,
    session_id: str,
    rule_id: str,
    url: str,
    method: str,
    body: dict,
    headers: dict,
    log,
):
    """异步执行 webhook, 失败两次后入死信表。"""
    from database import AsyncSessionLocal  # 局部 import 避开循环

    method = (method or "POST").upper()
    attempt = 0
    last_err: Optional[str] = None
    payload_for_db = {"body": body, "headers": headers}
    async with httpx.AsyncClient(timeout=_WEBHOOK_TIMEOUT_S) as cli:
        for delay in (0.0,) + _WEBHOOK_RETRY_DELAYS:
            if delay > 0:
                await asyncio.sleep(delay)
            attempt += 1
            try:
                resp = await cli.request(method, url, json=body, headers=headers or None)
                if 200 <= resp.status_code < 300:
                    log.info(f"[Webhook] OK {method} {url} -> {resp.status_code} (attempt={attempt})")
                    return
                last_err = f"HTTP {resp.status_code}: {resp.text[:200]}"
            except Exception as e:
                last_err = repr(e)
            log.warning(f"[Webhook] attempt={attempt} {method} {url} 失败: {last_err}")

    # 三次都失败, 入死信
    try:
        async with AsyncSessionLocal() as db:
            db.add(WebhookDeadLetter(
                session_id=session_id, rule_id=rule_id,
                url=url, method=method,
                payload=payload_for_db, last_error=last_err, attempts=attempt,
            ))
            await db.commit()
        log.error(f"[Webhook] 💀 入死信表 url={url} attempts={attempt} err={last_err}")
    except Exception as e:
        log.exception(f"[Webhook] 写死信表也失败: {e}")


# =============================================================================
# 5. metadata: 供前端下拉用
# =============================================================================
# 字段 / 操作符 / 动作类型的人话描述。前端 UI 用 label_zh 显示, 选中存 value (即 raw key)。
# 加新字段时同时在这三张表里加 label,不然前端下拉会显示空白。

_FIELD_LABELS = {
    "new_emotion":       {"zh": "本轮客户情绪",        "en": "Current emotion",     "hint": "LLM 对本轮客户消息判定的情绪"},
    "prev_emotion":      {"zh": "上一轮客户情绪",      "en": "Previous emotion",    "hint": "本轮 LLM 跑之前 session 上记录的情绪"},
    "new_stage":         {"zh": "本轮 SOP 阶段",       "en": "Current stage",       "hint": "LLM 判定后客户进入/停留的阶段"},
    "prev_stage":        {"zh": "上一轮 SOP 阶段",     "en": "Previous stage",      "hint": "LLM 跑之前的 stage"},
    "stage_flipped":     {"zh": "本轮是否跨阶段",      "en": "Stage flipped (bool)","hint": "true = 本轮发生了 stage 切换"},
    "stage_flipped_to":  {"zh": "本轮跳到了哪个阶段",  "en": "Flipped to stage",    "hint": "瞬时事件: 仅在跨阶段的那一轮有值"},
    "total_turn_count":  {"zh": "总对话回合数",        "en": "Total turns",         "hint": "整个 session 的访客消息条数"},
    "stage_turn_count":  {"zh": "当前阶段回合数",      "en": "Current stage turns", "hint": "在当前 stage 停留了多少回合, 跨阶段会重置为 1"},
    "extracted_tags":    {"zh": "LLM 提取的标签",      "en": "Extracted tags",      "hint": "如 [高意向, 在意价格]; 用 contains 判断"},
    "emotion_degraded":  {"zh": "情绪是否恶化",        "en": "Emotion degraded",    "hint": "上一轮非负 → 本轮负向(犹豫/急躁/愤怒)"},
    "detected_language": {"zh": "检测到的访客语言",    "en": "Detected language",   "hint": "zh-CN / en-US / ja / es ..."},
}

_OP_LABELS = {
    "eq":            {"zh": "等于",     "en": "= (equals)"},
    "neq":           {"zh": "不等于",   "en": "≠ (not equals)"},
    "in":            {"zh": "在列表中", "en": "in [...]"},
    "not_in":        {"zh": "不在列表", "en": "not in [...]"},
    "gte":           {"zh": "≥ 大于等于","en": ">= "},
    "gt":            {"zh": "> 大于",   "en": "> "},
    "lte":           {"zh": "≤ 小于等于","en": "<= "},
    "lt":            {"zh": "< 小于",   "en": "< "},
    "contains":      {"zh": "包含",     "en": "contains"},
    "not_contains":  {"zh": "不包含",   "en": "not contains"},
}

_EMOTION_LABELS = {
    "calm":       {"zh": "平静",  "en": "calm"},
    "joy":        {"zh": "喜悦",  "en": "joy"},
    "excited":    {"zh": "兴奋",  "en": "excited"},
    "hesitation": {"zh": "犹豫",  "en": "hesitation"},
    "impatience": {"zh": "急躁",  "en": "impatience"},
    "anger":      {"zh": "愤怒",  "en": "anger"},
}

_ACTION_LABELS = {
    "send_text":         {"zh": "发送文本",       "en": "Send text"},
    "send_link":         {"zh": "发送链接",       "en": "Send link"},
    "send_image":        {"zh": "发送图片",       "en": "Send image"},
    "send_video":        {"zh": "发送视频",       "en": "Send video"},
    "send_payment_link": {"zh": "发送支付链接",   "en": "Send payment link"},
    "send_material":     {"zh": "发送素材(暂未启用)","en": "Send material (TBD)"},
    "transfer_to_human": {"zh": "转人工接管",     "en": "Transfer to human"},
    "system_notify":     {"zh": "系统通知员工",   "en": "System notify"},
    "webhook":           {"zh": "调用 Webhook",   "en": "Call webhook"},
    "override_reply":    {"zh": "覆盖 LLM 回复",  "en": "Override LLM reply"},
    "block_llm":         {"zh": "阻断 LLM 调用",  "en": "Block LLM"},
    "set_tag":           {"zh": "打标签(暂未启用)","en": "Set tag (TBD)"},
}

_FIRE_POLICY_LABELS = {
    "once_per_session": {"zh": "整个会话只触发一次", "en": "Once per session"},
    "once_per_stage":   {"zh": "每个 stage 只触发一次","en": "Once per stage"},
    "every_n_turns:3":  {"zh": "每 3 回合可再触发",  "en": "Every 3 turns"},
    "every_n_turns:5":  {"zh": "每 5 回合可再触发",  "en": "Every 5 turns"},
    "always":           {"zh": "每次满足都触发",    "en": "Always"},
}

_PHASE_LABELS = {
    "pre_llm":  {"zh": "LLM 调用前 (拦截类)",     "en": "Before LLM (intercept)"},
    "post_llm": {"zh": "LLM 调用后 (增强类)",     "en": "After LLM (enrich)"},
}

# 业务约定的 SOP stage 枚举(与 database.sql 中 stages_config 对齐)。
# 注: 每个 activity 可以自定义自己的 stages, 这里给的是"全公司通用"的 6 个 SOP key。
# 前端展示时按 activity 自己的 stages_config 覆盖也可以,但 90% 场景就是这 6 个。
_STAGE_LABELS_GLOBAL = {
    "stage_1_icebreak":   {"zh": "破冰与探需",       "en": "Icebreak"},
    "stage_2_solution":   {"zh": "方案与价值传递",   "en": "Solution"},
    "stage_3_objection":  {"zh": "异议处理",         "en": "Objection handling"},
    "stage_4_push":       {"zh": "逼单转化",         "en": "Push for close"},
    "stage_5_sleep":      {"zh": "沉睡/沉默",        "en": "Sleep"},
    "stage_6_aftersales": {"zh": "售后",             "en": "Aftersales"},
}


def _enriched(d: dict, value: str) -> dict:
    """把 (value, {zh, en, hint?}) 合成前端要的 {value, label_zh, label_en, hint}。"""
    info = d.get(value, {})
    return {
        "value": value,
        "label_zh": info.get("zh", value),
        "label_en": info.get("en", value),
        "hint": info.get("hint"),
    }


def metadata_for_frontend() -> dict:
    """供 GET /api/event-rules/metadata 返回, 让前端节点画布拿到合法字段/op/动作列表。

    每一项 = {value, label_zh, label_en, hint?}。前端下拉用 label_zh 显示, value 仍是 raw key。
    """
    return {
        "fields": [_enriched(_FIELD_LABELS, f) for f in sorted(ALLOWED_FIELDS)],
        "ops":    [_enriched(_OP_LABELS,    o) for o in sorted(ALLOWED_OPS)],
        "emotions": [_enriched(_EMOTION_LABELS, e) for e in
                     ["calm", "joy", "excited", "hesitation", "impatience", "anger"]],
        "stages_global": [_enriched(_STAGE_LABELS_GLOBAL, s) for s in _STAGE_LABELS_GLOBAL.keys()],
        "fire_policies": [_enriched(_FIRE_POLICY_LABELS, p) for p in
                          ["once_per_session", "once_per_stage",
                           "every_n_turns:3", "every_n_turns:5", "always"]],
        "phases": [_enriched(_PHASE_LABELS, p) for p in ["pre_llm", "post_llm"]],
        "action_types": [_enriched(_ACTION_LABELS, a) for a in [
            "send_text", "send_link", "send_image", "send_video",
            "send_payment_link", "send_material",
            "transfer_to_human", "system_notify", "webhook",
            "override_reply", "block_llm", "set_tag",
        ]],
        # 用前端 v-if 判断"字段是否是 stage 类"
        "stage_like_fields": ["new_stage", "prev_stage", "stage_flipped_to"],
        "emotion_like_fields": ["new_emotion", "prev_emotion"],
        "boolean_like_fields": ["stage_flipped", "emotion_degraded"],
    }
