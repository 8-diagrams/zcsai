-- 002_session_stage_default.sql
-- 把 sessions.current_stage 的列默认值改成 stage_1_icebreak
-- 仅影响后续 INSERT 未显式赋值的情况；已存在的行不会被回填。
ALTER TABLE sessions
    MODIFY COLUMN current_stage VARCHAR(50) DEFAULT 'stage_1_icebreak'
    COMMENT '该访客当前处于SOP的哪个阶段';
