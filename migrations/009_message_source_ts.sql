-- 009_message_source_ts.sql
-- 下游平台(如 fb_business)通过 WS action=report_history 回传历史聊天记录时，需要的两列：
--   1) source_ts:     源平台原始消息时间戳(DOUBLE, epoch 秒带小数)，用于排序/展示。
--                     注: 下游每次全量回传会重打时间戳，故 source_ts 不作去重键。
--   2) source_msg_id: 源平台消息稳定唯一ID(预留)。下游若回传 message_id，历史去重优先用它
--                     (最鲁棒，不惧乱序/增量上报)；缺省 NULL 时回退到 (位置+方向+文本) 顺序指纹去重。
--
-- 实时进线消息此两列为 NULL。现有行兼容：列允许 NULL，老行自动为 NULL。

ALTER TABLE messages
    ADD COLUMN source_ts DOUBLE NULL COMMENT '源平台消息时间戳(epoch秒); 历史回传排序用' AFTER fired_by_rule_id,
    ADD COLUMN source_msg_id VARCHAR(128) NULL COMMENT '源平台消息唯一ID(预留); 历史回传去重优先键' AFTER source_ts,
    ADD INDEX idx_messages_source_ts (source_ts),
    ADD INDEX idx_messages_source_msg_id (source_msg_id);
