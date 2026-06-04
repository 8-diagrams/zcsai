# UtilLLM.py
import json
import asyncio
from loguru import logger

# 严格规约的客户情绪枚举值 (与 models.CustomerEmotion 必须一致)
ALLOWED_EMOTIONS = {"calm", "joy", "excited", "hesitation", "impatience", "anger"}

async def generate_ai_reply_with_retry(
    session_id,
    llm_client,
    model_name: str,
    visitor_msg: str,
    # --- 状态机与活动上下文 ---
    activity_name: str,
    current_stage: str,
    allowed_next_stages: list,
    global_guideline: str,
    stage_guideline: str,
    # --- RAG与记忆上下文 ---
    kb_context: str,
    kb_instructions: str,
    memory_context: str,
    # --- 素材库 (可选): [{id, kind, title, description}, ...] ---
    material_catalog: list = None,
    # --- 配置 ---
    max_retries: int = 3
) -> dict:
    """
    高度内聚的大模型调度核心：内部组装 Prompt + 质检 + 重试 + 兜底
    """
    # ==========================================
    # 1. 内部动态组装 System Prompt
    # ==========================================
    # UtilLLM.py 核心修改片段
    system_prompt_dict = {
        "role_definition": f"你是一个顶级的金牌销售，当前正在执行【{activity_name}】任务。请严格遵守以下全局红线：{global_guideline}",
        
        # 🆕 核心新增：强力语言跟随指令
        "language_requirement": "【极其重要】：请自动检测访客最新消息的语言种类。你最终生成的 `reply_content` 必须严格使用与访客完全相同的语言进行回复（例如：访客用英文，你的回复也必须全是英文；访客用繁体中文，你必须用繁体中文）。",
        
        "current_task_guideline": stage_guideline,
        "kb_special_instructions": kb_instructions,
        "kb_standard_context": kb_context,
        "customer_memory_profile": memory_context,
        "state_machine_context": f"当前访客处于漏斗的【{current_stage}】阶段。根据访客刚才的回复，如果你认为需要推进阶段，你只能从以下允许的阶段中选择：{allowed_next_stages}。如果你认为目前火候未到，请保持阶段为 {current_stage}。",

        "output_requirements": "你必须且只能返回一个合法的 JSON 对象，严禁输出任何多余的解释文本或 Markdown 标记。其中 customer_emotion 字段具有致命的业务约束，严禁生成不在允许列表中的任何词汇！",
        "output_schema_definition": {
            "reply_content": "你想对访客说的话（必须使用与访客相同的语言！）",
            "next_stage": "你裁判得出的下一步阶段ID（必须是上述允许的合法值）",
            "stage_reason": "你判断流转（或保持）该阶段的简短内部理由，用于系统复盘",
            "extracted_tags": ["高意向", "在意价格", "同行比价"],
            # 🆕 核心新增：让大模型顺手把语种报告给后端
            "detected_language": "你检测到的访客输入语言（如 'zh-CN', 'en-US', 'es', 'ja' 等）",
            # 🚨 严格枚举：基于访客最新消息的用词和语气判断；不允许新造词。
            "customer_emotion": "必须且只能是以下英文枚举值之一: [calm, joy, excited, hesitation, impatience, anger]",
            # 🆕 素材选择：从下方 material_catalog 中按需选 0~N 个素材的 id 一起发给访客；不需要就给空数组。严禁编造不在清单里的 id。
            "selected_material_ids": []
        }
    }

    # 🆕 素材清单注入: 仅当本活动有可用素材时, 把 id/类型/标题/描述给 LLM 作为选材依据。
    if material_catalog:
        system_prompt_dict["material_catalog"] = {
            "instruction": "以下是当前可发送给访客的素材库。如果有助于推进对话(如展示产品图/演示视频/标准说明), 在 selected_material_ids 里填入对应素材的 id; 不合适就别选。只能选下列 id, 不要编造。",
            "items": material_catalog,
        }

    system_prompt_json = json.dumps(system_prompt_dict, ensure_ascii=False, indent=2)
    
    
    messages = [
        {"role": "system", "content": system_prompt_json},
        {"role": "user", "content": visitor_msg}
    ]

    # ==========================================
    # 2. 呼叫、质检与重试循环
    # ==========================================
    for attempt in range(1, max_retries + 1):
        try:
            logger.debug(f"Session {session_id} LLM 🤖 正在发起第 {attempt}/{max_retries} 次 LLM 呼叫...")
            logger.debug(f"Session {session_id} LLMs call {model_name}, [[{json.dumps(messages, indent=2)}]] ")
            response = await llm_client.chat.completions.create(
                model=model_name,
                messages=messages,
                max_tokens=2000,
                temperature=0.7,
                response_format={"type": "json_object"} # 强制 JSON 模式
            )
            
            raw_content = response.choices[0].message.content
            ai_decision = json.loads(raw_content)
            
            # --- 业务质检 ---
            if "reply_content" not in ai_decision or "next_stage" not in ai_decision:
                raise ValueError("大模型少生成了必备字段")

            judged_stage = ai_decision["next_stage"]
            valid_stages = allowed_next_stages + [current_stage]
            if judged_stage not in valid_stages:
                raise ValueError(f"非法状态越权: 试图跳转到未授权的 {judged_stage}")

            # 情绪严格枚举校验 (LLM 不允许自创新词)
            judged_emotion = ai_decision.get("customer_emotion")
            if judged_emotion not in ALLOWED_EMOTIONS:
                raise ValueError(f"非法情绪: {judged_emotion!r} 不在允许枚举 {ALLOWED_EMOTIONS} 内")

            if not ai_decision["reply_content"].strip():
                raise ValueError("生成了空白回复")

            # selected_material_ids 容错: 缺省/非 list 一律归一为 [] (不因此 raise, 保持鲁棒)
            sel = ai_decision.get("selected_material_ids")
            if not isinstance(sel, list):
                ai_decision["selected_material_ids"] = []

            logger.success(f"Session {session_id} LLM ✅ LLM 质检通过 (耗费 {attempt} 次尝试)")
            return ai_decision

        except json.JSONDecodeError:
            logger.warning(f"Session {session_id} LLM ⚠️ 第 {attempt} 次尝试失败: 输出非合法 JSON 格式")
        except ValueError as ve:
            logger.warning(f"Session {session_id} LLM ⚠️ 第 {attempt} 次尝试失败: 业务质检未通过 ({ve})")
        except Exception as e:
            logger.error(f"Session {session_id} LLM ❌ 第 {attempt} 次尝试发生异常: {e}")
            await asyncio.sleep(1)

    # ==========================================
    # 3. 终极安全兜底 (Fallback)
    # ==========================================
    logger.error(f"Session {session_id} LLM 🚨 已达到最大重试次数 ({max_retries})，触发安全兜底！")
    return {
        "reply_content": "抱歉，刚刚系统网络走神了，能麻烦您再说一遍吗？",
        "next_stage": current_stage,
        "stage_reason": "大模型多次生成异常，触发系统安全拦截",
        "extracted_tags": [],
        "detected_language": "unknown",
        "customer_emotion": "calm",  # 安全默认值：calm 不会触发任何情绪类规则
    }