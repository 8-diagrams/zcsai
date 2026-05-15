from sqlalchemy import Column, String, Boolean, Integer, Text, DateTime, JSON
from sqlalchemy import ForeignKey
from database import Base

from datetime import datetime
# ========================================================
# 1. 会话记录表 (SessionRecord)
# 记录当前访客正在处于哪个活动的哪个阶段
# ========================================================
class SessionRecord(Base):
    __tablename__ = "sessions"
    
    id = Column(String(50), primary_key=True, comment="会话ID")
    
    # 租户与活动路由
    org_id = Column(String(50), index=True, comment="所属公司ID")
    group_id = Column(String(50), index=True, nullable=True, comment="所属团队ID")
    activity_id = Column(String(50), index=True, nullable=True, comment="当前参与的活动ID")
    
    # 漏斗状态追踪
    current_stage = Column(String(50), default="默认阶段", comment="当前SOP所处的阶段")
    created_at = Column(DateTime, default=datetime.utcnow)

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
    
    sender_type = Column(String(20), comment="发送方类型: visitor / employee(AI)")
    content = Column(Text, comment="聊天内容")
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