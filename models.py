from sqlalchemy import Column, String, Boolean, Integer, Text, DateTime, JSON, Enum as SQLEnum, Numeric
from sqlalchemy import ForeignKey
from database import Base

from datetime import datetime
import enum

# ========================================================
# 客户情绪枚举 (LLM-facing English snake_case)
# 严格规约：不允许 LLM 自创新值；UtilLLM 会做校验
# ========================================================
class CustomerEmotion(str, enum.Enum):
    CALM = "calm"               # 平静，正常沟通
    JOY = "joy"                 # 喜悦/满意/赞同/表达感谢
    EXCITED = "excited"         # 兴奋/高情绪/对方案显著心动
    HESITATION = "hesitation"   # 犹豫/在意价格/对比竞品
    IMPATIENCE = "impatience"   # 急躁/催促/失耐心
    ANGER = "anger"             # 愤怒/投诉/爆粗口


# ========================================================
# 0. 多租户主体 (Referrer / Organization / Group / Employee)
# 与 database.sql 中表结构 1:1 对齐
# ========================================================
class Referrer(Base):
    __tablename__ = "referrers"

    id = Column(String(50), primary_key=True)
    name = Column(String(100), nullable=False, comment="代理商名称")
    commission_rate = Column(Numeric(5, 2), default=0.00, comment="分佣比例")
    created_at = Column(DateTime, default=datetime.utcnow)


class Organization(Base):
    __tablename__ = "organizations"

    id = Column(String(50), primary_key=True)
    referrer_id = Column(String(50), ForeignKey("referrers.id", ondelete="SET NULL"), nullable=True)
    name = Column(String(100), nullable=False, comment="商户公司名称")
    api_key = Column(String(100), unique=True, nullable=False, comment="对外接口通信Key")
    plan_type = Column(SQLEnum("free", "pro", "enterprise"), default="free")
    created_at = Column(DateTime, default=datetime.utcnow)


class Group(Base):
    __tablename__ = "groups"

    id = Column(String(50), primary_key=True)
    org_id = Column(String(50), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(100), nullable=False, comment="组别名称")
    created_at = Column(DateTime, default=datetime.utcnow)


