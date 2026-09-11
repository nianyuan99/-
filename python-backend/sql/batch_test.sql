-- =============================================================================
-- AI 大模型评测平台 - 场景化批量测试相关库表
-- 与 Java 版共用同一套库表结构，全部使用 create table if not exists，可重复执行
-- =============================================================================

-- 测试场景表
create table if not exists scene
(
    id          varchar(36) primary key comment '场景唯一标识',
    userId      bigint                             null comment '创建用户ID(预设场景为NULL)',
    name        varchar(100)                       not null comment '场景名称',
    description text                               null comment '场景描述',
    category    varchar(50)                        null comment '分类:编程/数学/文案等',
    isPreset    tinyint      default 0             not null comment '是否为预设场景(1-预设 0-自定义)',
    isActive    tinyint      default 1             not null comment '是否启用(1-启用 0-禁用)',
    createTime  datetime     default CURRENT_TIMESTAMP not null comment '创建时间',
    updateTime  datetime     default CURRENT_TIMESTAMP not null on update CURRENT_TIMESTAMP comment '更新时间',
    isDelete    tinyint      default 0             not null comment '逻辑删除',
    index idx_category (category, isDelete),
    index idx_user (userId, isDelete),
    index idx_preset (isPreset, isDelete)
) comment '测试场景表' collate = utf8mb4_unicode_ci;

-- 场景提示词表
create table if not exists scene_prompt
(
    id              varchar(36) primary key comment '提示词唯一标识',
    sceneId         varchar(36)                        not null comment '场景ID',
    userId          bigint                             not null comment '用户ID',
    promptIndex     int                                not null comment '提示词序号',
    title           varchar(200)                       not null comment '提示词标题',
    content         text                               not null comment '提示词内容',
    difficulty      varchar(20)                        null comment '难度: easy/medium/hard',
    tags            json                               null comment '标签数组',
    expectedOutput  text                               null comment '期望输出(可选)',
    createTime      datetime     default CURRENT_TIMESTAMP not null comment '创建时间',
    updateTime      datetime     default CURRENT_TIMESTAMP not null on update CURRENT_TIMESTAMP comment '更新时间',
    isDelete        tinyint      default 0             not null comment '逻辑删除',
    index idx_scene (sceneId, promptIndex),
    index idx_user (userId, isDelete)
) comment '场景提示词表' collate = utf8mb4_unicode_ci;

-- 批量测试任务表
create table if not exists test_task
(
    id                  varchar(36) primary key comment '任务唯一标识',
    userId              bigint                             not null comment '用户ID',
    name                varchar(200)                       null comment '任务名称',
    sceneId             varchar(36)                        not null comment '场景ID',
    models              json                               not null comment '测试的模型列表',
    status              varchar(20)                        not null comment '状态: pending/running/completed/failed/cancelled',
    totalSubtasks       int      default 0                 not null comment '子任务总数',
    completedSubtasks   int      default 0                 not null comment '已完成子任务数',
    startedAt           datetime                           null comment '开始时间',
    completedAt         datetime                           null comment '完成时间',
    createTime          datetime default CURRENT_TIMESTAMP not null comment '创建时间',
    updateTime          datetime default CURRENT_TIMESTAMP not null on update CURRENT_TIMESTAMP comment '更新时间',
    isDelete            tinyint  default 0                 not null comment '逻辑删除',
    index idx_user_created (userId, createTime desc, isDelete),
    index idx_status (status, isDelete),
    index idx_scene (sceneId, isDelete)
) comment '批量测试任务表' collate = utf8mb4_unicode_ci;

-- 批量测试结果表
create table if not exists test_result
(
    id              varchar(36) primary key comment '结果唯一标识',
    taskId          varchar(36)                        not null comment '任务ID',
    userId          bigint                             not null comment '用户ID',
    sceneId         varchar(36)                        not null comment '场景ID',
    promptId        varchar(36)                        not null comment '提示词ID',
    modelName       varchar(100)                       not null comment '模型名称',
    inputPrompt     text                               not null comment '输入提示词',
    outputText      text                               not null comment '输出内容',
    reasoning       text                               null comment '思考过程内容',
    responseTimeMs  int                                null comment '响应时间(毫秒)',
    inputTokens     int                                null comment '输入Token数',
    outputTokens    int                                null comment '输出Token数',
    cost            decimal(10, 6)                     null comment '成本(USD)',
    userRating      int                                null comment '用户评分(1-5)',
    aiScore         json                               null comment 'AI评分详情(多个评委模型的评分)',
    createTime      datetime default CURRENT_TIMESTAMP not null comment '创建时间',
    updateTime      datetime default CURRENT_TIMESTAMP not null on update CURRENT_TIMESTAMP comment '更新时间',
    isDelete        tinyint  default 0                 not null comment '逻辑删除',
    index idx_task (taskId, isDelete),
    index idx_model (modelName, isDelete),
    index idx_user (userId, isDelete),
    index idx_scene (sceneId, isDelete),
    index idx_prompt (promptId, isDelete)
) comment '批量测试结果表' collate = utf8mb4_unicode_ci;

