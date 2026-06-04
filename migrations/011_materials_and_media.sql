-- 011_materials_and_media.sql
-- 富媒体消息 + 素材库
--
-- 1) messages 新增 3 列, 让消息支持图片/视频/链接:
--    - content_type: text/image/video/link, NOT NULL DEFAULT 'text' (历史行自动为 'text')
--    - media_url:    图片/视频/链接 URL
--    - media_caption: 媒体说明文字
--    现有行兼容: content_type 有默认值, media_* 允许 NULL。
--
-- 2) materials 表: 镜像 knowledge_bases 的多租户 + 共享语义, LLM 与人工均可引用。
--    activity_id NULL = org 级通用素材; is_shared_to_groups = 共享给同 org 其他组。

ALTER TABLE messages
    ADD COLUMN content_type VARCHAR(20) NOT NULL DEFAULT 'text' COMMENT 'text/image/video/link' AFTER content,
    ADD COLUMN media_url VARCHAR(1000) NULL COMMENT '图片/视频/链接 URL' AFTER content_type,
    ADD COLUMN media_caption VARCHAR(500) NULL COMMENT '媒体说明文字' AFTER media_url;

CREATE TABLE materials (
    id VARCHAR(50) PRIMARY KEY COMMENT '素材ID mat_xxxx',
    org_id VARCHAR(50) NOT NULL COMMENT '所属公司ID',
    group_id VARCHAR(50) NULL COMMENT '所属团队ID',
    is_shared_to_groups BOOLEAN NOT NULL DEFAULT FALSE COMMENT '是否共享给同 org 其他组',
    activity_id VARCHAR(50) NULL COMMENT 'NULL = org 级通用素材',
    kind VARCHAR(20) NOT NULL COMMENT 'image/video/text',
    title VARCHAR(200) NULL COMMENT '素材标题',
    description TEXT NULL COMMENT '给 LLM 看的选材依据',
    media_url VARCHAR(1000) NULL COMMENT 'image/video 的 URL',
    text_content TEXT NULL COMMENT 'kind=text 时的文本内容',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_materials_org (org_id),
    INDEX idx_materials_group (group_id),
    INDEX idx_materials_activity (activity_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
