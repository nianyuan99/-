-- 提示词模板表 (阶段8: 提示词模板库)
create table if not exists prompt_template
(
    id              varchar(36) primary key comment '模板唯一标识',
    userId          bigint                             null comment '用户ID(预设模板为NULL)',
    name            varchar(100)                       not null comment '模板名称',
    description     text                               null comment '模板描述',
    strategy        varchar(50)                        not null comment '策略类型: direct/cot/role_play/few_shot',
    content         text                               not null comment '模板内容(支持占位符)',
    variables       json                               null comment '变量列表(JSON数组)',
    category        varchar(50)                        null comment '分类',
    isPreset        tinyint      default 0             not null comment '是否为预设模板(1-预设 0-自定义)',
    usageCount      int          default 0             not null comment '使用次数',
    isActive        tinyint      default 1             not null comment '是否启用(1-启用 0-禁用)',
    createTime      datetime     default CURRENT_TIMESTAMP not null comment '创建时间',
    updateTime      datetime     default CURRENT_TIMESTAMP not null on update CURRENT_TIMESTAMP comment '更新时间',
    isDelete        tinyint      default 0             not null comment '逻辑删除',
    index idx_user (userId, isDelete),
    index idx_strategy (strategy, isDelete),
    index idx_preset (isPreset, isDelete),
    index idx_category (category, isDelete)
) comment '提示词模板表' collate = utf8mb4_unicode_ci;

-- 初始化预设模板数据
INSERT INTO prompt_template (id, userId, name, description, strategy, content, variables, category, isPreset, usageCount, isActive, isDelete) VALUES
('preset-direct-001', NULL, '直接提问模板', '适用于简单直接的问答场景', 'direct', '{question}', '["question"]', '通用', 1, 0, 1, 0),
('preset-cot-001', NULL, 'CoT思维链模板', '引导AI进行逐步思考', 'cot', '请逐步思考以下问题，并给出详细的分析过程：

问题：{question}

请按照以下步骤思考：
1. 理解问题
2. 分析关键信息
3. 推理过程
4. 得出结论', '["question"]', '通用', 1, 0, 1, 0),
('preset-role-001', NULL, '角色扮演模板', '让AI扮演特定角色', 'role_play', '你是一位{role}，请以{role}的身份回答以下问题：

问题：{question}

请以专业、准确的方式回答。', '["role", "question"]', '通用', 1, 0, 1, 0),
('preset-fewshot-001', NULL, 'Few-shot示例模板', '通过示例引导AI理解任务', 'few_shot', '以下是几个示例：

示例1：
输入：{example1_input}
输出：{example1_output}

示例2：
输入：{example2_input}
输出：{example2_output}

现在请根据以上示例，回答以下问题：
输入：{question}
输出：', '["example1_input", "example1_output", "example2_input", "example2_output", "question"]', '通用', 1, 0, 1, 0)
ON DUPLICATE KEY UPDATE
    name = VALUES(name),
    description = VALUES(description),
    strategy = VALUES(strategy),
    content = VALUES(content),
    variables = VALUES(variables),
    category = VALUES(category),
    isPreset = VALUES(isPreset),
    isActive = VALUES(isActive),
    isDelete = VALUES(isDelete);
