-- 008_visitor_profile.sql
-- 为 sessions / messages 增加访客 profile 属性，便于后续主动联系访客。
--
-- sessions: 已有 platform_type(所属平台) 与 visitor_uid(平台ID)，此处仅补充 昵称 / email。
-- messages: 增加访客 profile 快照(昵称/email/平台/平台ID)，与现有 stage_at_send / emotion_at_send 快照风格一致，
--           便于单查一条消息时无需 JOIN sessions 即可拿到当时的访客联系方式。
--
-- 现有行兼容：全部新列允许 NULL，老行自动为 NULL，无需回填。

-- 1) sessions: 访客昵称 + email
ALTER TABLE sessions
    ADD COLUMN visitor_nickname VARCHAR(100) NULL COMMENT '访客昵称' AFTER visitor_uid,
    ADD COLUMN visitor_email VARCHAR(120) NULL COMMENT '访客邮箱' AFTER visitor_nickname;

-- 2) messages: 发出时的访客 profile 快照
ALTER TABLE messages
    ADD COLUMN visitor_nickname_at_send VARCHAR(100) NULL COMMENT '发出时访客昵称' AFTER llm_decision_raw,
    ADD COLUMN visitor_email_at_send VARCHAR(120) NULL COMMENT '发出时访客邮箱' AFTER visitor_nickname_at_send,
    ADD COLUMN visitor_platform_at_send VARCHAR(20) NULL COMMENT '发出时访客所属平台' AFTER visitor_email_at_send,
    ADD COLUMN visitor_platform_id_at_send VARCHAR(100) NULL COMMENT '发出时访客平台ID' AFTER visitor_platform_at_send;
