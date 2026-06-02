-- 006_rules_engine_and_takeover_audit.sql
-- P2: 规则引擎 + 转人工通知 + Webhook 死信 + Messages 标记
--
-- 设计要点:
--   1. activity_event_rules 独立表 (不污染 activities.stages_config)；activity_id NULL = 该 org 全部 activity 共用。
--   2. session_rule_fires 兼任 once_per_session 的唯一约束兜底，也是 once_per_stage / every_n_turns 的查询源。
--   3. agent_notifications 给员工 inbox 看 (转人工通知 / 系统级提醒)。
--   4. webhook_dead_letters 在 RuleEngine 派发 webhook action 失败后留底，方便后台手工/定时重试。
--   5. messages 新增 fired_by_rule_id 标识"这条消息是规则发的而不是 LLM 生成的"。

-- 1) 规则定义表
CREATE TABLE activity_event_rules (
    id VARCHAR(50) PRIMARY KEY,
    org_id VARCHAR(50) NOT NULL,
    activity_id VARCHAR(50) NULL COMMENT 'NULL = 该 org 所有 activity 适用',
    name VARCHAR(100) NOT NULL,
    priority INT NOT NULL DEFAULT 0 COMMENT '大 = 先评估；short_circuit 控制是否短路',
    is_active TINYINT(1) NOT NULL DEFAULT 1,
    phase ENUM('pre_llm','post_llm') NOT NULL DEFAULT 'post_llm' COMMENT 'pre_llm: LLM 前拦截; post_llm: LLM 后增强',
    conditions JSON NOT NULL COMMENT 'DSL {all:[], any:[]}',
    actions JSON NOT NULL COMMENT '有序 action 数组',
    fire_policy VARCHAR(30) NOT NULL DEFAULT 'once_per_session' COMMENT 'once_per_session | once_per_stage | every_n_turns:N | always',
    short_circuit TINYINT(1) NOT NULL DEFAULT 0 COMMENT '命中后是否停止评估更低优先级规则',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_org_act_active (org_id, activity_id, is_active),
    FOREIGN KEY (org_id) REFERENCES organizations(id) ON DELETE CASCADE,
    FOREIGN KEY (activity_id) REFERENCES activities(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 2) 规则触发审计表 (防"复读机" + 后台复盘)
CREATE TABLE session_rule_fires (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    session_id VARCHAR(50) NOT NULL,
    rule_id VARCHAR(50) NOT NULL,
    fired_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    fired_at_stage VARCHAR(50) NULL,
    fired_at_total_turn INT NULL,
    fired_at_stage_turn INT NULL,
    actions_executed JSON NULL COMMENT '实际执行的 action + 各 action 结果',
    UNIQUE KEY uq_session_rule_once (session_id, rule_id) COMMENT 'once_per_session 用此约束兜底',
    INDEX idx_session (session_id),
    INDEX idx_rule (rule_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
-- 注意: once_per_session 用 INSERT IGNORE 利用唯一约束；
--      once_per_stage / every_n_turns 走 SELECT MAX(fired_at_total_turn) WHERE session_id=? AND rule_id=?

-- 3) 员工通知表 (Agent Inbox)
CREATE TABLE agent_notifications (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    org_id VARCHAR(50) NOT NULL,
    group_id VARCHAR(50) NULL,
    target_employee_id VARCHAR(50) NULL COMMENT 'NULL = 整组广播',
    session_id VARCHAR(50) NULL,
    rule_id VARCHAR(50) NULL,
    level ENUM('info','warning','urgent') DEFAULT 'info',
    title VARCHAR(200) NOT NULL,
    body TEXT NULL,
    is_read TINYINT(1) NOT NULL DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_target (org_id, target_employee_id, is_read),
    INDEX idx_group (org_id, group_id, is_read)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 4) Webhook 死信表 (规则派发 webhook 失败时留底)
CREATE TABLE webhook_dead_letters (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    session_id VARCHAR(50) NULL,
    rule_id VARCHAR(50) NULL,
    url VARCHAR(500) NOT NULL,
    method VARCHAR(10) NOT NULL,
    payload JSON NULL,
    last_error TEXT NULL,
    attempts INT DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_session (session_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 5) messages 表加 fired_by_rule_id 标识 "这条消息由规则触发"
ALTER TABLE messages
    ADD COLUMN fired_by_rule_id VARCHAR(50) NULL COMMENT '该消息由哪条规则触发(NULL = LLM 或人工发的)' AFTER llm_decision_raw,
    ADD INDEX idx_fired_rule (fired_by_rule_id);
