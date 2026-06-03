"""
RuleEngine 纯函数侧的单元测试 (不碰 DB / 不碰 LLM)。

聚焦覆盖:
  - 各 op (eq/neq/in/not_in/gte/gt/lte/lt/contains/not_contains)
  - all / any 组合 + 空条件防御
  - build_context_post_llm 衍生字段 (stage_flipped / emotion_degraded / stage_flipped_to)
  - 非法 field / 非法 op 走 False (不抛)
"""
import sys
import os
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from RuleEngine import (
    _match_one, match_rule,
    build_context_pre_llm, build_context_post_llm,
    ALLOWED_FIELDS, ALLOWED_OPS, NEGATIVE_EMOTIONS,
    metadata_for_frontend,
)


# ---------------------------------------------------------------------------
# _match_one: 每个 op 至少一组真 + 一组假
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("cond, ctx, expected", [
    # eq / neq
    ({"field": "new_emotion", "op": "eq", "value": "anger"}, {"new_emotion": "anger"}, True),
    ({"field": "new_emotion", "op": "eq", "value": "anger"}, {"new_emotion": "calm"}, False),
    ({"field": "new_emotion", "op": "neq", "value": "calm"}, {"new_emotion": "anger"}, True),
    # in / not_in
    ({"field": "new_emotion", "op": "in", "value": ["impatience", "anger"]}, {"new_emotion": "anger"}, True),
    ({"field": "new_emotion", "op": "in", "value": ["impatience", "anger"]}, {"new_emotion": "calm"}, False),
    ({"field": "new_emotion", "op": "not_in", "value": ["calm", "joy"]}, {"new_emotion": "anger"}, True),
    # 数值类
    ({"field": "stage_turn_count", "op": "gte", "value": 3}, {"stage_turn_count": 5}, True),
    ({"field": "stage_turn_count", "op": "gte", "value": 3}, {"stage_turn_count": 2}, False),
    ({"field": "total_turn_count", "op": "gt",  "value": 3}, {"total_turn_count": 3}, False),
    ({"field": "total_turn_count", "op": "lte", "value": 3}, {"total_turn_count": 3}, True),
    ({"field": "total_turn_count", "op": "lt",  "value": 3}, {"total_turn_count": 3}, False),
    # 数值类 value=None 安全降级
    ({"field": "stage_turn_count", "op": "gte", "value": None}, {"stage_turn_count": 5}, False),
    # contains / not_contains
    ({"field": "extracted_tags", "op": "contains",     "value": "高意向"}, {"extracted_tags": ["高意向", "急"]},  True),
    ({"field": "extracted_tags", "op": "contains",     "value": "高意向"}, {"extracted_tags": []},                False),
    ({"field": "extracted_tags", "op": "not_contains", "value": "高意向"}, {"extracted_tags": ["其它"]},          True),
    ({"field": "extracted_tags", "op": "not_contains", "value": None},     {"extracted_tags": ["高意向"]},        True),
    # bool 字段
    ({"field": "stage_flipped",   "op": "eq", "value": True},  {"stage_flipped": True},  True),
    ({"field": "emotion_degraded","op": "eq", "value": True},  {"emotion_degraded": False}, False),
])
def test_match_one_each_op(cond, ctx, expected):
    assert _match_one(cond, ctx) is expected


def test_match_one_rejects_unknown_field():
    assert _match_one({"field": "evil_field", "op": "eq", "value": 1}, {"evil_field": 1}) is False


def test_match_one_rejects_unknown_op():
    assert _match_one({"field": "new_emotion", "op": "regex", "value": ".*"}, {"new_emotion": "x"}) is False


# ---------------------------------------------------------------------------
# match_rule: all / any 组合 + 防御
# ---------------------------------------------------------------------------
def test_match_rule_all_passes():
    conds = {"all": [
        {"field": "new_emotion",      "op": "in",  "value": ["impatience", "anger"]},
        {"field": "stage_turn_count", "op": "gte", "value": 3},
    ]}
    assert match_rule(conds, {"new_emotion": "anger", "stage_turn_count": 4}) is True


def test_match_rule_all_one_fail_blocks():
    conds = {"all": [
        {"field": "new_emotion",      "op": "in",  "value": ["anger"]},
        {"field": "stage_turn_count", "op": "gte", "value": 5},
    ]}
    assert match_rule(conds, {"new_emotion": "anger", "stage_turn_count": 4}) is False


def test_match_rule_any_at_least_one():
    conds = {"any": [
        {"field": "new_emotion",       "op": "eq", "value": "anger"},
        {"field": "emotion_degraded",  "op": "eq", "value": True},
    ]}
    assert match_rule(conds, {"new_emotion": "calm", "emotion_degraded": True}) is True
    assert match_rule(conds, {"new_emotion": "calm", "emotion_degraded": False}) is False


def test_match_rule_all_and_any_combined():
    conds = {
        "all": [{"field": "stage_equals_dummy_just_for_test", "op": "eq", "value": "x"}],
        "any": [{"field": "new_emotion", "op": "eq", "value": "anger"}],
    }
    # all 里的字段非法 -> False (短路, 即便 any 满足也无效)
    assert match_rule(conds, {"new_emotion": "anger"}) is False


