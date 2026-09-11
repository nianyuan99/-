-- =============================================================================
-- 教程第 10 节「七、功能扩展」相关建表与升级脚本
--
-- 包含：
--   1. prompt_template 加 isPublic 字段（扩展 2：模板分享和社区）
--   2. prompt_template_like    点赞表（扩展 2）
--   3. prompt_template_favorite 收藏表（扩展 2）
--   4. prompt_optimization_history 优化历史表（扩展 3）
--
-- 扩展 1（模板变量自动替换）与扩展 4（提示词质量评分）不需要改表结构：
--   扩展 1 是纯函数 + 接口，扩展 4 的 qualityScore 落在优化历史表的 qualityScore 列。
--
-- MySQL 8.0 的 add column 不支持 if not exists，重复执行会报
-- ERROR 1060 (42S21): Duplicate column name，忽略即可。
-- =============================================================================

-- ---------- 扩展 2：模板公开字段 ----------
alter table prompt_template
    add column isPublic tinyint default 0 not null comment '是否公开(1-公开，社区可见并使用 0-私有)'
        after isPreset;


-- ---------- 扩展 2：模板点赞表 ----------
create table if not exists prompt_template_like
(
    id          varchar(36) primary key comment '点赞唯一标识',
    templateId  varchar(36)                        not null comment '模板ID',
    userId      bigint                             not null comment '用户ID',
    createTime  datetime default CURRENT_TIMESTAMP not null comment '创建时间',
    isDelete    tinyint  default 0                 not null comment '逻辑删除',
    -- 一个用户对一个模板只保留一行（取消再点赞走行内翻转，不新增）
    unique key uk_template_user (templateId, userId),
    index idx_user (userId, isDelete)
) comment '模板点赞表' collate = utf8mb4_unicode_ci;


-- ---------- 扩展 2：模板收藏表 ----------
create table if not exists prompt_template_favorite
(
    id          varchar(36) primary key comment '收藏唯一标识',
    templateId  varchar(36)                        not null comment '模板ID',
    userId      bigint                             not null comment '用户ID',
    createTime  datetime default CURRENT_TIMESTAMP not null comment '创建时间',
    isDelete    tinyint  default 0                 not null comment '逻辑删除',
    unique key uk_template_user (templateId, userId),
    index idx_user (userId, isDelete)
) comment '模板收藏表' collate = utf8mb4_unicode_ci;


-- ---------- 扩展 3 + 扩展 4：优化历史表（含质量评分） ----------
create table if not exists prompt_optimization_history
(
    id               varchar(36) primary key comment '记录唯一标识',
    userId           bigint                             not null comment '用户ID',
    originalPrompt   text                               not null comment '原始提示词',
    optimizedPrompt  text                               null comment '优化后的提示词',
    issues           json                               null comment '发现的问题(JSON数组)',
    improvements     json                               null comment '改进说明(JSON数组)',
    qualityScore     int                                null comment '原始提示词质量评分(0-100)',
    evaluationModel  varchar(100)                       null comment '评估模型',
    createTime       datetime default CURRENT_TIMESTAMP not null comment '创建时间',
    isDelete         tinyint  default 0                 not null comment '逻辑删除',
    index idx_user_time (userId, isDelete, createTime)
) comment '提示词优化历史表' collate = utf8mb4_unicode_ci;