class Employee(Base):
    __tablename__ = "employees"

    id = Column(String(50), primary_key=True)
    org_id = Column(String(50), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    group_id = Column(String(50), ForeignKey("groups.id", ondelete="SET NULL"), nullable=True)
    name = Column(String(100), nullable=False, comment="客服/AI 花名")
    is_ai = Column(Boolean, default=False)
    status = Column(SQLEnum("online", "offline", "busy"), default="offline")
    created_at = Column(DateTime, default=datetime.utcnow)


# ========================================================
# 0.1 登录账号表 (User)
# ========================================================
class User(Base):
    __tablename__ = "users"

    id = Column(String(50), primary_key=True)
    email = Column(String(120), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    display_name = Column(String(100), nullable=True)
    role = Column(
        SQLEnum("platform_admin", "org_admin", "group_admin", "agent"),
        nullable=False,
    )
    org_id = Column(String(50), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True)
    group_id = Column(String(50), ForeignKey("groups.id", ondelete="SET NULL"), nullable=True, index=True)
    employee_id = Column(String(50), ForeignKey("employees.id", ondelete="SET NULL"), nullable=True, index=True)
    is_active = Column(Boolean, default=True)
    last_login_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


# ========================================================
# 1. 会话记录表 (SessionRecord)
# 记录当前访客正在处于哪个活动的哪个阶段
# ========================================================
class SessionRecord(Base):
    __tablename__ = "sessions"

    id = Column(String(50), primary_key=True, comment="会话ID")

    org_id = Column(String(50), index=True, comment="所属公司ID")
    group_id = Column(String(50), index=True, nullable=True, comment="所属团队ID")
    activity_id = Column(String(50), index=True, nullable=True, comment="当前参与的活动ID")
    employee_id = Column(String(50), index=True, nullable=True, comment="当前接待的坐席ID")

    platform_type = Column(String(20), nullable=True, comment="来源渠道: whatsapp/telegram/wechat/web_demo")
    visitor_uid = Column(String(100), nullable=True, comment="访客外部唯一ID")
    status = Column(
        SQLEnum("active", "closed", "transferred"),
        default="active",
        comment="会话生命周期",
    )

    current_stage = Column(String(50), default="stage_1_icebreak", comment="当前SOP所处的阶段")

    # === P1 新增: 情绪 + 多维回合数 + 接管审计 ===
    current_emotion = Column(
            SQLEnum(CustomerEmotion, values_callable=lambda obj: [e.value for e in obj]),
            default="calm",  # 直接使用字符串默认值
            nullable=False,
            comment="访客最近一次被识别到的情绪",
        )
    total_turn_count = Column(Integer, default=0, nullable=False, comment="总对话回合数 (以访客发一条计一回合)")
    stage_turn_count = Column(Integer, default=0, nullable=False, comment="在当前 stage 停留的回合数")
    is_human_takeover = Column(Boolean, default=False, nullable=False, index=True, comment="是否已被人工接管；True 时不再调 LLM")
    human_takeover_at = Column(DateTime, nullable=True, comment="接管发生的时间")
    human_takeover_by = Column(String(50), nullable=True, comment="接管的 employee_id")

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

# ========================================================
# 2. 聊天明细表 (Message)
# 用于持久化保存 AI 和访客的具体聊天内容流水
# ========================================================
class Message(Base):
    __tablename__ = "messages"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(50), index=True, comment="绑定的会话ID")
    
    # 冗余租户字段，方便后期做数据报表统计
    org_id = Column(String(50), index=True)
    group_id = Column(String(50), index=True, nullable=True)
    activity_id = Column(String(50), index=True, nullable=True)
    
    sender_type = Column(String(20), comment="发送方类型: visitor / employee / system")
    sender_id = Column(String(100), nullable=True, comment="发送者实体ID")
    content = Column(Text, comment="聊天内容")

    # === P1 新增: 这条消息发出时 session 的状态快照 ===
    stage_at_send = Column(String(50), nullable=True, index=True, comment="发出时 session 所处 stage")
    emotion_at_send = Column(
            SQLEnum(CustomerEmotion, values_callable=lambda obj: [e.value for e in obj]),
            default="calm",  # 直接使用字符串默认值
            nullable=False,
            comment="访客最近一次被识别到的情绪",
        )
    llm_decision_raw = Column(JSON, nullable=True, comment="仅 sender_type=employee 时有值: LLM 当轮完整返回")
    # === P2 新增: 该消息由哪条规则触发(NULL = LLM/人工/系统兜底所发) ===
    fired_by_rule_id = Column(String(50), nullable=True, index=True, comment="规则触发本条消息的 rule_id")

    created_at = Column(DateTime, default=datetime.utcnow)

# ========================================================
# 3. 活动/剧本表 (Activity)
# ========================================================
class Activity(Base):
    __tablename__ = "activities"
        
    id = Column(String(50), primary_key=True)
    
    # 带有外键约束的租户字段
    org_id = Column(String(50), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, comment="归属公司ID")
    group_id = Column(String(50), ForeignKey("groups.id", ondelete="CASCADE"), nullable=False, comment="执行此活动的组别ID")
    
    name = Column(String(100), nullable=False, comment="活动名称")
    welcome_message = Column(Text, nullable=True, comment="进线欢迎语")
    closing_message = Column(Text, nullable=True, comment="结束语")
    
    # 完美契合你 SQL 里的 json DEFAULT NULL
    stages_config = Column(Text, nullable=True, comment="阶段定义字典")
    
    # 👇 新增的全局基础指引字段
    global_guideline = Column(Text, nullable=True, comment="全局基础指引 (AI 底层系统提示词)")
    
    created_at = Column(DateTime, default=datetime.utcnow)

# ========================================================
# 4. 知识库主表 (KnowledgeBase)
# ========================================================
class KnowledgeBase(Base):
    __tablename__ = "knowledge_bases"
    
    id = Column(String(50), primary_key=True)
    name = Column(String(100), comment="知识库名称")
    
    # 核心：使用指引/元提示词
    usage_guideline = Column(Text, nullable=True, comment="该库的话术语气要求、适用场景等")
    
    # SaaS 租户隔离
    org_id = Column(String(50), index=True, comment="所属公司ID")
    group_id = Column(String(50), nullable=True, index=True, comment="所属团队ID")
    is_shared_to_groups = Column(Boolean, default=False, comment="是否共享给所有子团队")
    
    # 向量数据库映射
    vector_collection_name = Column(String(100), comment="对应 Qdrant/Milvus 中的集合名")

# ========================================================
# 5. 活动与知识库的挂载映射表 (ActivityKBMount)
# ========================================================
class ActivityKBMount(Base):
    __tablename__ = "activity_kb_mounts"
    
    # 联合主键
    activity_id = Column(String(50), primary_key=True, comment="活动剧本ID")
    kb_id = Column(String(50), primary_key=True, comment="知识库ID")
    
    # 挂载属性
    priority = Column(Integer, default=0, comment="挂载权重(数值越大越优先)")
    mount_guideline = Column(Text, nullable=True, comment="当该活动挂载此库时特有的AI提示词")


# ========================================================
# P2: 规则引擎相关表
# ========================================================
class ActivityEventRule(Base):
    """事件规则:运营人员可在前端节点画布配置,后端在 LLM 前/后评估并触发动作。"""
    __tablename__ = "activity_event_rules"

    id = Column(String(50), primary_key=True)
    org_id = Column(String(50), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    # NULL = 该 org 下所有 activity 共用; 否则只对指定 activity 生效
    activity_id = Column(String(50), ForeignKey("activities.id", ondelete="CASCADE"), nullable=True)
    name = Column(String(100), nullable=False)
    # 大 = 先评估; short_circuit 决定命中后是否短路
    priority = Column(Integer, default=0, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    # pre_llm: LLM 调用前评估(转人工拦截/关键词阻断)
    # post_llm: LLM 调用后评估(发素材/支付链接/webhook 等增强类)
    phase = Column(
        SQLEnum("pre_llm", "post_llm"),
        default="post_llm",
        nullable=False,
    )
    # DSL: {"all": [{field,op,value}, ...], "any": [...]}
    conditions = Column(JSON, nullable=False)
    # 有序 action 数组, 见 RuleEngine.py 支持的 action.type
    actions = Column(JSON, nullable=False)
    # once_per_session | once_per_stage | every_n_turns:N | always
    fire_policy = Column(String(30), default="once_per_session", nullable=False)
    short_circuit = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class SessionRuleFire(Base):
    """规则触发审计:防"复读机"(once_per_session/once_per_stage 查询源) + 后台复盘"""
    __tablename__ = "session_rule_fires"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(50), index=True, nullable=False)
    rule_id = Column(String(50), index=True, nullable=False)
    fired_at = Column(DateTime, default=datetime.utcnow)
    fired_at_stage = Column(String(50), nullable=True)
    fired_at_total_turn = Column(Integer, nullable=True)
    fired_at_stage_turn = Column(Integer, nullable=True)
    # 实际执行了哪些 action + 各 action 的结果(成功/失败/原因)
    actions_executed = Column(JSON, nullable=True)


class AgentNotification(Base):
    """员工通知 inbox:转人工邀请、系统提醒等"""
    __tablename__ = "agent_notifications"

    id = Column(Integer, primary_key=True, autoincrement=True)
    org_id = Column(String(50), nullable=False)
    group_id = Column(String(50), nullable=True)
    # NULL = 整组广播; 否则定向到指定员工
    target_employee_id = Column(String(50), nullable=True)
    session_id = Column(String(50), nullable=True)
    rule_id = Column(String(50), nullable=True)
    level = Column(SQLEnum("info", "warning", "urgent"), default="info")
    title = Column(String(200), nullable=False)
    body = Column(Text, nullable=True)
    is_read = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class WebhookDeadLetter(Base):
    """规则派发 webhook 失败后的死信留底,供后台手工/定时重试"""
    __tablename__ = "webhook_dead_letters"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(50), nullable=True)
    rule_id = Column(String(50), nullable=True)
    url = Column(String(500), nullable=False)
    method = Column(String(10), nullable=False)
    payload = Column(JSON, nullable=True)
    last_error = Column(Text, nullable=True)
    attempts = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)