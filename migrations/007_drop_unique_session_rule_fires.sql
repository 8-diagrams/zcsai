-- 007_drop_unique_session_rule_fires.sql
-- 修复: every_n_turns / once_per_stage 政策下, 第二次及以后的命中行被唯一约束 + INSERT IGNORE 静默丢弃,
-- 导致 _can_fire_by_policy 用 MAX(fired_at_total_turn) 永远拿到第一次的回合数, 后续逻辑全错。
-- 现在 once_per_session 已改为应用层 SELECT 兜底, 不再需要 DB 唯一约束。

ALTER TABLE session_rule_fires DROP INDEX uq_session_rule_once;
