-- 012_knowledge_base_raw_text.sql
-- 保存知识库用户输入原文。
--
-- 用途:
--   1) 创建/追加/替换知识库时, 在 MySQL 中保留用户输入的完整原文。
--   2) 分享复制 activity 时, 可优先基于 raw_text 重新切片、重新 embedding,
--      避免只依赖旧 Qdrant collection 中的 points。
--
-- 兼容:
--   现有知识库行 raw_text 为 NULL; 后续编辑/替换后会逐步补齐。

ALTER TABLE knowledge_bases
    ADD COLUMN raw_text TEXT NULL COMMENT '用户输入的知识库原文' AFTER usage_guideline;