def test_match_rule_empty_never_fires():
    # 防误配置:空 conditions 不应永远命中
    assert match_rule({}, {"new_emotion": "anger"}) is False
    assert match_rule({"all": [], "any": []}, {"new_emotion": "anger"}) is False


# ---------------------------------------------------------------------------
# build_context_post_llm: 衍生字段
# ---------------------------------------------------------------------------
def test_post_ctx_stage_flipped_true():
    ctx = build_context_post_llm(
        prev_stage="stage_2_solution", prev_emotion="calm",
        new_total_turn=10, new_stage_turn=1,
        llm_decision={"next_stage": "stage_4_push", "customer_emotion": "joy",
                      "extracted_tags": ["高意向"], "detected_language": "zh-CN"},
    )
    assert ctx["stage_flipped"] is True
    assert ctx["stage_flipped_to"] == "stage_4_push"
    assert ctx["new_emotion"] == "joy"
    assert ctx["extracted_tags"] == ["高意向"]


def test_post_ctx_stage_not_flipped():
    ctx = build_context_post_llm(
        prev_stage="stage_2_solution", prev_emotion="calm",
        new_total_turn=10, new_stage_turn=5,
        llm_decision={"next_stage": "stage_2_solution", "customer_emotion": "calm"},
    )
    assert ctx["stage_flipped"] is False
    assert ctx["stage_flipped_to"] is None


@pytest.mark.parametrize("prev, new, expected", [
    ("calm",        "anger",       True),   # 非负 -> 负
    ("joy",         "impatience",  True),
    ("excited",     "hesitation",  True),
    ("anger",       "hesitation",  False),  # 已经是负 -> 负, 不算"恶化"
    ("impatience",  "anger",       False),
    ("calm",        "joy",         False),
    ("calm",        "calm",        False),
])
def test_post_ctx_emotion_degraded(prev, new, expected):
    ctx = build_context_post_llm(
        prev_stage="x", prev_emotion=prev,
        new_total_turn=1, new_stage_turn=1,
        llm_decision={"customer_emotion": new, "next_stage": "x"},
    )
    assert ctx["emotion_degraded"] is expected


def test_pre_ctx_no_llm_signals():
    ctx = build_context_pre_llm(
        cur_stage="stage_1_icebreak", cur_emotion="impatience",
        total_turn=7, stage_turn=3,
    )
    # 还没有 LLM 输出, 这些字段必须是空 / False
    assert ctx["extracted_tags"] == []
    assert ctx["stage_flipped"] is False
    assert ctx["emotion_degraded"] is False
    assert ctx["new_emotion"] == "impatience"


# ---------------------------------------------------------------------------
# 综合场景: "防暴走机制" - 客户情绪恶化 + 总回合 >= 2 触发
# ---------------------------------------------------------------------------
def test_rule_anti_meltdown_fires():
    conds = {"all": [
        {"field": "emotion_degraded",  "op": "eq",  "value": True},
        {"field": "total_turn_count",  "op": "gte", "value": 2},
    ]}
    ctx = build_context_post_llm(
        prev_stage="stage_2_solution", prev_emotion="calm",
        new_total_turn=3, new_stage_turn=2,
        llm_decision={"next_stage": "stage_2_solution", "customer_emotion": "anger"},
    )
    assert match_rule(conds, ctx) is True


def test_rule_anti_meltdown_doesnt_fire_on_first_turn():
    conds = {"all": [
        {"field": "emotion_degraded",  "op": "eq",  "value": True},
        {"field": "total_turn_count",  "op": "gte", "value": 2},
    ]}
    ctx = build_context_post_llm(
        prev_stage="stage_2_solution", prev_emotion="calm",
        new_total_turn=1, new_stage_turn=1,
        llm_decision={"next_stage": "stage_2_solution", "customer_emotion": "anger"},
    )
    # emotion_degraded=True 但 total_turn_count<2, 不命中
    assert match_rule(conds, ctx) is False


# ---------------------------------------------------------------------------
# metadata_for_frontend: 与白名单同步
# ---------------------------------------------------------------------------
def test_metadata_lists_match_whitelist():
    md = metadata_for_frontend()
    # metadata 现在每项是 {value, label_zh, label_en, hint?},取 value 集合比对白名单
    field_values   = {x["value"] for x in md["fields"]}
    op_values      = {x["value"] for x in md["ops"]}
    emotion_values = {x["value"] for x in md["emotions"]}
    action_values  = {x["value"] for x in md["action_types"]}
    assert field_values == ALLOWED_FIELDS
    assert op_values == ALLOWED_OPS
    assert NEGATIVE_EMOTIONS.issubset(emotion_values)
    # 核心动作必须存在
    for a in ("transfer_to_human", "webhook", "send_payment_link", "system_notify"):
        assert a in action_values
    # 新增的 stages_global 与字段类别提示
    assert "stages_global" in md and len(md["stages_global"]) >= 6
    assert "stage_like_fields" in md
    assert "new_stage" in md["stage_like_fields"]