-- 用户-模型使用统计表
create table if not exists user_model_usage
(
    id              varchar(36) primary key comment '记录唯一标识',
    userId          bigint                             not null comment '用户ID',
    modelName       varchar(100)                       not null comment '模型名称',
    totalTokens     bigint       default 0             not null comment '累计使用Token数',
    totalCost       decimal(12, 6) default 0           not null comment '累计花费（美元）',
    createTime      datetime     default CURRENT_TIMESTAMP not null comment '创建时间',
    updateTime      datetime     default CURRENT_TIMESTAMP not null on update CURRENT_TIMESTAMP comment '更新时间',
    isDelete        tinyint      default 0             not null comment '逻辑删除',
    unique key uk_user_model (userId, modelName, isDelete),
    index idx_user (userId, isDelete),
    index idx_model (modelName, isDelete)
) comment '用户-模型使用统计表' collate = utf8mb4_unicode_ci;


-- =============================================================================
-- 预设场景与提示词种子数据（可选执行）
--
-- 预设场景 userId 为 NULL、isPreset 为 1；scene_prompt 的 userId 不允许为 NULL，
-- 预设提示词统一填 0 表示「系统内置」，与自定义提示词（真实用户 ID）区分开。
-- id 使用固定值，配合下面「先删后插」的写法可以重复执行而不会产生重复数据。
-- =============================================================================

delete from scene_prompt where sceneId in ('preset-coding', 'preset-math', 'preset-copywriting');
delete from scene where id in ('preset-coding', 'preset-math', 'preset-copywriting');

insert into scene (id, userId, name, description, category, isPreset, isActive)
values ('preset-coding', null, '编程能力评测',
        '考察代码生成、算法实现与调试能力，共 4 道题，由易到难。', '编程', 1, 1),
       ('preset-math', null, '数学推理评测',
        '考察算术、代数与逻辑推理能力，共 3 道题。', '数学', 1, 1),
       ('preset-copywriting', null, '文案创作评测',
        '考察中文文案的创意、结构与语气把控，共 3 道题。', '文案', 1, 1);

insert into scene_prompt (id, sceneId, userId, promptIndex, title, content, difficulty, tags, expectedOutput)
values
    -- 编程场景
    ('preset-coding-0', 'preset-coding', 0, 0, '快排实现',
     '请用 Python 实现快速排序，要求：1）原地排序；2）包含详细的注释；3）给出一组测试用例并说明输出结果。',
     'easy', '["数组","排序","Python"]', null),
    ('preset-coding-1', 'preset-coding', 0, 1, '两数之和',
     '给定一个整数数组 nums 和一个目标值 target，请找出数组中和为目标值的两个整数，返回它们的下标。要求时间复杂度优于 O(n^2)，并说明你使用的算法思想。',
     'medium', '["哈希表","数组"]', null),
    ('preset-coding-2', 'preset-coding', 0, 2, 'LRU 缓存',
     '请设计并实现一个 LRU（最近最少使用）缓存结构，支持 get 和 put 操作，要求两个操作的时间复杂度均为 O(1)。请用 Python 实现并解释你的数据结构选择。',
     'hard', '["设计","哈希表","双向链表"]', null),
    ('preset-coding-3', 'preset-coding', 0, 3, '代码找 Bug',
     '下面这段 Python 代码本意是统计字符串中每个单词出现的次数，但存在 Bug，请找出问题并给出修正后的代码：\n\n```python\ndef word_count(text):\n    result = {}\n    for word in text.split(" "):\n        if word in result:\n            result[word] += 1\n        result[word] = 1\n    return result\n```',
     'medium', '["调试","字典"]', null),
    -- 数学场景
    ('preset-math-0', 'preset-math', 0, 0, '鸡兔同笼',
     '笼子里有鸡和兔共 35 只，脚共 94 只，问鸡和兔各有多少只？请写出完整的解题过程。',
     'easy', '["方程"]', null),
    ('preset-math-1', 'preset-math', 0, 1, '数列求和',
     '求数列 1/(1×2) + 1/(2×3) + 1/(3×4) + ... + 1/(99×100) 的值，请给出推导过程。',
     'medium', '["裂项相消"]', null),
    ('preset-math-2', 'preset-math', 0, 2, '概率推理',
     '有三个盒子，其中一个盒子里有奖品。你选择了 1 号盒，主持人知道奖品在哪，打开了一个空盒子（2 号），然后问你是否要换成 3 号盒。请用概率计算说明换与不换的胜率分别是多少。',
     'hard', '["概率","贝叶斯"]', null),
    -- 文案场景
    ('preset-copywriting-0', 'preset-copywriting', 0, 0, '产品卖点文案',
     '请为一款主打「续航 30 天」的智能手表写一段 100 字以内的电商详情页卖点文案，要求有画面感、不堆砌参数。',
     'easy', '["电商","短文案"]', null),
    ('preset-copywriting-1', 'preset-copywriting', 0, 1, '朋友圈推广',
     '请为一家新开的社区咖啡店写 3 条朋友圈推广文案，风格分别为：文艺、幽默、亲切，每条不超过 60 字。',
     'medium', '["社交媒体"]', null),
    ('preset-copywriting-2', 'preset-copywriting', 0, 2, '品牌故事',
     '请为一个国产户外运动品牌撰写一段 300 字左右的品牌故事，主题是「陪普通人走向山野」，要求真诚、不喊口号。',
     'hard', '["品牌","长文案"]', null);
