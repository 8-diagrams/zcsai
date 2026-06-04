-- 010_platform_type_to_varchar.sql
-- sessions.platform_type 原为 ENUM('whatsapp','telegram','wechat','web_demo')，
-- 无法容纳下游平台回传的新渠道值(如 fb_business)，导致历史导入报错 1265 Data truncated。
-- 改为自由字符串字段，便于接入任意平台来源，不再受枚举约束。
--
-- 注: 列上有 UNIQUE KEY idx_active_session (org_id, platform_type, visitor_uid, status)，
--     改类型不影响该索引；VARCHAR(50) 足够容纳平台标识。
-- 兼容: 原 ENUM 值是合法字符串，转换后原数据原样保留。

ALTER TABLE sessions
    MODIFY COLUMN platform_type VARCHAR(50) NOT NULL COMMENT '来源渠道(所属平台); 自由字符串, 如 whatsapp/telegram/wechat/web_demo/fb_business';

-- 同步: messages 的平台快照列原为 VARCHAR(20)，与 sessions.platform_type 对齐放宽到 50，避免未来更长平台名被截断。
ALTER TABLE messages
    MODIFY COLUMN visitor_platform_at_send VARCHAR(50) NULL COMMENT '发出时访客所属平台';
