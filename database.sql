-- =========================================================
-- SaaS AI Agent Hub 核心数据库初始化脚本 (终极版)
-- =========================================================

-- 1. 创建数据库并设置字符集为 utf8mb4 (完美支持全球语言和 Emoji 表情)
CREATE DATABASE IF NOT EXISTS saas_agent_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE saas_agent_db;

-- =========================================================
-- 表结构定义
-- =========================================================

-- 1. 代理商表 (Referrers) - 顶层分销渠道
CREATE TABLE referrers (
    id VARCHAR(50) PRIMARY KEY,
    name VARCHAR(100) NOT NULL COMMENT '代理商名称',
    commission_rate DECIMAL(5,2) DEFAULT 0.00 COMMENT '分佣比例 (如 0.20 代表 20%)',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 2. 公司/租户表 (Organizations) - SaaS 隔离的绝对核心
CREATE TABLE organizations (
    id VARCHAR(50) PRIMARY KEY,
    referrer_id VARCHAR(50) NULL COMMENT '归属代理商ID',
    name VARCHAR(100) NOT NULL COMMENT '商户公司名称',
    api_key VARCHAR(100) UNIQUE NOT NULL COMMENT '对外接口通信Key',
    plan_type ENUM('free', 'pro', 'enterprise') DEFAULT 'free' COMMENT '订阅套餐类型',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (referrer_id) REFERENCES referrers(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 3. 项目组表 (Groups) - 商户内部的分组 (如: 售前组、售后组)
CREATE TABLE groups (
    id VARCHAR(50) PRIMARY KEY,
    org_id VARCHAR(50) NOT NULL COMMENT '归属公司ID',
    name VARCHAR(100) NOT NULL COMMENT '组别名称',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (org_id) REFERENCES organizations(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 4. 坐席表 (Employees) - 包含真人客服与 AI
CREATE TABLE employees (
    id VARCHAR(50) PRIMARY KEY,
    org_id VARCHAR(50) NOT NULL COMMENT '归属公司ID',
    group_id VARCHAR(50) NULL COMMENT '归属项目组ID',
    name VARCHAR(100) NOT NULL COMMENT '客服/AI花名',
    is_ai BOOLEAN DEFAULT FALSE COMMENT '是否为AI接管',
    status ENUM('online', 'offline', 'busy') DEFAULT 'offline' COMMENT '当前接客状态',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (org_id) REFERENCES organizations(id) ON DELETE CASCADE,
    FOREIGN KEY (group_id) REFERENCES groups(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 5. 会话表 (Sessions) - 访客进线的状态机
CREATE TABLE sessions (
    id VARCHAR(50) PRIMARY KEY,
    org_id VARCHAR(50) NOT NULL COMMENT '归属公司ID',
    group_id VARCHAR(50) NULL COMMENT '当前分配的组别',
    employee_id VARCHAR(50) NULL COMMENT '当前接待的客服ID(可以是AI)',
    platform_type ENUM('whatsapp', 'telegram', 'wechat', 'web_demo') NOT NULL COMMENT '来源渠道',
    visitor_uid VARCHAR(100) NOT NULL COMMENT '访客在外部平台的唯一ID',
    status ENUM('active', 'closed', 'transferred') DEFAULT 'active' COMMENT '会话生命周期',
    -- === P1 新增: 情绪 + 多维回合数 + 接管审计 ===
    current_emotion ENUM('calm','joy','excited','hesitation','impatience','anger')
        NOT NULL DEFAULT 'calm' COMMENT '访客最近识别到的情绪',
    total_turn_count INT NOT NULL DEFAULT 0 COMMENT '总对话回合数',
    stage_turn_count INT NOT NULL DEFAULT 0 COMMENT '当前 stage 停留回合数',
    is_human_takeover TINYINT(1) NOT NULL DEFAULT 0 COMMENT '是否已被人工接管；True 时不再调 LLM',
    human_takeover_at TIMESTAMP NULL DEFAULT NULL COMMENT '接管发生时间',
    human_takeover_by VARCHAR(50) NULL DEFAULT NULL COMMENT '接管的员工ID',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY idx_active_session (org_id, platform_type, visitor_uid, status), -- 防止同一访客出现多个活跃会话
    INDEX idx_sessions_takeover (is_human_takeover),
    FOREIGN KEY (org_id) REFERENCES organizations(id) ON DELETE CASCADE,
    FOREIGN KEY (group_id) REFERENCES groups(id) ON DELETE SET NULL,
    FOREIGN KEY (employee_id) REFERENCES employees(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 6. 消息记录表 (Messages) - 聊天记录核心表
CREATE TABLE messages (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    session_id VARCHAR(50) NOT NULL,
    org_id VARCHAR(50) NOT NULL COMMENT '冗余:公司ID',
    group_id VARCHAR(50) NULL COMMENT '冗余:组别ID (大幅提升按组查询性能)',
    sender_type ENUM('visitor', 'employee', 'system') NOT NULL COMMENT '发送者身份',
    sender_id VARCHAR(100) NULL COMMENT '发送者实体ID (访客UID或客服ID)',
    content TEXT NOT NULL COMMENT '消息文本内容',
    -- === P1 新增: 消息发出时 session 的状态快照 ===
    stage_at_send VARCHAR(50) NULL COMMENT '消息发出时所处 stage',
    emotion_at_send ENUM('calm','joy','excited','hesitation','impatience','anger')
        NULL COMMENT '消息发出时识别到的访客情绪',
    llm_decision_raw JSON NULL COMMENT '仅 employee 行：LLM 完整决策快照',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE,
    INDEX idx_org_group (org_id, group_id), -- 核心查询索引：管理后台按公司/组别看聊天记录秒出
    INDEX idx_messages_stage (stage_at_send)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- =========================================================
-- 注入测试数据 (仅供跑通 Demo 使用)
-- =========================================================

-- 1. 创建一个测试公司
INSERT INTO organizations (id, name, api_key, plan_type) 
VALUES ('org_123', '出海电商A公司', 'sk_test_abc123', 'pro');

-- 2. 为该公司创建两个组
INSERT INTO groups (id, org_id, name) VALUES ('grp_123_sales', 'org_123', '售前冲锋组');
INSERT INTO groups (id, org_id, name) VALUES ('grp_123_support', 'org_123', '售后安抚组');

-- 3. 创建测试坐席：一个 AI 销售，一个 真人 售后
INSERT INTO employees (id, org_id, group_id, name, is_ai, status) 
VALUES ('emp_ai_001', 'org_123', 'grp_123_sales', '金牌销售-小A (AI)', TRUE, 'online');

INSERT INTO employees (id, org_id, group_id, name, is_ai, status) 
VALUES ('emp_human_001', 'org_123', 'grp_123_support', '人工客服-老李', FALSE, 'offline');


-- 1. 创建 Activity (活动/场景剧本) 表
CREATE TABLE activities (
    id VARCHAR(50) PRIMARY KEY,
    org_id VARCHAR(50) NOT NULL COMMENT '归属公司ID',
    group_id VARCHAR(50) NOT NULL COMMENT '执行此活动的组别ID',
    name VARCHAR(100) NOT NULL COMMENT '活动名称 (如: 双十一引流跟进)',
    welcome_message TEXT COMMENT '进线欢迎语',
    closing_message TEXT COMMENT '结束语',
    -- 使用 JSON 存储该活动包含的阶段 SOP 规则，方便以后随时增减
    -- 阶段 key 统一英文 snake_case，主要给 LLM 看。当前 6 阶段 SOP：
    --   stage_1_icebreak  (破冰与探需)
    --   stage_2_solution  (方案与价值传递)
    --   stage_3_objection (异议处理)
    --   stage_4_push      (逼单转化)
    --   stage_5_sleep     (沉睡/沉默)
    --   stage_6_aftersales(售后)
    stages_config JSON NULL COMMENT '阶段定义字典',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (org_id) REFERENCES organizations(id) ON DELETE CASCADE,
    FOREIGN KEY (group_id) REFERENCES groups(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 2. 修改 Sessions 表，增加 activity 绑定和当前阶段状态
ALTER TABLE sessions 
ADD COLUMN activity_id VARCHAR(50) NULL COMMENT '当前绑定的活动剧本' AFTER group_id,
ADD COLUMN current_stage VARCHAR(50) DEFAULT 'stage_1_icebreak' COMMENT '该访客当前处于SOP的哪个阶段' AFTER visitor_uid,
ADD CONSTRAINT fk_session_activity FOREIGN KEY (activity_id) REFERENCES activities(id) ON DELETE SET NULL;

-- 3. 修改 Messages 表，增加 activity_id 冗余，方便极速出报表
ALTER TABLE messages 
ADD COLUMN activity_id VARCHAR(50) NULL COMMENT '冗余: 活动ID' AFTER group_id,
ADD INDEX idx_org_activity (org_id, activity_id); -- 性能起飞：按公司和活动查聊天记录




-- 1. 插入一条双十一活动剧本 (stages_config 与 stages.json 的 6 阶段定义对齐)
INSERT INTO activities (id, org_id, group_id, name, stages_config)
VALUES (
    'act_001', 'org_123', 'grp_123_sales', '双十一自动逼单剧本',
    JSON_OBJECT(
        'stage_1_icebreak',  JSON_OBJECT(
            'name', '破冰与探需',
            'ai_guideline', '你必须表现出极高的热情。主动抛出选择题或引导性问题，探寻客户的具体需求（如行业、痛点、预算或期望功能）。在客户明确需求前，绝对不要急于长篇大论地推销产品或给出准确报价。',
            'next_possible_stages', JSON_ARRAY('stage_2_solution', 'stage_3_objection', 'stage_5_sleep')
        ),
        'stage_2_solution',  JSON_OBJECT(
            'name', '方案与价值传递',
            'ai_guideline', '你现在需要扮演资深顾问。严格依据知识库中检索到的事实，给出能精准解决客户需求的方案，强调差异化亮点，并在结尾引导下一步动作。',
            'next_possible_stages', JSON_ARRAY('stage_3_objection', 'stage_4_push', 'stage_5_sleep')
        ),
        'stage_3_objection', JSON_OBJECT(
            'name', '异议处理',
            'ai_guideline', '先安抚情绪、表示共情；然后精准调用退换货保障/权威认证/售后承诺等政策给出专业且诚恳的解答。',
            'next_possible_stages', JSON_ARRAY('stage_2_solution', 'stage_4_push', 'stage_5_sleep')
        ),
        'stage_4_push',      JSON_OBJECT(
            'name', '逼单转化',
            'ai_guideline', '促单黄金时机！抛出限时优惠/库存紧张/当天专属福利等稀缺性话术，制造紧迫感推动客户成单。',
            'next_possible_stages', JSON_ARRAY('stage_6_aftersales', 'stage_3_objection', 'stage_5_sleep')
        ),
        'stage_5_sleep',     JSON_OBJECT(
            'name', '沉睡/沉默',
            'ai_guideline', '执行异步唤醒任务，结合客户此前关注点生成一条自然、不唐突的跟进话术。',
            'next_possible_stages', JSON_ARRAY('stage_1_icebreak', 'stage_2_solution')
        ),
        'stage_6_aftersales', JSON_OBJECT(
            'name', '售后',
            'ai_guideline', '把自己定位为贴心的客户经理：先确认订单细节与使用说明，再在合适时机铺垫复购或增值服务，避免让客户感觉刚成单又被推销。',
            'next_possible_stages', JSON_ARRAY('stage_5_sleep', 'stage_1_icebreak')
        )
    )
);

-- 2. 初始化一个会话 (Session)，绑定到上述活动，stage 从默认 stage_1_icebreak 起步
INSERT INTO sessions (id, org_id, group_id, employee_id, platform_type, visitor_uid, activity_id, current_stage)
VALUES ('sess_001', 'org_123', 'grp_123_sales', 'emp_ai_001', 'web_demo', 'uid_999', 'act_001', 'stage_1_icebreak');


-- =========================================================
-- 用户/账号表 (Users) - 登录主体；支持四种角色
-- platform_admin: 平台超管 (无 org_id)
-- org_admin:      公司管理员 (有 org_id)
-- group_admin:    组管理员 (有 org_id + group_id)
-- agent:          组员/坐席 (有 org_id + group_id + employee_id)
-- =========================================================
CREATE TABLE users (
    id VARCHAR(50) PRIMARY KEY,
    email VARCHAR(120) UNIQUE NOT NULL COMMENT '登录邮箱',
    password_hash VARCHAR(255) NOT NULL COMMENT 'bcrypt 哈希',
    display_name VARCHAR(100) COMMENT '昵称/真实姓名',
    role ENUM('platform_admin','org_admin','group_admin','agent') NOT NULL COMMENT '角色',
    org_id VARCHAR(50) NULL COMMENT '所属公司',
    group_id VARCHAR(50) NULL COMMENT '所属组',
    employee_id VARCHAR(50) NULL COMMENT '关联坐席ID',
    is_active BOOLEAN DEFAULT TRUE COMMENT '是否启用',
    last_login_at TIMESTAMP NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (org_id) REFERENCES organizations(id) ON DELETE CASCADE,
    FOREIGN KEY (group_id) REFERENCES groups(id) ON DELETE SET NULL,
    FOREIGN KEY (employee_id) REFERENCES employees(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 初始化平台超管账号 (登录: admin@local / 密码: admin123)
-- bcrypt hash 由后端启动脚本 bootstrap_root.py 自动写入
INSERT INTO users (id, email, password_hash, display_name, role)
VALUES (
    'usr_root',
    'admin@local',
    '$2b$12$0NIkbbB5B8SDPmsE4tQq7.rzkYG2LfoWgb4sU5qVOaWHcAIiyEOJe',
    '平台超管',
    'platform_admin'
);

-- 给测试公司 org_123 配一个公司管理员 (boss@org123.com / admin123)
INSERT INTO users (id, email, password_hash, display_name, role, org_id)
VALUES (
    'usr_org_admin_123',
    'boss@org123.com',
    '$2b$12$0NIkbbB5B8SDPmsE4tQq7.rzkYG2LfoWgb4sU5qVOaWHcAIiyEOJe',
    'A 公司老板',
    'org_admin',
    'org_123'
);

-- 给 grp_123_sales 配一个组管理员 (lead@org123.com / admin123)
INSERT INTO users (id, email, password_hash, display_name, role, org_id, group_id)
VALUES (
    'usr_group_admin_sales',
    'lead@org123.com',
    '$2b$12$0NIkbbB5B8SDPmsE4tQq7.rzkYG2LfoWgb4sU5qVOaWHcAIiyEOJe',
    '售前组长',
    'group_admin',
    'org_123',
    'grp_123_sales'
);

-- 把人工坐席 emp_human_001 关联到一个 agent 账号 (laoli@org123.com / admin123)
INSERT INTO users (id, email, password_hash, display_name, role, org_id, group_id, employee_id)
VALUES (
    'usr_agent_laoli',
    'laoli@org123.com',
    '$2b$12$0NIkbbB5B8SDPmsE4tQq7.rzkYG2LfoWgb4sU5qVOaWHcAIiyEOJe',
    '人工客服-老李',
    'agent',
    'org_123',
    'grp_123_support',
    'emp_human_001'
);

-- =========================================================
-- P2: 规则引擎 + 转人工通知 + Webhook 死信
-- 与 migrations/006_rules_engine_and_takeover_audit.sql 保持一致
-- =========================================================

-- 1) 规则定义表
CREATE TABLE activity_event_rules (
    id VARCHAR(50) PRIMARY KEY,
    org_id VARCHAR(50) NOT NULL,
    activity_id VARCHAR(50) NULL COMMENT 'NULL = 该 org 所有 activity 适用',
    name VARCHAR(100) NOT NULL,
    priority INT NOT NULL DEFAULT 0,
    is_active TINYINT(1) NOT NULL DEFAULT 1,
    phase ENUM('pre_llm','post_llm') NOT NULL DEFAULT 'post_llm',
    conditions JSON NOT NULL,
    actions JSON NOT NULL,
    fire_policy VARCHAR(30) NOT NULL DEFAULT 'once_per_session',
    short_circuit TINYINT(1) NOT NULL DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_org_act_active (org_id, activity_id, is_active),
    FOREIGN KEY (org_id) REFERENCES organizations(id) ON DELETE CASCADE,
    FOREIGN KEY (activity_id) REFERENCES activities(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 2) 规则触发审计表
CREATE TABLE session_rule_fires (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    session_id VARCHAR(50) NOT NULL,
    rule_id VARCHAR(50) NOT NULL,
    fired_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    fired_at_stage VARCHAR(50) NULL,
    fired_at_total_turn INT NULL,
    fired_at_stage_turn INT NULL,
    actions_executed JSON NULL,
    UNIQUE KEY uq_session_rule_once (session_id, rule_id),
    INDEX idx_session (session_id),
    INDEX idx_rule (rule_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 3) 员工通知表
CREATE TABLE agent_notifications (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    org_id VARCHAR(50) NOT NULL,
    group_id VARCHAR(50) NULL,
    target_employee_id VARCHAR(50) NULL,
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

-- 4) Webhook 死信表
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

-- 5) messages 表加 fired_by_rule_id
ALTER TABLE messages
    ADD COLUMN fired_by_rule_id VARCHAR(50) NULL COMMENT '该消息由哪条规则触发' AFTER llm_decision_raw,
    ADD INDEX idx_fired_rule (fired_by_rule_id);


