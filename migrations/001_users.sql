-- 001_users.sql — 给已部署的 saas_agent_db 补 users 表 + 4 个默认账号
-- 密码统一是 admin123 (bcrypt rounds=12)
-- 用法: mysql -u root -p saas_agent_db < migrations/001_users.sql

SET FOREIGN_KEY_CHECKS = 0;

CREATE TABLE IF NOT EXISTS users (
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
    FOREIGN KEY (group_id) REFERENCES `groups`(id) ON DELETE SET NULL,
    FOREIGN KEY (employee_id) REFERENCES employees(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 平台超管: admin@local / admin123
INSERT INTO users (id, email, password_hash, display_name, role)
VALUES ('usr_root', 'admin@local',
        '$2b$12$0NIkbbB5B8SDPmsE4tQq7.rzkYG2LfoWgb4sU5qVOaWHcAIiyEOJe',
        '平台超管', 'platform_admin')
ON DUPLICATE KEY UPDATE password_hash = VALUES(password_hash);

-- 公司管理员 (依赖 org_123 已存在): boss@org123.com / admin123
INSERT INTO users (id, email, password_hash, display_name, role, org_id)
VALUES ('usr_org_admin_123', 'boss@org123.com',
        '$2b$12$0NIkbbB5B8SDPmsE4tQq7.rzkYG2LfoWgb4sU5qVOaWHcAIiyEOJe',
        'A 公司老板', 'org_admin', 'org_123')
ON DUPLICATE KEY UPDATE password_hash = VALUES(password_hash);

-- 组管理员 (依赖 grp_123_sales 已存在): lead@org123.com / admin123
INSERT INTO users (id, email, password_hash, display_name, role, org_id, group_id)
VALUES ('usr_group_admin_sales', 'lead@org123.com',
        '$2b$12$0NIkbbB5B8SDPmsE4tQq7.rzkYG2LfoWgb4sU5qVOaWHcAIiyEOJe',
        '售前组长', 'group_admin', 'org_123', 'grp_123_sales')
ON DUPLICATE KEY UPDATE password_hash = VALUES(password_hash);

-- 坐席 (依赖 grp_123_support / emp_human_001 已存在): laoli@org123.com / admin123
INSERT INTO users (id, email, password_hash, display_name, role, org_id, group_id, employee_id)
VALUES ('usr_agent_laoli', 'laoli@org123.com',
        '$2b$12$0NIkbbB5B8SDPmsE4tQq7.rzkYG2LfoWgb4sU5qVOaWHcAIiyEOJe',
        '人工客服-老李', 'agent', 'org_123', 'grp_123_support', 'emp_human_001')
ON DUPLICATE KEY UPDATE password_hash = VALUES(password_hash);

SET FOREIGN_KEY_CHECKS = 1;
