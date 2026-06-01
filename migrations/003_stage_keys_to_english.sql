-- 003_stage_keys_to_english.sql
-- 将 sessions.current_stage 和 activities.stages_config 里的阶段 key
-- 从中文统一改为英文 snake_case，便于 LLM 直接消费。
--
-- 映射:
--   破冰 -> stage_1_icebreak
--   探求 -> stage_2_explore
--   方案 -> stage_3_solution
--   逼单 -> stage_4_close
--   售后 -> stage_5_aftersales
--   默认阶段 -> stage_1_icebreak   (兼容旧默认值)
--
-- 该脚本幂等：再次执行不会重复改写（找不到中文 key 时所有 REPLACE 都是 no-op）。

-- 1) sessions.current_stage
UPDATE sessions SET current_stage = CASE current_stage
    WHEN '破冰'     THEN 'stage_1_icebreak'
    WHEN '探求'     THEN 'stage_2_explore'
    WHEN '方案'     THEN 'stage_3_solution'
    WHEN '逼单'     THEN 'stage_4_close'
    WHEN '售后'     THEN 'stage_5_aftersales'
    WHEN '默认阶段' THEN 'stage_1_icebreak'
    ELSE current_stage
END
WHERE current_stage IN ('破冰', '探求', '方案', '逼单', '售后', '默认阶段');

-- 2) activities.stages_config (JSON)
--   逐 key 重命名：JSON_REMOVE + JSON_SET，只对存在该 key 的行操作，避免误伤。
UPDATE activities
SET stages_config = JSON_SET(
        JSON_REMOVE(stages_config, '$."破冰"'),
        '$.stage_1_icebreak', JSON_EXTRACT(stages_config, '$."破冰"')
    )
WHERE JSON_CONTAINS_PATH(stages_config, 'one', '$."破冰"');

UPDATE activities
SET stages_config = JSON_SET(
        JSON_REMOVE(stages_config, '$."探求"'),
        '$.stage_2_explore', JSON_EXTRACT(stages_config, '$."探求"')
    )
WHERE JSON_CONTAINS_PATH(stages_config, 'one', '$."探求"');

UPDATE activities
SET stages_config = JSON_SET(
        JSON_REMOVE(stages_config, '$."方案"'),
        '$.stage_3_solution', JSON_EXTRACT(stages_config, '$."方案"')
    )
WHERE JSON_CONTAINS_PATH(stages_config, 'one', '$."方案"');

UPDATE activities
SET stages_config = JSON_SET(
        JSON_REMOVE(stages_config, '$."逼单"'),
        '$.stage_4_close', JSON_EXTRACT(stages_config, '$."逼单"')
    )
WHERE JSON_CONTAINS_PATH(stages_config, 'one', '$."逼单"');

UPDATE activities
SET stages_config = JSON_SET(
        JSON_REMOVE(stages_config, '$."售后"'),
        '$.stage_5_aftersales', JSON_EXTRACT(stages_config, '$."售后"')
    )
WHERE JSON_CONTAINS_PATH(stages_config, 'one', '$."售后"');
