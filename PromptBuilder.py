


def build_prompt(activity_name, current_stage_name, current_stage_desc):
    ret = """【{activity.name}】任务。
    当前该访客处于SOP的【{session.current_stage}】阶段。
    
    请根据访客的最新回复，决定你要对他说的话，以及他接下来应该进入哪个阶段。
    你必须严格输出以下 JSON 格式：
    {{
        "reply_content": "你回复给访客的具体话术",
        "next_stage": "stage_1_icebreak | stage_2_solution | stage_3_objection | stage_4_push | stage_5_sleep | stage_6_aftersales",
        "stage_reason": "你判断流转到该阶段的理由（例如：客户询问了价格，说明进入了方案期）",
        "extracted_tags": ["高意向", "在意价格"] 
    }}
    """
    return ret 
    