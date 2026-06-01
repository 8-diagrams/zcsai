-- 005_stage_keys_refactor.sql
-- P1 衍生: 把 SOP stage 命名升级到新的 6 阶段:
--   stage_1_icebreak  (破冰与探需) -- 旧 stage_1_icebreak + stage_2_explore 合并
--   stage_2_solution  (方案与价值传递) -- 旧 stage_3_solution 改名
--   stage_3_objection (异议处理) -- 新增 (无旧映射)
--   stage_4_push      (逼单转化) -- 旧 stage_4_close / stage_4_closing 改名
--   stage_5_sleep     (沉睡/沉默) -- 新增 (无旧映射)
--   stage_6_aftersales(售后) -- 旧 stage_5_aftersales 改名
--
-- 旧 -> 新映射:
--   stage_2_explore   -> stage_1_icebreak   (合并：丢弃 explore 内容，保留 icebreak)
--   stage_3_solution  -> stage_2_solution   (改名)
--   stage_4_close     -> stage_4_push       (改名)
--   stage_4_closing   -> stage_4_push       (改名: stages.json 旧默认值)
--   stage_5_aftersales-> stage_6_aftersales (改名)
--
-- 幂等：脚本对每条记录都用 WHERE 守卫，再跑一次不会重复改写。

-- ============================================================
-- 1) sessions.current_stage 单值映射
-- ============================================================
UPDATE sessions SET current_stage = CASE current_stage
    WHEN 'stage_2_explore'    THEN 'stage_1_icebreak'
    WHEN 'stage_3_solution'   THEN 'stage_2_solution'
    WHEN 'stage_4_close'      THEN 'stage_4_push'
    WHEN 'stage_4_closing'    THEN 'stage_4_push'
    WHEN 'stage_5_aftersales' THEN 'stage_6_aftersales'
    ELSE current_stage
END
WHERE current_stage IN ('stage_2_explore', 'stage_3_solution', 'stage_4_close', 'stage_4_closing', 'stage_5_aftersales');

-- ============================================================
-- 2) activities.stages_config (JSON 键重命名)
-- ============================================================
-- stage_2_explore -> stage_1_icebreak (合并：保留 stage_1_icebreak 已有内容)
--   • 若 stage_1_icebreak 已存在 → 直接删掉 stage_2_explore (保留 icebreak)
--   • 若 stage_1_icebreak 不存在 → 把 stage_2_explore 的值搬到 stage_1_icebreak
UPDATE activities
SET stages_config = JSON_REMOVE(stages_config, '$."stage_2_explore"')
WHERE JSON_CONTAINS_PATH(stages_config, 'one', '$."stage_2_explore"')
  AND JSON_CONTAINS_PATH(stages_config, 'one', '$."stage_1_icebreak"');

UPDATE activities
SET stages_config = JSON_SET(
        JSON_REMOVE(stages_config, '$."stage_2_explore"'),
        '$.stage_1_icebreak', JSON_EXTRACT(stages_config, '$."stage_2_explore"')
    )
WHERE JSON_CONTAINS_PATH(stages_config, 'one', '$."stage_2_explore"')
  AND NOT JSON_CONTAINS_PATH(stages_config, 'one', '$."stage_1_icebreak"');

-- stage_3_solution -> stage_2_solution
UPDATE activities
SET stages_config = JSON_REMOVE(stages_config, '$."stage_3_solution"')
WHERE JSON_CONTAINS_PATH(stages_config, 'one', '$."stage_3_solution"')
  AND JSON_CONTAINS_PATH(stages_config, 'one', '$."stage_2_solution"');

UPDATE activities
SET stages_config = JSON_SET(
        JSON_REMOVE(stages_config, '$."stage_3_solution"'),
        '$.stage_2_solution', JSON_EXTRACT(stages_config, '$."stage_3_solution"')
    )
WHERE JSON_CONTAINS_PATH(stages_config, 'one', '$."stage_3_solution"')
  AND NOT JSON_CONTAINS_PATH(stages_config, 'one', '$."stage_2_solution"');

-- stage_4_close -> stage_4_push
UPDATE activities
SET stages_config = JSON_REMOVE(stages_config, '$."stage_4_close"')
WHERE JSON_CONTAINS_PATH(stages_config, 'one', '$."stage_4_close"')
  AND JSON_CONTAINS_PATH(stages_config, 'one', '$."stage_4_push"');

UPDATE activities
SET stages_config = JSON_SET(
        JSON_REMOVE(stages_config, '$."stage_4_close"'),
        '$.stage_4_push', JSON_EXTRACT(stages_config, '$."stage_4_close"')
    )
WHERE JSON_CONTAINS_PATH(stages_config, 'one', '$."stage_4_close"')
  AND NOT JSON_CONTAINS_PATH(stages_config, 'one', '$."stage_4_push"');

-- stage_4_closing -> stage_4_push
UPDATE activities
SET stages_config = JSON_REMOVE(stages_config, '$."stage_4_closing"')
WHERE JSON_CONTAINS_PATH(stages_config, 'one', '$."stage_4_closing"')
  AND JSON_CONTAINS_PATH(stages_config, 'one', '$."stage_4_push"');

UPDATE activities
SET stages_config = JSON_SET(
        JSON_REMOVE(stages_config, '$."stage_4_closing"'),
        '$.stage_4_push', JSON_EXTRACT(stages_config, '$."stage_4_closing"')
    )
WHERE JSON_CONTAINS_PATH(stages_config, 'one', '$."stage_4_closing"')
  AND NOT JSON_CONTAINS_PATH(stages_config, 'one', '$."stage_4_push"');

-- stage_5_aftersales -> stage_6_aftersales
UPDATE activities
SET stages_config = JSON_REMOVE(stages_config, '$."stage_5_aftersales"')
WHERE JSON_CONTAINS_PATH(stages_config, 'one', '$."stage_5_aftersales"')
  AND JSON_CONTAINS_PATH(stages_config, 'one', '$."stage_6_aftersales"');

UPDATE activities
SET stages_config = JSON_SET(
        JSON_REMOVE(stages_config, '$."stage_5_aftersales"'),
        '$.stage_6_aftersales', JSON_EXTRACT(stages_config, '$."stage_5_aftersales"')
    )
WHERE JSON_CONTAINS_PATH(stages_config, 'one', '$."stage_5_aftersales"')
  AND NOT JSON_CONTAINS_PATH(stages_config, 'one', '$."stage_6_aftersales"');

-- ============================================================
-- 3) activities.stages_config 内部 next_possible_stages 数组里的旧名也要换掉
-- ============================================================
-- 用 CAST + REPLACE 串行清洗一遍：把内嵌的旧 stage key 字符串值替换为新名。
-- 这里同时覆盖键名和数组值（数组值出现在 "stage_2_solution" 等加双引号的位置）。
-- 注意：上面的 JSON_REMOVE/JSON_SET 只重命名顶层 key；这里负责清洗深层引用。
UPDATE activities
SET stages_config = CAST(
    REPLACE(
        REPLACE(
            REPLACE(
                REPLACE(
                    REPLACE(
                        CAST(stages_config AS CHAR),
                        '"stage_2_explore"',    '"stage_1_icebreak"'
                    ),
                    '"stage_3_solution"',   '"stage_2_solution"'
                ),
                '"stage_4_closing"',    '"stage_4_push"'
            ),
            '"stage_4_close"',      '"stage_4_push"'
        ),
        '"stage_5_aftersales"', '"stage_6_aftersales"'
    ) AS JSON
);
