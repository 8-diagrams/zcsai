-- 004_session_emotion_and_takeover.sql
-- P1: 为 sessions 增加情绪/回合数/接管审计字段；为 messages 增加发出时的 stage/emotion 快照及 LLM 决策原始 JSON。
-- 现有行兼容：messages 的快照列允许 NULL；sessions 计数器/情绪/接管列有 NOT NULL DEFAULT，老行自动获得默认值。
--
-- 回合数语义:
--   total_turn_count: 每处理一条访客消息 +1 (无论 LLM 成功与否)
--   stage_turn_count: stage 跃迁时重置为 1；否则 +1。当前这一轮已经发生在新 stage，所以从 1 起算。
--
-- 情绪枚举: calm / joy / excited / hesitation / impatience / anger (严格枚举，LLM 不允许新造词)

-- 1) sessions: 情绪 + 计数器 + 接管审计
ALTER TABLE sessions
    ADD COLUMN current_emotion ENUM('calm','joy','excited','hesitation','impatience','anger')
        NOT NULL DEFAULT 'calm' COMMENT '访客最近识别到的情绪' AFTER current_stage,
    ADD COLUMN total_turn_count INT NOT NULL DEFAULT 0 COMMENT '总对话回合数',
    ADD COLUMN stage_turn_count INT NOT NULL DEFAULT 0 COMMENT '当前 stage 停留回合数',
    ADD COLUMN is_human_takeover TINYINT(1) NOT NULL DEFAULT 0 COMMENT '是否已被人工接管；True 时不再调 LLM',
    ADD COLUMN human_takeover_at TIMESTAMP NULL DEFAULT NULL COMMENT '接管发生时间',
    ADD COLUMN human_takeover_by VARCHAR(50) NULL DEFAULT NULL COMMENT '接管的员工ID',
    ADD INDEX idx_sessions_takeover (is_human_takeover);

-- 2) messages: 发出时的 stage / emotion 快照 + LLM 决策 raw
ALTER TABLE messages
    ADD COLUMN stage_at_send VARCHAR(50) NULL COMMENT '消息发出时所处 stage' AFTER content,
    ADD COLUMN emotion_at_send ENUM('calm','joy','excited','hesitation','impatience','anger')
        NULL COMMENT '消息发出时识别到的访客情绪',
    ADD COLUMN llm_decision_raw JSON NULL COMMENT '仅 employee 行：LLM 完整决策快照',
    ADD INDEX idx_messages_stage (stage_at_send);
