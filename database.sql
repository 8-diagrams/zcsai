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
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY idx_active_session (org_id, platform_type, visitor_uid, status), -- 防止同一访客出现多个活跃会话
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
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE,
    INDEX idx_org_group (org_id, group_id) -- 核心查询索引：管理后台按公司/组别看聊天记录秒出
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
    -- 例如: ["破冰", "探求", "方案", "逼单", "售后"]
    stages_config JSON NULL COMMENT '阶段定义字典', 
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (org_id) REFERENCES organizations(id) ON DELETE CASCADE,
    FOREIGN KEY (group_id) REFERENCES groups(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 2. 修改 Sessions 表，增加 activity 绑定和当前阶段状态
ALTER TABLE sessions 
ADD COLUMN activity_id VARCHAR(50) NULL COMMENT '当前绑定的活动剧本' AFTER group_id,
ADD COLUMN current_stage VARCHAR(50) DEFAULT '破冰' COMMENT '该访客当前处于SOP的哪个阶段' AFTER visitor_uid,
ADD CONSTRAINT fk_session_activity FOREIGN KEY (activity_id) REFERENCES activities(id) ON DELETE SET NULL;

-- 3. 修改 Messages 表，增加 activity_id 冗余，方便极速出报表
ALTER TABLE messages 
ADD COLUMN activity_id VARCHAR(50) NULL COMMENT '冗余: 活动ID' AFTER group_id,
ADD INDEX idx_org_activity (org_id, activity_id); -- 性能起飞：按公司和活动查聊天记录




-- 1. 插入一条双十一活动剧本（请注意 stages_config 字段里的 JSON 规则）
INSERT INTO activities (id, org_id, group_id, name, stages_config) 
VALUES (
    'act_001', 'org_123', 'grp_123_sales', '双十一自动逼单剧本', 
    '{"破冰": "你是客服，现在只需热情打招呼，不要推销。", "探求": "问对方预算是多少，目前有什么痛点。", "逼单": "告诉对方现在下单马上发货，错过等一年！"}'
);

-- 2. 初始化一个会话 (Session)，并强制将其绑定到刚才的活动上，阶段设定为 "探求"
INSERT INTO sessions (id, org_id, group_id, employee_id, platform_type, visitor_uid, activity_id, current_stage) 
VALUES ('sess_001', 'org_123', 'grp_123_sales', 'emp_ai_001', 'web_demo', 'uid_999', 'act_001', '探求');

