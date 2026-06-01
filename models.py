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
        SQLEnum(CustomerEmotion),
        default=CustomerEmotion.CALM,
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
    emotion_at_send = Column(SQLEnum(CustomerEmotion), nullable=True, comment="发出时识别到的访客情绪")
    llm_decision_raw = Column(JSON, nullable=True, comment="仅 sender_type=employee 时有值: LLM 当轮完整返回")

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