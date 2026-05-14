
from loguru import logger

def ProcMem(m0msg, log=None):
    log.info(f"PROCMEM {m0msg}")
    if "results" in m0msg:
        relevant_memories = m0msg['results']
    else:
        relevant_memories = m0msg 
    memory_context = ""
    valid_mems = []
    if isinstance(relevant_memories, list):
        for m in relevant_memories:
            if isinstance(m, dict) and 'memory' in m:
                valid_mems.append(m['memory']) # 标准情况：列表套字典
            elif isinstance(m, str):
                valid_mems.append(m) # 异常情况：列表套纯字符串
    elif isinstance(relevant_memories, str):
        valid_mems.append(relevant_memories) # 异常情况：直接返回了纯字符串
    
    # 组装最终的记忆上下文给大模型
    if valid_mems:
        memory_context = "\n".join(valid_mems)
        log.success(f"💡 唤醒记忆成功，提取到 {len(valid_mems)} 条核心画像")
    else:
        log.debug("💡 本次对话未触发历史记忆 (新客户或无相关记录)")
    return memory_context