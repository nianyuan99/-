<template>
  <div class="pl-root">
    <!-- ==================== 左侧：实验历史 ==================== -->
    <aside class="pl-sidebar">
      <RouterLink to="/" class="pl-brand" title="返回首页">
        <img class="pl-brand-logo" src="@/assets/logo.svg" alt="Logo" />
        <span class="pl-brand-title">大模型评测平台</span>
      </RouterLink>

      <button class="pl-new-chat" :disabled="isStreaming" @click="startNewExperiment">
        <EditOutlined />
        <span>新实验</span>
      </button>

      <div class="pl-history">
        <div class="pl-history-label">更早</div>
        <div
          v-for="conv in conversations"
          :key="conv.id"
          class="pl-conv"
          :class="{ active: conv.id === currentConversationId }"
          :title="conv.title || '未命名实验'"
          @click="loadConversation(conv.id)"
        >
          <span class="pl-conv-icon">
            <ExperimentOutlined />
          </span>
          <span class="pl-conv-title">{{ conv.title || '未命名实验' }}</span>
        </div>
        <div v-if="historyLoading" class="pl-history-tip">加载中…</div>
        <div v-else-if="conversations.length === 0" class="pl-history-tip">还没有实验记录</div>
      </div>

      <a-dropdown placement="topLeft" :trigger="['click']">
        <div class="pl-user">
          <a-avatar :size="26" :src="loginUserStore.loginUser.userAvatar" />
          <span class="pl-user-name">{{ loginUserStore.loginUser.userName ?? '未登录' }}</span>
        </div>
        <template #overlay>
          <a-menu>
            <a-menu-item key="home" @click="router.push('/')">
              <HomeOutlined />
              返回首页
            </a-menu-item>
            <a-menu-item key="logout" @click="doLogout">
              <LogoutOutlined />
              退出登录
            </a-menu-item>
          </a-menu>
        </template>
      </a-dropdown>
    </aside>

    <!-- ==================== 右侧：实验区 ==================== -->
    <main class="pl-main">
      <!-- 顶部：模式 + 单模型选择 -->
      <header class="pl-topbar">
        <div class="mode-wrap">
          <SwapOutlined class="mode-icon" />
          <a-select
            v-model:value="mode"
            :options="modeOptions"
            :disabled="isStreaming"
            class="mode-select"
            @change="onModeChange"
          />
        </div>

        <a-select
          v-model:value="selectedModel"
          :options="modelOptions"
          :loading="modelLoading"
          :disabled="isStreaming"
          :filter-option="filterModelOption"
          popup-class-name="pl-select-popup"
          :virtual="false"
          show-search
          class="pl-select wide"
          placeholder="选择一个模型"
        />

        <span class="pl-topbar-spacer" />
        <span class="pl-topbar-hint">同一个模型 · 多个提示词变体并排对比</span>
      </header>

      <!-- 中间：实验记录 -->
      <div class="pl-messages-wrap">
        <div ref="listRef" class="pl-messages" @scroll="onScroll">
          <div v-if="messages.length === 0" class="pl-empty">
            <div class="pl-empty-title">输入 2-5 个提示词变体，开始实验</div>
            <div class="pl-empty-desc">
              同一个模型分别回答每个变体，横向对比响应速度、Token 消耗与回答质量，
              帮你找出效果最好的提问方式
            </div>
          </div>

          <div v-for="(msg, idx) in messages" :key="idx" class="pl-row">
            <!-- 用户提交的多个变体 -->
            <div v-if="msg.type === 'user'" class="pl-user-line">
              <div class="pl-user-block">
                <div v-for="(variant, vi) in msg.variants" :key="vi" class="pl-user-bubble">
                  <span class="pl-user-tag">变体 {{ vi + 1 }}</span>
                  <span class="pl-user-text">{{ variant }}</span>
                </div>
              </div>
            </div>

            <!-- 各变体的回答 -->
            <template v-else>
              <div v-if="msg.results" class="pl-responses">
                <!-- 评分：所有变体都结束后出现（多次运行模式下隐藏评分，避免对多次结果歧义） -->
                <div v-if="canRate(msg) && (msg.runCount ?? 1) === 1" class="pl-rating-section">
                  <div class="pl-rating-title">选择最佳变体：</div>
                  <div class="pl-rating-buttons">
                    <button
                      v-for="(_, vIdx) in (msg.variants?.length ?? 0)"
                      :key="`rate-${vIdx}`"
                      class="pl-rating-btn"
                      :class="{ selected: msg.rating?.winnerVariantIndex === vIdx }"
                      @click="handleVariantRating(idx, vIdx)"
                    >
                      变体 {{ vIdx + 1 }}
                    </button>
                    <button
                      class="pl-rating-btn"
                      :class="{ selected: msg.rating?.ratingType === 'both_bad' }"
                      @click="handleVariantRating(idx, -1)"
                    >
                      都不好 👎
                    </button>
                  </div>
                </div>
                <div v-else-if="canRate(msg) && (msg.runCount ?? 1) > 1" class="pl-rating-section">
                  <div class="pl-rating-title">多次运行完成 · 仅展示聚合统计，不写评分</div>
                </div>

                <!-- 变体结果：水平平铺，可横向滚动 -->
                <div class="pl-results-grid">
                  <div
                    v-for="(group, vIdx) in groupResultsByVariant(msg)"
                    :key="`var-${vIdx}`"
                    class="pl-card"
                  >
                    <div class="pl-card-head">
                      <span class="pl-variant-badge">变体 {{ vIdx + 1 }}</span>
                      <span class="pl-head-spacer" />
                      <!-- 多次运行：显示聚合统计 -->
                      <template v-if="(msg.runCount ?? 1) > 1">
                        <span
                          v-if="aggregateRuns(group.runs).okCount > 0"
                          class="pl-metric pl-metric-aggregate"
                          :title="`${group.runs.length} 次运行的平均值`"
                        >
                          <ClockCircleOutlined />
                          {{ (aggregateRuns(group.runs).meanTime / 1000).toFixed(2) }}s
                        </span>
                        <span
                          v-if="aggregateRuns(group.runs).meanTokens > 0"
                          class="pl-metric pl-metric-aggregate"
                          :title="`${group.runs.length} 次运行的平均 Token`"
                        >
                          <BarChartOutlined />
                          {{ Math.round(aggregateRuns(group.runs).meanTokens) }}t
                        </span>
                        <span
                          v-if="aggregateRuns(group.runs).sumCost > 0"
                          class="pl-metric pl-metric-aggregate"
                          :title="`${group.runs.length} 次运行的总成本`"
                        >
                          <DollarOutlined />
                          {{ aggregateRuns(group.runs).sumCost.toFixed(4) }}
                        </span>
                      </template>
                      <!-- 单次运行：显示单次指标 -->
                      <template v-else>
                        <span v-if="group.runs[0]?.responseTimeMs" class="pl-metric">
                          <ClockCircleOutlined />
                          {{ (group.runs[0].responseTimeMs / 1000).toFixed(2) }}s
                        </span>
                        <span v-if="group.runs[0] && totalTokens(group.runs[0])" class="pl-metric">
                          <BarChartOutlined />
                          {{ totalTokens(group.runs[0]) }}t
                        </span>
                        <span v-if="group.runs[0]?.cost != null" class="pl-metric">
                          <DollarOutlined />
                          {{ group.runs[0].cost.toFixed(4) }}
                        </span>
                      </template>
                      <button
                        v-if="(msg.runCount ?? 1) === 1 && group.runs[0]"
                        class="pl-icon-btn"
                        title="复制回答"
                        :disabled="!group.runs[0].fullContent"
                        @click="copyResult(group.runs[0])"
                      >
                        <CopyOutlined />
                      </button>
                    </div>

                    <!-- 多次运行：每个 run 一个子卡片 -->
                    <template v-if="(msg.runCount ?? 1) > 1">
                      <div
                        v-for="(run, rIdx) in group.runs"
                        :key="`run-${vIdx}-${rIdx}`"
                        class="pl-subrun"
                      >
                        <div class="pl-subrun-head">
                          <span class="pl-subrun-label">第 {{ rIdx + 1 }}/{{ group.runs.length }} 次</span>
                          <span v-if="run.responseTimeMs" class="pl-subrun-metric">
                            <ClockCircleOutlined /> {{ (run.responseTimeMs / 1000).toFixed(2) }}s
                          </span>
                          <span v-if="totalTokens(run)" class="pl-subrun-metric">
                            <BarChartOutlined /> {{ totalTokens(run) }}t
                          </span>
                          <span v-if="run.cost != null" class="pl-subrun-metric">
                            <DollarOutlined /> {{ run.cost.toFixed(4) }}
                          </span>
                          <button
                            v-if="run.fullContent"
                            class="pl-icon-btn pl-icon-btn-sm"
                            title="复制这次回答"
                            @click="copyResult(run)"
                          >
                            <CopyOutlined />
                          </button>
                        </div>
                        <a-alert
                          v-if="run.hasError"
                          type="error"
                          :message="run.error || '该次调用失败'"
                          show-icon
                          class="pl-alert"
                        />
                        <template v-else-if="run.fullContent">
                          <details
                            v-if="hasReasoning(run) && run.reasoning"
                            class="pl-reasoning"
                            :open="!isReasoningCollapsed(idx, msg.results?.indexOf(run) ?? 0)"
                          >
                            <summary
                              class="pl-reasoning-head"
                              @click.prevent="toggleReasoning(idx, msg.results?.indexOf(run) ?? 0)"
                            >
                              <DownOutlined
                                class="pl-caret"
                                :class="{ collapsed: isReasoningCollapsed(idx, msg.results?.indexOf(run) ?? 0) }"
                              />
                              <span>思考了 {{ run.thinkingTime || 1 }} 秒</span>
                            </summary>
                            <div class="pl-reasoning-body">
                              <MarkdownRenderer :content="run.reasoning || ''" />
                            </div>
                          </details>
                          <MarkdownRenderer :content="run.fullContent" />
                        </template>
                        <div v-else-if="!run.done" class="pl-typing-dots">
                          <span /><span /><span />
                        </div>
                      </div>
                    </template>

                    <!-- 单次运行：保持原版渲染 -->
                    <template v-else>
                      <a-alert
                        v-if="group.runs[0]?.hasError"
                        type="error"
                        :message="group.runs[0].error || '该变体调用失败'"
                        show-icon
                        class="pl-alert"
                      />

                      <template v-else>
                        <div v-if="group.runs[0] && hasReasoning(group.runs[0])" class="pl-reasoning">
                          <div class="pl-reasoning-head" @click="toggleReasoning(idx, vIdx)">
                            <DownOutlined
                              class="pl-caret"
                              :class="{ collapsed: isReasoningCollapsed(idx, vIdx) }"
                            />
                            <span>
                              {{
                                group.runs[0]?.thinkingTime
                                  ? `思考了 ${group.runs[0].thinkingTime} 秒`
                                  : '思考过程'
                              }}
                            </span>
                          </div>
                          <div
                            v-show="!isReasoningCollapsed(idx, vIdx)"
                            class="pl-reasoning-body"
                          >
                            <MarkdownRenderer :content="group.runs[0]?.reasoning || ''" />
                          </div>
                        </div>

                        <MarkdownRenderer :content="group.runs[0]?.fullContent || ''" />
                      </template>

                      <div
                        v-if="!group.runs[0]?.done && !group.runs[0]?.hasError"
                        class="pl-dots"
                      >
                        <span></span><span></span><span></span>
                      </div>
                      <div v-if="group.runs[0]?.stopped" class="pl-stopped-tip">
                        已停止生成 · 以上为已生成的内容，已保存到历史记录
                      </div>
                    </template>
                  </div>
                </div>
              </div>
            </template>
          </div>
        </div>

        <button v-if="!atBottom" class="pl-scroll-btn" title="回到最新" @click="scrollToBottom(true)">
          <DownOutlined />
        </button>
      </div>

      <!-- 底部：变体输入区 -->
      <div class="pl-variants-wrap">
        <div class="pl-variants-panel">
          <div class="pl-panel-header">
            <span class="pl-panel-title">提示词变体 ({{ variants.length }}/5)</span>
            <div class="pl-header-actions">
              <a-tooltip title="多次运行会串行发起多次同变体实验，便于统计平均耗时/Token/成本。仅前端聚合，不写数据库。">
                <a-select
                  v-model:value="runCount"
                  size="small"
                  :options="runCountOptions"
                  :disabled="isStreaming"
                  style="width: 110px"
                  popup-class-name="pl-runcount-popup"
                />
              </a-tooltip>
              <a-button
                size="small"
                type="primary"
                :disabled="isStreaming"
                style="flex-shrink: 0"
                @click="showTemplateLibrary"
              >
                <template #icon><AppstoreOutlined /></template>
                模板库
              </a-button>
              <a-button
                size="small"
                :disabled="isStreaming"
                style="flex-shrink: 0"
                @click="showOptimizationHistory"
              >
                <template #icon><HistoryOutlined /></template>
                优化历史
              </a-button>
              <a-button
                size="small"
                type="dashed"
                :disabled="isStreaming || generating"
                @click="openGenerateModal"
              >
                <template #icon><RocketOutlined /></template>
                AI 自动生成
              </a-button>
              <a-button
                size="small"
                type="dashed"
                :disabled="variants.length >= MAX_VARIANTS || isStreaming"
                @click="addVariant"
              >
                + 添加变体
              </a-button>
              <a-button
                v-if="variants.length > MIN_VARIANTS"
                size="small"
                type="dashed"
                danger
                :disabled="isStreaming"
                @click="removeVariant(variants.length - 1)"
              >
                - 移除
              </a-button>
            </div>
          </div>

          <div class="pl-variants-horizontal">
            <div v-for="(variant, vi) in variants" :key="vi" class="pl-variant-card">
              <div class="pl-variant-card-header">
                <span class="pl-variant-label">变体 {{ vi + 1 }}</span>
                <div class="pl-variant-actions">
                  <a-button
                    size="small"
                    type="link"
                    :loading="optimizingIndex === vi"
                    :disabled="!variants[vi] || variants[vi].trim() === '' || isStreaming"
                    class="pl-optimize-btn"
                    @click="handleOptimizePrompt(vi)"
                  >
                    <template #icon><ThunderboltOutlined /></template>
                    优化
                  </a-button>
                  <button class="pl-icon-btn" title="放大编辑" @click="expandVariant(vi)">
                    <ExpandOutlined />
                  </button>
                </div>
              </div>
              <textarea
                v-model="variants[vi]"
                class="pl-variant-input"
                rows="3"
                placeholder="输入提示词变体..."
                :disabled="isStreaming"
              ></textarea>
            </div>
          </div>

          <div class="pl-submit-row">
            <button
              v-if="isStreaming"
              class="pl-submit-btn stop"
              @click="stopGeneration"
            >
              停止生成
            </button>
            <button
              v-else
              class="pl-submit-btn"
              :disabled="!canSubmit"
              @click="handleSubmit"
            >
              开始实验
            </button>
          </div>
        </div>
      </div>
    </main>

    <!-- 放大编辑某个变体 -->
    <a-modal
      v-model:open="expandOpen"
      :title="`放大编辑 · 变体 ${expandIndex + 1}`"
      ok-text="完成"
      :footer="null"
      width="720px"
    >
      <textarea
        v-model="variants[expandIndex]"
        class="pl-expand-textarea"
        rows="12"
        placeholder="输入提示词变体..."
        :disabled="isStreaming"
      ></textarea>
    </a-modal>

    <!-- AI 自动生成变体弹窗 -->
    <a-modal
      v-model:open="generateOpen"
      title="AI 自动生成变体"
      ok-text="生成并填充"
      cancel-text="取消"
      :confirm-loading="generating"
      :mask-closable="!generating"
      @ok="submitGenerate"
      @cancel="resetGenerate"
      width="560px"
    >
      <div class="pl-generate-form">
        <div class="pl-generate-tip">
          输入一个基础提示词，AI 会基于它生成多个不同风格（直接提问 / 角色扮演 / 思维链 / Few-shot）的变体，
          生成结果会替换下方变体输入框。
        </div>
        <div class="pl-generate-field">
          <label>基础提示词</label>
          <a-textarea
            v-model:value="generateForm.basePrompt"
            :rows="4"
            :maxlength="2000"
            :disabled="generating"
            placeholder="例如：帮我写一个快速排序"
          />
        </div>
        <div class="pl-generate-field">
          <label>生成数量</label>
          <a-input-number
            v-model:value="generateForm.count"
            :min="MIN_VARIANTS"
            :max="MAX_VARIANTS"
            :disabled="generating"
            style="width: 120px"
          />
        </div>
        <div class="pl-generate-field">
          <label>生成模型（可选）</label>
          <a-select
            v-model:value="generateForm.model"
            :options="generateModelOptions"
            :disabled="generating"
            allow-clear
            placeholder="默认使用免费模型"
            style="width: 100%"
          />
        </div>
      </div>
    </a-modal>

    <!-- 模板库抽屉 -->
    <a-drawer
      v-model:open="templateLibraryVisible"
      title="提示词模板库"
      width="720px"
      placement="right"
    >
      <div class="template-library">
        <!-- 模板来源分页签：全部 / 社区 / 我的收藏（功能扩展 2） -->
        <a-tabs v-model:activeKey="templateTab" size="small" @change="onTemplateTabChange">
          <a-tab-pane key="all" tab="全部模板" />
          <a-tab-pane key="community" tab="社区分享" />
          <a-tab-pane key="favorite" tab="我的收藏" />
        </a-tabs>

        <!-- 策略筛选 -->
        <div class="strategy-filter">
          <a-radio-group v-model:value="selectedStrategy" @change="loadTemplates">
            <a-radio-button value="">全部</a-radio-button>
            <a-radio-button value="direct">直接提问</a-radio-button>
            <a-radio-button value="cot">CoT</a-radio-button>
            <a-radio-button value="role_play">角色扮演</a-radio-button>
            <a-radio-button value="few_shot">Few-shot</a-radio-button>
          </a-radio-group>
          <!-- 社区页签下提供排序切换 -->
          <a-radio-group
            v-if="templateTab === 'community'"
            v-model:value="communitySortBy"
            size="small"
            @change="loadTemplates"
          >
            <a-radio-button value="latest">最新</a-radio-button>
            <a-radio-button value="hot">最热</a-radio-button>
          </a-radio-group>
        </div>

        <!-- 模板列表 -->
        <div v-if="templates.length > 0" class="template-list">
          <div v-for="template in templates" :key="template.id" class="template-item">
            <div class="template-header" @click="selectTemplate(template)">
              <div class="template-title-row">
                <span class="template-name">{{ template.name }}</span>
                <a-tag v-if="template.isPreset" color="blue">预设</a-tag>
                <a-tag v-else color="green">自定义</a-tag>
                <a-tag v-if="template.isPublic && !template.isPreset" color="cyan">公开</a-tag>
              </div>
              <a-tag color="purple">{{ template.strategyName }}</a-tag>
            </div>
            <div
              v-if="template.description"
              class="template-description"
              @click="selectTemplate(template)"
            >
              {{ template.description }}
            </div>
            <div class="template-preview" @click="selectTemplate(template)">
              {{ template.content?.substring(0, 100)
              }}{{ template.content && template.content.length > 100 ? '...' : '' }}
            </div>
            <!-- 底部：使用次数 + 作者 + 点赞/收藏（功能扩展 2） -->
            <div class="template-footer">
              <div class="template-meta">
                <span class="template-usage">使用 {{ template.usageCount || 0 }} 次</span>
                <span v-if="template.authorName" class="template-author">
                  来自 {{ template.authorName }}
                </span>
              </div>
              <div class="template-interactions">
                <button
                  class="template-interact-btn"
                  :class="{ active: template.liked }"
                  :title="template.liked ? '取消点赞' : '点赞'"
                  @click.stop="handleToggleLike(template)"
                >
                  <LikeFilled v-if="template.liked" />
                  <LikeOutlined v-else />
                  <span>{{ template.likeCount || 0 }}</span>
                </button>
                <button
                  class="template-interact-btn"
                  :class="{ active: template.favorited }"
                  :title="template.favorited ? '取消收藏' : '收藏'"
                  @click.stop="handleToggleFavorite(template)"
                >
                  <StarFilled v-if="template.favorited" />
                  <StarOutlined v-else />
                  <span>{{ template.favoriteCount || 0 }}</span>
                </button>
              </div>
            </div>
          </div>
        </div>
        <a-empty v-else :description="emptyTemplateHint" />

        <!-- 创建模板按钮 -->
        <div class="template-actions">
          <a-button type="dashed" block @click="showCreateTemplateModal">
            <template #icon><PlusOutlined /></template>
            创建自定义模板
          </a-button>
        </div>
      </div>
    </a-drawer>

    <!-- 模板变量填写（功能扩展 1：模板变量自动替换） -->
    <a-modal
      v-model:open="variableFormVisible"
      title="填写模板变量"
      ok-text="应用模板"
      cancel-text="取消"
      :confirm-loading="fillingVariables"
      width="560px"
      @ok="submitVariableForm"
    >
      <div class="variable-form">
        <div class="variable-form-tip">
          模板「{{ variableFormTemplate?.name }}」包含 {{ variableFormFields.length }} 个变量，填写后会自动替换到变体 {{ variableFormVariantIndex + 1 }}。
        </div>
        <div
          v-for="field in variableFormFields"
          :key="field.name"
          class="variable-form-field"
        >
          <label>{{ field.name }}</label>
          <a-textarea
            v-model:value="field.value"
            :rows="2"
            :placeholder="`请输入 ${field.name} 的值`"
          />
        </div>
      </div>
    </a-modal>

    <!-- 创建自定义模板 -->
    <a-modal
      v-model:open="createTemplateVisible"
      title="创建自定义模板"
      ok-text="创建并应用"
      cancel-text="取消"
      :confirm-loading="creatingTemplate"
      width="620px"
      @ok="submitCreateTemplate"
    >
      <div class="pl-generate-form">
        <div class="pl-generate-field">
          <label>模板名称</label>
          <a-input v-model:value="createTemplateForm.name" placeholder="例如：代码审查助手" />
        </div>
        <div class="pl-generate-field">
          <label>策略类型</label>
          <a-select
            v-model:value="createTemplateForm.strategy"
            :options="strategyOptions"
            style="width: 100%"
          />
        </div>
        <div class="pl-generate-field">
          <label>描述（可选）</label>
          <a-input v-model:value="createTemplateForm.description" placeholder="这个模板用在什么场景" />
        </div>
        <div class="pl-generate-field">
          <label>模板内容</label>
          <a-textarea
            v-model:value="createTemplateForm.content"
            :rows="8"
            placeholder="支持 {变量名} 占位符，例如：你是一位{role}，请回答：{question}"
          />
        </div>
        <div class="pl-generate-field">
          <label>分享到社区</label>
          <a-switch v-model:checked="createTemplateForm.isPublic" />
          <span class="pl-generate-hint">
            开启后其他用户可以在「社区分享」里浏览和使用这个模板
          </span>
        </div>
      </div>
    </a-modal>

    <!-- 优化结果抽屉 -->
    <a-drawer
      v-model:open="optimizationDrawerVisible"
      title="提示词优化建议"
      width="600px"
      placement="right"
    >
      <div v-if="optimizationResult" class="optimization-result">
        <!-- 质量评分（功能扩展 4） -->
        <div v-if="optimizationResult.qualityScore != null" class="quality-score-card">
          <div class="quality-score-left">
            <div
              class="quality-score-value"
              :class="`quality-${optimizationResult.qualityLevel}`"
            >
              {{ optimizationResult.qualityScore }}
            </div>
            <div class="quality-score-unit">/ 100</div>
          </div>
          <div class="quality-score-right">
            <div class="quality-score-title">
              原始提示词质量
              <a-tag :color="QUALITY_LEVEL_COLOR[optimizationResult.qualityLevel || 'fair']">
                {{ QUALITY_LEVEL_TEXT[optimizationResult.qualityLevel || 'fair'] }}
              </a-tag>
            </div>
            <a-progress
              :percent="optimizationResult.qualityScore"
              :stroke-color="qualityScoreColor(optimizationResult.qualityScore)"
              :show-info="false"
              size="small"
            />
          </div>
        </div>

        <!-- 问题列表 -->
        <div class="optimization-section">
          <h3 class="section-title">发现的问题</h3>
          <ul class="issues-list">
            <li v-for="(issue, idx) in optimizationResult.issues" :key="idx" class="issue-item">
              {{ issue }}
            </li>
          </ul>
        </div>
        <!-- 优化后的提示词 -->
        <div class="optimization-section">
          <h3 class="section-title">优化后的提示词</h3>
          <div class="optimized-prompt-box">
            <pre class="optimized-prompt-text">{{ optimizationResult.optimizedPrompt }}</pre>
            <a-button type="primary" size="small" style="margin-top: 12px" @click="applyOptimizedPrompt">
              应用优化
            </a-button>
          </div>
        </div>
        <!-- 改进点 -->
        <div class="optimization-section">
          <h3 class="section-title">改进说明</h3>
          <ul class="improvements-list">
            <li
              v-for="(improvement, idx) in optimizationResult.improvements"
              :key="idx"
              class="improvement-item"
            >
              {{ improvement }}
            </li>
          </ul>
        </div>
      </div>
      <a-empty v-else description="暂无优化结果" />
    </a-drawer>

    <!-- 优化历史抽屉（功能扩展 3） -->
    <a-drawer
      v-model:open="historyDrawerVisible"
      title="优化历史记录"
      width="620px"
      placement="right"
    >
      <div class="history-drawer">
        <div v-if="optimizationHistory.length > 0" class="history-list">
          <div v-for="record in optimizationHistory" :key="record.id" class="history-item">
            <div class="history-item-head">
              <div class="history-item-title">
                <span class="history-time">{{ formatHistoryTime(record.createTime) }}</span>
                <a-tag
                  v-if="record.qualityScore != null"
                  :color="QUALITY_LEVEL_COLOR[record.qualityLevel || 'fair']"
                >
                  {{ record.qualityScore }} 分 · {{ QUALITY_LEVEL_TEXT[record.qualityLevel || 'fair'] }}
                </a-tag>
              </div>
              <div class="history-item-actions">
                <a-button type="link" size="small" @click="reuseHistoryRecord(record)">
                  再次优化
                </a-button>
                <a-button type="link" size="small" danger @click="removeHistoryRecord(record)">
                  删除
                </a-button>
              </div>
            </div>
            <div class="history-original">
              <span class="history-label">原始</span>
              {{ record.originalPrompt }}
            </div>
            <div v-if="record.optimizedPrompt" class="history-optimized">
              <span class="history-label">优化后</span>
              {{ record.optimizedPrompt }}
            </div>
            <div class="history-item-foot">
              <span v-if="record.issues.length" class="history-count">
                {{ record.issues.length }} 个问题
              </span>
              <span v-if="record.improvements.length" class="history-count">
                {{ record.improvements.length }} 项改进
              </span>
              <span v-if="record.evaluationModel" class="history-model">
                评估模型：{{ record.evaluationModel }}
              </span>
            </div>
          </div>
        </div>
        <a-empty v-else description="还没有优化记录" />
      </div>
    </a-drawer>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import {
  AppstoreOutlined,
  BarChartOutlined,
  ClockCircleOutlined,
  CopyOutlined,
  DollarOutlined,
  DownOutlined,
  EditOutlined,
  ExpandOutlined,
  ExperimentOutlined,
  HistoryOutlined,
  HomeOutlined,
  LikeFilled,
  LikeOutlined,
  LogoutOutlined,
  PlusOutlined,
  RocketOutlined,
  StarFilled,
  StarOutlined,
  SwapOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons-vue'
import { API_BASE_URL } from '@/config/env'
import { userLogout } from '@/api/user'
import { useLoginUserStore } from '@/stores/loginUser'
import {
  addRating,
  generateVariants,
  listConversationMessages,
  listConversationVoByPage,
  listRatings,
  type ConversationMessageVO,
  type ConversationVO,
  type RatingType,
  type RatingVO,
  type StreamChunkVO,
} from '@/api/conversation'
import { listModels, type ModelVO } from '@/api/model'
import {
  createTemplate,
  deleteOptimizationHistory,
  fillTemplateVariables,
  incrementUsage,
  listCommunityTemplates,
  listFavoriteTemplates,
  listOptimizationHistory,
  listTemplates,
  optimizePrompt,
  toggleTemplateFavorite,
  toggleTemplateLike,
  QUALITY_LEVEL_COLOR,
  QUALITY_LEVEL_TEXT,
  type PromptOptimizationHistoryVO,
  type PromptOptimizationVO,
  type PromptTemplateVO,
} from '@/api/prompt'
import { createPostSSE, type SSEHandle } from '@/utils/sseClient'
import { MODE_OPTIONS, MODE_PROMPT_LAB, resolveModeNavigation } from '@/constants/mode'
import MarkdownRenderer from '@/components/MarkdownRenderer.vue'

/** 变体数量约束，与后端 constants 保持一致 */
const MIN_VARIANTS = 2
const MAX_VARIANTS = 5

/** 页面所在模式：本页固定是 prompt-lab，另外几项会跳去对应页面 */
const PROMPT_LAB_MODE = MODE_PROMPT_LAB

/** 距离底部多少像素内算「贴着底部」，此时新内容自动跟随滚动 */
const AUTO_SCROLL_THRESHOLD = 80

/** 侧栏一次拉取的历史实验条数 */
const HISTORY_PAGE_SIZE = 30

/** 单个变体的回答状态 */
interface VariantResult {
  variantIndex: number
  /** 多次运行下的 run 序号（从 0 开始；单次运行时固定为 0） */
  runIndex: number
  fullContent: string
  reasoning?: string
  done: boolean
  hasError: boolean
  error?: string
  elapsedMs?: number
  responseTimeMs?: number
  inputTokens?: number
  outputTokens?: number
  cost?: number
  hasReasoning?: boolean
  thinkingTime?: number
  /** 是否被用户主动停止生成（区别于调用失败） */
  stopped?: boolean
  /** 这次 run 关联的会话ID，多次运行模式下用于聚合 */
  conversationId?: string
  messageIndex?: number
}

/** 实验记录中的一条消息 */
interface PromptLabMsg {
  type: 'user' | 'assistant'
  /** 用户消息：本轮提交的提示词变体列表 */
  variants?: string[]
  /** AI 消息：各变体的回答（多次运行模式下：runCount × variantCount 长度，按 (runIdx, varIdx) 展开） */
  results?: VariantResult[]
  conversationId?: string
  messageIndex?: number
  rating?: { ratingType: string; winnerVariantIndex?: number }
  /** 多次运行次数（1 表示普通单次实验） */
  runCount?: number
}

const router = useRouter()
const route = useRoute()
const loginUserStore = useLoginUserStore()

// ---------- 模型 ----------
const modelList = ref<ModelVO[]>([])
const modelLoading = ref(false)
const mode = ref<string>(PROMPT_LAB_MODE)
const selectedModel = ref<string>()

const modeOptions = MODE_OPTIONS

// ---------- 实验状态 ----------
const variants = ref<string[]>(['', ''])
const isStreaming = ref(false)
/** 多次运行：1/2/3/5 次。1 = 走单次流程，>1 = 串行 N 次独立请求后做纯前端聚合 */
const runCount = ref<1 | 2 | 3 | 5>(1)
const runCountOptions = [
  { value: 1, label: '运行 1 次' },
  { value: 2, label: '运行 2 次' },
  { value: 3, label: '运行 3 次' },
  { value: 5, label: '运行 5 次' },
]
const messages = ref<PromptLabMsg[]>([])
/** 首轮实验的变体（用于加载历史后恢复输入框，保证轮次间变体数量一致） */
const originalVariants = ref<string[]>([])
const currentConversationId = ref<string | null>(null)
const conversations = ref<ConversationVO[]>([])
const historyLoading = ref(false)

// ---------- 视图状态 ----------
const listRef = ref<HTMLElement>()
const atBottom = ref(true)
const collapsedReasoning = ref<Set<string>>(new Set())
const expandOpen = ref(false)
const expandIndex = ref(0)
const sse = ref<SSEHandle | null>(null)

/** 下拉里的一个叶子选项 */
interface ModelOption {
  value: string
  label: string
  name?: string
}

/** 下拉里的一个分组（厂商） */
interface ModelOptionGroup {
  label: string
  options: ModelOption[]
}

/** 免费模型的分组标题 */
const FREE_GROUP_LABEL = '免费'

/** OpenRouter 免费变体：模型 ID 以 `:free` 结尾 */
const isFreeModel = (model: ModelVO) => model.id.endsWith(':free')

/** 展示名去掉「厂商: 」前缀 —— 分组标题已经写了厂商，二级菜单里再重复一遍太啰嗦 */
const shortModelName = (model: ModelVO) => {
  const name = model.name || model.id
  const sep = name.indexOf(': ')
  return sep > 0 ? name.slice(sep + 2) : name
}

/** 厂商展示名：优先取展示名的前缀，取不到再退回 provider 字段 */
const vendorLabel = (model: ModelVO) => {
  const name = model.name || ''
  const sep = name.indexOf(': ')
  if (sep > 0) return name.slice(0, sep)
  return model.provider || '其他'
}

/**
 * 模型下拉选项（分组结构）：第一组是免费模型，其余按厂商分组
 *
 * 排序与模型对比页一致：整体按发布时间由新到旧，组内新的在前；
 * 免费变体单独抽成一组放最前面（账号未充值时付费模型会 402）。
 */
const modelOptions = computed(() => {
  const sorted = [...modelList.value].sort((a, b) => (b.created ?? 0) - (a.created ?? 0))
  const free: ModelOption[] = []
  const vendors = new Map<string, ModelOption[]>()
  for (const model of sorted) {
    const option: ModelOption = {
      value: model.id,
      label: shortModelName(model),
      name: model.name,
    }
    if (isFreeModel(model)) {
      free.push(option)
      continue
    }
    const vendor = vendorLabel(model)
    const group = vendors.get(vendor)
    if (group) group.push(option)
    else vendors.set(vendor, [option])
  }

  const groups: ModelOptionGroup[] = []
  if (free.length) groups.push({ label: FREE_GROUP_LABEL, options: free })
  for (const [label, options] of vendors) groups.push({ label, options })
  return groups
})

/** 下拉搜索：模型 ID、完整展示名、去前缀的名字都能命中 */
const filterModelOption = (input: string, option: ModelOption) => {
  const keyword = input.trim().toLowerCase()
  if (!keyword) return true
  return (
    String(option.value).toLowerCase().includes(keyword) ||
    String(option.name || '').toLowerCase().includes(keyword) ||
    String(option.label || '').toLowerCase().includes(keyword)
  )
}

/**
 * 生成弹窗专用的「生成模型」下拉：扁平结构，不分厂商。
 * 这里只让用户选「用什么模型来生成变体」，与实验模型解耦，避免下拉过于复杂。
 */
const generateModelOptions = computed(() =>
  [...modelList.value]
    .sort((a, b) => (b.created ?? 0) - (a.created ?? 0))
    .map((m) => ({ value: m.id, label: shortModelName(m) })),
)

/* ========== AI 自动生成变体 ========== */
const generateOpen = ref(false)
const generating = ref(false)
const generateForm = ref<{ basePrompt: string; count: number; model?: string }>({
  basePrompt: '',
  count: 3,
  model: undefined,
})

const openGenerateModal = () => {
  if (isStreaming.value) return
  // 弹窗打开时如果变体输入框有内容，预填第一条作为基础提示词
  if (!generateForm.value.basePrompt && variants.value.length > 0) {
    generateForm.value.basePrompt = variants.value.find((v) => v && v.trim()) || ''
  }
  generateOpen.value = true
}

const resetGenerate = () => {
  generateForm.value = { basePrompt: '', count: 3, model: undefined }
}

const submitGenerate = async () => {
  if (generating.value) return
  const base = (generateForm.value.basePrompt || '').trim()
  if (!base) {
    message.warning('请输入基础提示词')
    return
  }
  const count = Math.max(MIN_VARIANTS, Math.min(MAX_VARIANTS, generateForm.value.count || 3))
  generating.value = true
  try {
    const res: any = await generateVariants({
      basePrompt: base,
      count,
      model: generateForm.value.model || undefined,
    })
    if (res?.data?.code === 0 && Array.isArray(res.data.data)) {
      const list = (res.data.data as string[]).slice(0, MAX_VARIANTS)
      // 变体数量对齐到 list 长度（不超过上限）；多则截断
      const final = list.slice(0, MAX_VARIANTS)
      // 少于最小值时用基础提示词补齐
      while (final.length < MIN_VARIANTS) final.push(base)
      variants.value = final
      message.success(`已生成 ${final.length} 个变体`)
      generateOpen.value = false
      resetGenerate()
    } else {
      message.error(res?.data?.message || '生成失败')
    }
  } catch (e: any) {
    message.error(e?.response?.data?.message || e?.message || '生成失败，请稍后重试')
  } finally {
    generating.value = false
  }
}

/**
 * 首次打开页面默认选中的模型
 *
 * 必须是免费模型：账号没充值时付费模型一律返回 402。
 * 这里写死一个实测可用的免费模型，不跟着后端排序走（排序规则一改默认值就会被换掉）。
 */
const DEFAULT_MODEL_IDS = ['nex-agi/nex-n2.5-mini:free', 'nvidia/nemotron-3-ultra-550b-a55b:free']

const pickDefaultModel = () => {
  const available = modelList.value.map((model) => model.id)
  const pool = [
    ...DEFAULT_MODEL_IDS.filter((id) => available.includes(id)),
    ...modelList.value.filter(isFreeModel).map((model) => model.id),
    ...modelList.value.filter((model) => model.recommended === 1).map((model) => model.id),
    ...available,
  ]
  return [...new Set(pool)][0]
}

/** 参与提交的变体（去掉空行） */
const filledVariants = computed(() => variants.value.map((v) => v.trim()).filter((v) => v !== ''))

/** 至少两个非空变体、选了模型、且没有正在跑的实验才能提交 */
const canSubmit = computed(
  () => !!selectedModel.value && filledVariants.value.length >= MIN_VARIANTS && !isStreaming.value,
)

onMounted(async () => {
  if (!loginUserStore.loginUser.id) {
    loginUserStore.fetchLoginUser().catch(() => {})
  }
  await Promise.all([loadModels(), loadConversations()])
  // 从 URL 带 conversationId 进来（刷新页面 / 分享链接）时恢复实验
  const queryId = route.query.conversationId as string | undefined
  if (queryId) {
    await loadConversation(queryId)
  }
})

// 组件销毁时关闭 SSE 连接，防止连接泄漏
onBeforeUnmount(() => {
  closeSSE()
})

/* ==================== 模式切换 ==================== */

/** 下拉里选「模型对比 / 单模型 / 代码模式」= 跳到对应页面；本页固定显示「提示词实验」 */
const onModeChange = (value: string) => {
  if (value === PROMPT_LAB_MODE) return
  const target = resolveModeNavigation(value, PROMPT_LAB_MODE)
  if (target) router.push(target)
  mode.value = PROMPT_LAB_MODE
}

/* ==================== 模型与历史数据 ==================== */

/** 加载模型列表（后端已按「国内优先 → 推荐优先」排序） */
const loadModels = async () => {
  modelLoading.value = true
  try {
    const res = await listModels()
    if (res.data.code === 0) {
      modelList.value = res.data.data || []
      if (!selectedModel.value) selectedModel.value = pickDefaultModel()
    } else {
      message.error('加载模型列表失败：' + res.data.message)
    }
  } catch (error) {
    message.error('加载模型列表失败：' + (error as Error).message)
  } finally {
    modelLoading.value = false
  }
}

/** 加载侧栏历史实验（只取 prompt_lab 类型、且非代码预览会话，避免混入其他模式的记录） */
const loadConversations = async () => {
  historyLoading.value = true
  try {
    const res = await listConversationVoByPage({
      conversationType: 'prompt_lab',
      // 代码模式的提示词实验也是 prompt_lab 类型，靠 codePreviewEnabled 区分开
      codePreviewEnabled: false,
      current: 1,
      pageSize: HISTORY_PAGE_SIZE,
    })
    if (res.data.code === 0) {
      conversations.value = res.data.data?.records || []
    }
  } catch {
    // 侧栏属于辅助信息，加载失败不打断主流程
  } finally {
    historyLoading.value = false
  }
}

/**
 * 加载历史实验
 *
 * Prompt Lab 的一轮实验里，多个变体的消息共享同一个 messageIndex，
 * 因此先按 messageIndex 归组，再按 variantIndex 排回变体顺序。
 */
const loadConversation = async (conversationId: string) => {
  if (isStreaming.value) {
    message.warning('正在运行实验，请先停止再切换')
    return
  }
  if (conversationId === currentConversationId.value && messages.value.length > 0) return

  try {
    const [msgRes, ratingRes] = await Promise.all([
      listConversationMessages(conversationId),
      listRatings(conversationId),
    ])
    if (msgRes.data.code !== 0) {
      message.error('加载实验失败：' + msgRes.data.message)
      return
    }

    const conv = conversations.value.find((item) => item.id === conversationId)
    if (conv?.models?.length) selectedModel.value = conv.models[0]

    const ratingMap = new Map<number, RatingVO>()
    if (ratingRes.data.code === 0) {
      for (const rating of ratingRes.data.data || []) {
        ratingMap.set(rating.messageIndex, rating)
      }
    }

    const rows = msgRes.data.data || []
    const groupMap = new Map<number, { userRows: ConversationMessageVO[]; aiRows: ConversationMessageVO[] }>()
    for (const row of rows) {
      let group = groupMap.get(row.messageIndex)
      if (!group) {
        group = { userRows: [], aiRows: [] }
        groupMap.set(row.messageIndex, group)
      }
      if (row.role === 'user') group.userRows.push(row)
      else group.aiRows.push(row)
    }

    const built: PromptLabMsg[] = []
    let firstRoundVariants: string[] = []
    const indexes = [...groupMap.keys()].sort((a, b) => a - b)

    for (const index of indexes) {
      const group = groupMap.get(index)!

      if (group.userRows.length) {
        const sorted = [...group.userRows].sort(
          (a, b) => (a.variantIndex ?? 0) - (b.variantIndex ?? 0),
        )
        const variantTexts = sorted.map((row) => row.content)
        // 首轮（最早的一轮）的变体作为输入框的原始变体
        if (firstRoundVariants.length === 0) firstRoundVariants = [...variantTexts]
        built.push({ type: 'user', variants: variantTexts, conversationId, messageIndex: index })
      }

      if (group.aiRows.length) {
        // 结果按 variantIndex 对号入座，保证「第 N 个卡片的评分按钮 = variant_N」
        const maxVariant = Math.max(
          ...group.aiRows.map((row, i) => (row.variantIndex ?? i) + 1),
          firstRoundVariants.length,
        )
        const results: VariantResult[] = Array.from({ length: maxVariant }, (_, i) => ({
          variantIndex: i,
          runIndex: 0,
          fullContent: '',
          done: true,
          hasError: true,
          error: '该变体没有保存到响应记录',
        }))
        group.aiRows.forEach((row, i) => {
          const vi = row.variantIndex ?? i
          results[vi] = {
            variantIndex: vi,
            runIndex: 0,
            fullContent: row.content,
            reasoning: row.reasoning,
            done: true,
            hasError: false,
            responseTimeMs: row.responseTimeMs,
            elapsedMs: row.responseTimeMs,
            inputTokens: row.inputTokens,
            outputTokens: row.outputTokens,
            cost: row.cost,
            hasReasoning: !!row.reasoning,
          }
        })
        built.push({ type: 'assistant', conversationId, messageIndex: index, results })
      }
    }

    // 回填评分状态，让评分按钮显示为已选中
    for (const item of built) {
      if (item.type !== 'assistant' || item.messageIndex === undefined) continue
      const rating = ratingMap.get(item.messageIndex)
      if (rating) {
        item.rating = {
          ratingType: rating.ratingType,
          winnerVariantIndex: rating.winnerVariantIndex,
        }
      }
    }

    // 恢复首轮变体：后续轮次无论如何修改输入框，变体数量都与首轮一致
    if (firstRoundVariants.length) {
      originalVariants.value = [...firstRoundVariants]
      variants.value = [...firstRoundVariants]
    }

    messages.value = built
    currentConversationId.value = conversationId
    // 历史记录的思考过程默认折叠，避免一屏都是灰色文本
    const collapsed = new Set<string>()
    built.forEach((item, msgIdx) => {
      ;(item.results || []).forEach((result, rIdx) => {
        if (hasReasoning(result)) collapsed.add(reasoningKey(msgIdx, rIdx))
      })
    })
    collapsedReasoning.value = collapsed
    scrollToBottom(true)
  } catch (error) {
    message.error('加载实验失败：' + (error as Error).message)
  }
}

/** 开启一个新实验（保留当前的模型选择） */
const startNewExperiment = () => {
  if (isStreaming.value) return
  closeSSE()
  messages.value = []
  currentConversationId.value = null
  variants.value = ['', '']
  originalVariants.value = []
  collapsedReasoning.value = new Set()
  if (route.query.conversationId) router.replace({ path: '/prompt-lab' })
  scrollToBottom(true)
}

/* ==================== 变体管理 ==================== */

const addVariant = () => {
  if (variants.value.length < MAX_VARIANTS) variants.value.push('')
}

const removeVariant = (index: number) => {
  if (variants.value.length > MIN_VARIANTS) variants.value.splice(index, 1)
}

const expandVariant = (index: number) => {
  expandIndex.value = index
  expandOpen.value = true
}

/* ==================== 展示辅助 ==================== */

const totalTokens = (result: VariantResult) => (result.inputTokens || 0) + (result.outputTokens || 0)

/**
 * 按变体索引把 results 拆成「每个变体一组 run」的二维结构
 *
 * 单次运行时：每个变体只有 1 个 run，结果与原渲染逻辑完全一致
 * 多次运行时：每个变体有 runCount 个 run，模板内再循环展开为子卡片
 */
const groupResultsByVariant = (msg: PromptLabMsg): { runs: VariantResult[] }[] => {
  const V = msg.variants?.length ?? 0
  if (!V || !msg.results) return []
  const groups: VariantResult[][] = Array.from({ length: V }, () => [])
  for (const r of msg.results) {
    if (r.variantIndex != null && r.variantIndex < V) groups[r.variantIndex]!.push(r)
  }
  // 多次运行时组内按 runIndex 稳定排序，避免初次占位顺序错乱
  return groups.map((runs) => ({
    runs: [...runs].sort((a, b) => (a.runIndex ?? 0) - (b.runIndex ?? 0)),
  }))
}

/**
 * 多次运行聚合：算平均耗时/平均 token/总成本/成功次数
 *
 * - 平均耗时/平均 token：仅统计成功的 run（done 且无 error）
 * - 总成本：累加所有成功的 run
 * - 成功次数：用于在卡片头部显示「3/5 次成功」之类
 */
const aggregateRuns = (runs: VariantResult[]) => {
  const ok = runs.filter((r) => r.done && !r.hasError)
  const totalCost = ok.reduce((s, r) => s + (r.cost || 0), 0)
  const meanTime =
    ok.length > 0
      ? ok.reduce((s, r) => s + (r.responseTimeMs || 0), 0) / ok.length
      : 0
  const meanTokens =
    ok.length > 0 ? ok.reduce((s, r) => s + totalTokens(r), 0) / ok.length : 0
  return {
    okCount: ok.length,
    totalCount: runs.length,
    meanTime,
    meanTokens,
    sumCost: totalCost,
  }
}

/**
 * 是否展示思考过程
 *
 * 个别模型会在 reasoning 字段里返回只含换行/空格的伪内容（后端已清洗，这里再兜一层），
 * 否则会渲染出一个空的灰色折叠框。
 */
const hasReasoning = (result: VariantResult) =>
  !!result.hasReasoning && !!(result.reasoning || '').trim()

/**
 * 本轮是否允许评分
 *
 * 必须所有变体都已结束、且至少有一个变体真的产出了内容：
 * 如果全都没内容（例如刚发出去就停止），库里不会有对应的 assistant 消息，
 * 此时提交评分就会变成指向不存在消息的孤儿数据。
 */
const canRate = (msg: PromptLabMsg) => {
  const results = msg.results
  if (!results || results.length < MIN_VARIANTS) return false
  if (!results.every((result) => result.done)) return false
  return results.some((result) => (result.fullContent || '').length > 0)
}

const reasoningKey = (msgIndex: number, resultIndex: number) => `${msgIndex}-${resultIndex}`

const isReasoningCollapsed = (msgIndex: number, resultIndex: number) =>
  collapsedReasoning.value.has(reasoningKey(msgIndex, resultIndex))

const toggleReasoning = (msgIndex: number, resultIndex: number) => {
  const next = new Set(collapsedReasoning.value)
  const key = reasoningKey(msgIndex, resultIndex)
  if (next.has(key)) next.delete(key)
  else next.add(key)
  collapsedReasoning.value = next
}

/* ==================== 滚动 ==================== */

/** 只有用户本来就贴着底部时才自动跟随新内容，避免打断向上翻看的操作 */
const scrollToBottom = (force = false) => {
  if (!force && !atBottom.value) return
  nextTick(() => {
    const el = listRef.value
    if (el) el.scrollTop = el.scrollHeight
  })
}

const onScroll = () => {
  const el = listRef.value
  if (!el) return
  atBottom.value = el.scrollHeight - el.scrollTop - el.clientHeight < AUTO_SCROLL_THRESHOLD
}

/* ==================== 提交与流式接收 ==================== */

const closeSSE = () => {
  if (sse.value) {
    sse.value.close()
    sse.value = null
  }
}

/** 新实验首次拿到 conversationId 后写入 URL，刷新页面才能恢复 */
const syncQuery = (conversationId: string) => {
  if (route.query.conversationId === conversationId) return
  router.replace({ path: '/prompt-lab', query: { conversationId } })
}

/**
 * 提交实验：串行发起 runCount 次，每次按 variantIndex 把结果分发到对应卡片
 *
 * runCount=1：单次流程，行为与之前一致（共用 currentConversationId，URL 同步等）
 * runCount>1：每次都新建 conversation；前 N×M 个 result 占位按 (runIdx, varIdx) 二维布局
 */
const handleSubmit = async () => {
  if (!canSubmit.value) return

  isStreaming.value = true

  const promptVariants = [...filledVariants.value]
  // 新实验的首轮：记下原始变体，后续轮次以它为准
  if (!currentConversationId.value && originalVariants.value.length === 0) {
    originalVariants.value = [...promptVariants]
  }

  messages.value.push({ type: 'user', variants: promptVariants })

  const totalRuns = runCount.value
  const isMultiRun = totalRuns > 1

  // 预创建 runCount × variantCount 个空 result，UI 立即显示 N 张卡片 × M 个子卡片的占位
  const assistantMsgIndex = messages.value.length
  const placeholderResults: VariantResult[] = []
  for (let r = 0; r < totalRuns; r++) {
    for (let v = 0; v < promptVariants.length; v++) {
      placeholderResults.push({
        variantIndex: v,
        runIndex: r,
        fullContent: '',
        done: false,
        hasError: false,
      })
    }
  }
  messages.value.push({
    type: 'assistant',
    conversationId: currentConversationId.value ?? undefined,
    results: placeholderResults,
    runCount: totalRuns,
  })
  scrollToBottom(true)

  try {
    for (let r = 0; r < totalRuns; r++) {
      // 多次运行时每次都传 undefined 强制新建 conversation
      // 单次时保留 currentConversationId 以支持多轮
      const useExisting = runCount.value === 1 && !!currentConversationId.value
      const cid = useExisting ? currentConversationId.value || undefined : undefined
      await runSingleRound(assistantMsgIndex, r, promptVariants, cid)
      // 中途失败但其他 run 还要继续
      if (hasRoundError(assistantMsgIndex, r) && r < totalRuns - 1) continue
    }
  } finally {
    isStreaming.value = false
    loadConversations()
  }
}

/**
 * 执行一次实验 run，把流式数据归位到 assistantMsg.results[runIdx * V + variantIdx]
 *
 * Returns when stream is complete (done 或错误)。不会 throw，错误通过 msg.results 标记。
 */
const runSingleRound = (
  assistantMsgIndex: number,
  runIdx: number,
  promptVariants: string[],
  conversationId: string | undefined,
): Promise<void> => {
  return new Promise((resolve) => {
    let settled = false
    const settle = () => {
      if (settled) return
      settled = true
      resolve()
    }

    createPostSSE(
      `${API_BASE_URL}/conversation/prompt-lab/stream`,
      {
        conversationId,
        model: selectedModel.value,
        promptVariants,
      },
      {
        onMessage: (chunk: StreamChunkVO) => {
          const msg = messages.value[assistantMsgIndex]
          if (!msg?.results) return

          if (chunk.conversationId) {
            // 单次运行时同步 URL 与 currentConversationId；多次运行只挂到自己的 result 上
            if (runIdx === 0 && runCount.value === 1) {
              currentConversationId.value = chunk.conversationId
              msg.conversationId = chunk.conversationId
              syncQuery(chunk.conversationId)
            }
          }

          const target = chunk.variantIndex
          if (target === undefined) return
          const slot = runIdx * promptVariants.length + target
          const prev = msg.results[slot]
          if (!prev) return
          msg.results[slot] = {
            ...prev,
            ...chunk,
            runIndex: runIdx,
            variantIndex: target,
            conversationId: chunk.conversationId || prev.conversationId,
            messageIndex: chunk.messageIndex ?? prev.messageIndex,
          }
          if (chunk.messageIndex !== undefined) msg.messageIndex = chunk.messageIndex
          // 强制触发 Vue 响应式更新
          messages.value = [...messages.value]
          scrollToBottom()

          // 本 run 所有变体都 done 才算这一轮结束
          if (!msg.results) return
          const allThisRunDone = promptVariants.every(
            (_, v) => msg.results![runIdx * promptVariants.length + v]?.done,
          )
          if (allThisRunDone) settle()
        },
        onError: (err) => {
          markRoundResultsFailed(assistantMsgIndex, runIdx, promptVariants.length, err.message)
          settle()
        },
        onComplete: () => {
          markRoundResultsFailed(
            assistantMsgIndex,
            runIdx,
            promptVariants.length,
            '连接已中断',
          )
          settle()
        },
      },
    )
  })
}

const hasRoundError = (msgIndex: number, runIdx: number): boolean => {
  const msg = messages.value[msgIndex]
  if (!msg?.results) return false
  // 仅当本 run 全部 hasError 时才视为本轮失败（部分变体成功不算）
  return msg.results.every((r) => r.runIndex === runIdx && r.hasError)
}

const markRoundResultsFailed = (
  msgIndex: number,
  runIdx: number,
  variantCount: number,
  reason: string,
) => {
  const msg = messages.value[msgIndex]
  if (!msg?.results) return
  for (let v = 0; v < variantCount; v++) {
    const slot = runIdx * variantCount + v
    const r = msg.results[slot]
    if (r && !r.done) {
      r.done = true
      r.hasError = true
      r.error = reason
    }
  }
  messages.value = [...messages.value]
}

/** 把仍然停留在「生成中」的变体标记为失败，避免页面一直转圈 */
const markResultsFailed = (msgIndex: number, reason: string) => {
  const msg = messages.value[msgIndex]
  if (!msg?.results) return
  let changed = false
  msg.results.forEach((result) => {
    if (!result.done) {
      result.done = true
      result.hasError = true
      result.error = reason
      changed = true
    }
  })
  if (changed) messages.value = [...messages.value]
}

/**
 * 中途停止生成
 *
 * 关闭 SSE 连接后，服务端会在下一次推送前检测到客户端断开并取消所有未完成的变体调用，
 * 因此不会继续消耗 API 额度；已经生成的内容后端会落库，历史记录里能看到。
 */
const stopGeneration = () => {
  closeSSE()
  isStreaming.value = false

  const lastMsg = messages.value[messages.value.length - 1]
  if (lastMsg?.results) {
    lastMsg.results.forEach((result) => {
      if (!result.done) {
        result.done = true
        result.stopped = true
      }
    })
    messages.value = [...messages.value]
  }
  message.info('已停止生成，已生成的内容已保存')
  loadConversations()
}

/* ==================== 评分 / 复制 ==================== */

/** 提交变体评分：variant_N 表示第 N 个变体最好，-1 表示都不好 */
const handleVariantRating = async (msgIndex: number, variantIndex: number) => {
  const msg = messages.value[msgIndex]
  if (!msg?.conversationId || msg.messageIndex === undefined) {
    message.warning('本轮实验尚未保存完成，请稍后再试')
    return
  }

  const ratingType: RatingType = variantIndex === -1 ? 'both_bad' : `variant_${variantIndex}`
  const winnerVariantIndex = variantIndex === -1 ? undefined : variantIndex

  try {
    const res = await addRating({
      conversationId: msg.conversationId,
      messageIndex: msg.messageIndex,
      ratingType,
      winnerVariantIndex,
    })
    if (res.data.code === 0) {
      msg.rating = { ratingType, winnerVariantIndex }
      messages.value = [...messages.value]
      message.success('评分已提交，感谢反馈')
    } else {
      message.error('评分失败：' + res.data.message)
    }
  } catch (error) {
    message.error('评分失败：' + (error as Error).message)
  }
}

/** 复制某个变体的完整回答 */
const copyResult = async (result: VariantResult) => {
  try {
    await navigator.clipboard.writeText(result.fullContent || '')
    message.success('已复制到剪贴板')
  } catch {
    message.error('复制失败，请手动选择内容')
  }
}

/* ==================== 模板库 ==================== */
const templateLibraryVisible = ref(false)
const templates = ref<PromptTemplateVO[]>([])
const selectedStrategy = ref<string>('')
/** 模板要应用到哪个变体；打开模板库时若没选就默认第 1 个 */
const selectedVariantIndex = ref<number>(0)

/** 模板来源页签：全部 / 社区分享 / 我的收藏（功能扩展 2） */
const templateTab = ref<'all' | 'community' | 'favorite'>('all')
const communitySortBy = ref<'latest' | 'hot'>('latest')

const emptyTemplateHint = computed(() => {
  if (templateTab.value === 'community') return '社区里还没有公开分享的模板'
  if (templateTab.value === 'favorite') return '还没有收藏任何模板'
  return '暂无模板'
})

/** 创建自定义模板 */
const createTemplateVisible = ref(false)
const creatingTemplate = ref(false)
const createTemplateForm = ref({
  name: '',
  strategy: 'direct',
  description: '',
  content: '',
  isPublic: false,
})

/** 模板变量填写（功能扩展 1） */
const variableFormVisible = ref(false)
const fillingVariables = ref(false)
const variableFormTemplate = ref<PromptTemplateVO | null>(null)
const variableFormVariantIndex = ref(0)
const variableFormFields = ref<{ name: string; value: string }[]>([])

const strategyOptions = [
  { value: 'direct', label: '直接提问' },
  { value: 'cot', label: 'CoT (思维链)' },
  { value: 'role_play', label: '角色扮演' },
  { value: 'few_shot', label: 'Few-shot (示例学习)' },
]

/** 显示模板库 */
const showTemplateLibrary = () => {
  templateLibraryVisible.value = true
  loadTemplates()
  if (
    selectedVariantIndex.value === null ||
    selectedVariantIndex.value < 0 ||
    selectedVariantIndex.value >= variants.value.length
  ) {
    selectedVariantIndex.value = 0
  }
}

/** 切换模板来源页签 */
const onTemplateTabChange = () => {
  loadTemplates()
}

/** 加载模板列表（按当前页签走不同接口） */
const loadTemplates = async () => {
  try {
    let res: any
    if (templateTab.value === 'community') {
      res = await listCommunityTemplates({
        strategy: selectedStrategy.value || undefined,
        sortBy: communitySortBy.value,
      })
    } else if (templateTab.value === 'favorite') {
      res = await listFavoriteTemplates()
    } else {
      res = await listTemplates({
        strategy: selectedStrategy.value || undefined,
      })
    }
    if (res.data && res.data.code === 0 && res.data.data) {
      templates.value = res.data.data
    } else {
      templates.value = []
    }
  } catch (error) {
    console.error('加载模板列表失败:', error)
    message.error('加载模板列表失败')
  }
}

/** 解析模板里要用到的变量名（后端已返回，兜底再从前端 content 解析一次） */
const resolveTemplateVariables = (template: PromptTemplateVO): string[] => {
  if (template.variables && template.variables.length > 0) return template.variables
  const matched = (template.content || '').match(/\{([a-zA-Z_][a-zA-Z0-9_]*)\}/g) || []
  const names: string[] = []
  for (const token of matched) {
    const name = token.slice(1, -1)
    if (!names.includes(name)) names.push(name)
  }
  return names
}

/** 选择模板：带变量的先弹表单填值（功能扩展 1），无变量的直接应用 */
const selectTemplate = async (template: PromptTemplateVO) => {
  if (!template.content) {
    message.warning('模板内容为空')
    return
  }

  const variableNames = resolveTemplateVariables(template)
  const targetIndex =
    selectedVariantIndex.value !== null &&
    selectedVariantIndex.value >= 0 &&
    selectedVariantIndex.value < variants.value.length
      ? selectedVariantIndex.value
      : 0

  if (variableNames.length > 0) {
    // 功能扩展 1：弹出表单让用户填写每个变量的值
    variableFormTemplate.value = template
    variableFormVariantIndex.value = targetIndex
    variableFormFields.value = variableNames.map((name) => ({ name, value: '' }))
    variableFormVisible.value = true
    return
  }

  await applyTemplateContent(template, targetIndex, template.content)
}

/** 把内容写进目标变体并记一次使用 */
const applyTemplateContent = async (
  template: PromptTemplateVO,
  targetIndex: number,
  content: string,
) => {
  try {
    if (template.id) {
      await incrementUsage(template.id)
    }
    variants.value[targetIndex] = content
    message.success(`模板已应用到变体 ${targetIndex + 1}`)
    templateLibraryVisible.value = false
    // 应用后同步刷新列表里的使用次数
    loadTemplates()
  } catch (error) {
    console.error('应用模板失败:', error)
    message.error('应用模板失败')
  }
}

/** 提交变量表单（功能扩展 1）：调后端替换，结果写回变体输入框（仍可编辑） */
const submitVariableForm = async () => {
  if (fillingVariables.value) return
  const template = variableFormTemplate.value
  if (!template) return

  const filled = variableFormFields.value.filter((f) => f.value.trim() !== '')
  if (filled.length === 0) {
    message.warning('请至少填写一个变量的值')
    return
  }

  fillingVariables.value = true
  try {
    const variables: Record<string, string> = {}
    for (const field of variableFormFields.value) {
      variables[field.name] = field.value
    }
    const res: any = await fillTemplateVariables({
      templateId: template.id,
      variables,
    })
    if (res.data?.code === 0 && res.data.data) {
      const { content, unfilledVariables } = res.data.data
      variableFormVisible.value = false
      await applyTemplateContent(template, variableFormVariantIndex.value, content)
      if (unfilledVariables && unfilledVariables.length > 0) {
        message.warning(`以下变量未填写，占位符已保留：${unfilledVariables.join('、')}`)
      }
    } else {
      message.error(res.data?.message || '填充模板变量失败')
    }
  } catch (error) {
    console.error('填充模板变量失败:', error)
    message.error('填充模板变量失败')
  } finally {
    fillingVariables.value = false
  }
}

/** 点赞 / 取消点赞（功能扩展 2） */
const handleToggleLike = async (template: PromptTemplateVO) => {
  try {
    const res: any = await toggleTemplateLike(template.id)
    if (res.data?.code === 0) {
      const liked = res.data.data
      template.liked = liked
      template.likeCount = Math.max(0, (template.likeCount || 0) + (liked ? 1 : -1))
      message.success(liked ? '已点赞' : '已取消点赞')
    } else {
      message.error(res.data?.message || '操作失败')
    }
  } catch (error) {
    console.error('点赞失败:', error)
    message.error('点赞失败')
  }
}

/** 收藏 / 取消收藏（功能扩展 2） */
const handleToggleFavorite = async (template: PromptTemplateVO) => {
  try {
    const res: any = await toggleTemplateFavorite(template.id)
    if (res.data?.code === 0) {
      const favorited = res.data.data
      template.favorited = favorited
      template.favoriteCount = Math.max(
        0,
        (template.favoriteCount || 0) + (favorited ? 1 : -1),
      )
      message.success(favorited ? '已收藏' : '已取消收藏')
    } else {
      message.error(res.data?.message || '操作失败')
    }
  } catch (error) {
    console.error('收藏失败:', error)
    message.error('收藏失败')
  }
}

/** 打开创建模板弹窗：把当前变体内容预填进去，省得重新敲一遍 */
const showCreateTemplateModal = () => {
  const current = variants.value[selectedVariantIndex.value]
  createTemplateForm.value = {
    name: '',
    strategy: selectedStrategy.value || 'direct',
    description: '',
    content: current || '',
    isPublic: false,
  }
  createTemplateVisible.value = true
}

/** 提交创建自定义模板，成功后自动应用到选中的变体 */
const submitCreateTemplate = async () => {
  if (creatingTemplate.value) return
  const form = createTemplateForm.value
  if (!form.name.trim()) {
    message.warning('请输入模板名称')
    return
  }
  if (!form.content.trim()) {
    message.warning('请输入模板内容')
    return
  }

  creatingTemplate.value = true
  try {
    const res: any = await createTemplate({
      name: form.name.trim(),
      strategy: form.strategy,
      description: form.description.trim() || undefined,
      content: form.content,
      isPublic: form.isPublic,
    })
    if (res.data?.code === 0) {
      message.success('模板创建成功')
      createTemplateVisible.value = false
      await loadTemplates()
    } else {
      message.error(res.data?.message || '创建模板失败')
    }
  } catch (error) {
    message.error('创建模板失败: ' + (error as Error).message)
  } finally {
    creatingTemplate.value = false
  }
}

/* ==================== AI 优化 ==================== */

// 优化相关状态
const optimizingIndex = ref<number | null>(null)
const optimizationDrawerVisible = ref(false)
const optimizationResult = ref<PromptOptimizationVO | null>(null)
const currentOptimizingVariantIndex = ref<number | null>(null)

// 优化提示词
const handleOptimizePrompt = async (variantIndex: number) => {
  const prompt = variants.value[variantIndex]
  if (!prompt || prompt.trim() === '') {
    message.warning('请先输入提示词')
    return
  }

  optimizingIndex.value = variantIndex
  currentOptimizingVariantIndex.value = variantIndex
  optimizationResult.value = null

  try {
    // 如果这个变体已经跑过实验，把最后一条回答一并交给 AI，让它结合实际效果分析
    let aiResponse: string | undefined = undefined
    if (messages.value.length > 0) {
      const lastAssistantMsg = messages.value.filter((m) => m.type === 'assistant').pop()
      if (
        lastAssistantMsg &&
        lastAssistantMsg.results &&
        lastAssistantMsg.results[variantIndex]
      ) {
        aiResponse = lastAssistantMsg.results[variantIndex].fullContent
      }
    }

    const res: any = await optimizePrompt({
      originalPrompt: prompt,
      aiResponse: aiResponse,
    })

    if (res.data && res.data.code === 0 && res.data.data) {
      optimizationResult.value = res.data.data
      optimizationDrawerVisible.value = true
      message.success('优化分析完成')
    } else {
      message.error(res.data?.message || '优化失败')
    }
  } catch (error) {
    console.error('优化提示词失败:', error)
    message.error('优化失败: ' + (error instanceof Error ? error.message : '未知错误'))
  } finally {
    optimizingIndex.value = null
  }
}

// 应用优化后的提示词
const applyOptimizedPrompt = () => {
  if (optimizationResult.value && currentOptimizingVariantIndex.value !== null) {
    variants.value[currentOptimizingVariantIndex.value] =
      optimizationResult.value.optimizedPrompt
    message.success('已应用优化后的提示词')
    optimizationDrawerVisible.value = false
  }
}

/* ==================== 功能扩展 3：优化历史记录 ==================== */

const historyDrawerVisible = ref(false)
const optimizationHistory = ref<PromptOptimizationHistoryVO[]>([])

/** 显示优化历史抽屉 */
const showOptimizationHistory = async () => {
  historyDrawerVisible.value = true
  await loadOptimizationHistory()
}

/** 加载优化历史 */
const loadOptimizationHistory = async () => {
  try {
    const res: any = await listOptimizationHistory({ limit: 50 })
    if (res.data?.code === 0 && res.data.data) {
      optimizationHistory.value = res.data.data
    } else {
      optimizationHistory.value = []
    }
  } catch (error) {
    console.error('加载优化历史失败:', error)
    message.error('加载优化历史失败')
  }
}

/** 删除一条优化历史 */
const removeHistoryRecord = async (record: PromptOptimizationHistoryVO) => {
  try {
    const res: any = await deleteOptimizationHistory(record.id)
    if (res.data?.code === 0) {
      optimizationHistory.value = optimizationHistory.value.filter(
        (item) => item.id !== record.id,
      )
      message.success('已删除')
    } else {
      message.error(res.data?.message || '删除失败')
    }
  } catch (error) {
    console.error('删除优化历史失败:', error)
    message.error('删除优化历史失败')
  }
}

/** 把历史记录里的原始提示词拿回变体，方便再次优化对比 */
const reuseHistoryRecord = (record: PromptOptimizationHistoryVO) => {
  const targetIndex =
    currentOptimizingVariantIndex.value !== null &&
    currentOptimizingVariantIndex.value >= 0 &&
    currentOptimizingVariantIndex.value < variants.value.length
      ? currentOptimizingVariantIndex.value
      : 0
  variants.value[targetIndex] = record.originalPrompt
  historyDrawerVisible.value = false
  message.success(`已填入变体 ${targetIndex + 1}，可再次点击「优化」`)
}

/** 格式化历史记录时间：只保留到分钟 */
const formatHistoryTime = (createTime?: string) => {
  if (!createTime) return '-'
  const date = new Date(createTime)
  if (Number.isNaN(date.getTime())) return createTime
  const pad = (n: number) => String(n).padStart(2, '0')
  return (
    `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ` +
    `${pad(date.getHours())}:${pad(date.getMinutes())}`
  )
}

/** 质量评分对应的进度条颜色（功能扩展 4） */
const qualityScoreColor = (score?: number) => {
  if (score == null) return '#8c8c8c'
  if (score >= 90) return '#52c41a'
  if (score >= 75) return '#1677ff'
  if (score >= 60) return '#fa8c16'
  return '#ff4d4f'
}

/* ==================== 用户 ==================== */

const doLogout = async () => {
  const res = await userLogout()
  if (res.data.code === 0) {
    loginUserStore.setLoginUser({ userName: '未登录' })
    message.success('退出登录成功')
    router.push('/user/login')
  } else {
    message.error('退出登录失败，' + res.data.message)
  }
}
</script>

<style scoped>
/* ==================== 整体布局 ==================== */
.pl-root {
  display: flex;
  height: 100vh;
  overflow: hidden;
  background: #fff;
  color: #1f2328;
  font-size: 14px;
}

/* ==================== 左侧实验栏 ==================== */
.pl-sidebar {
  flex: 0 0 232px;
  width: 232px;
  display: flex;
  flex-direction: column;
  padding: 12px 12px 10px;
  box-sizing: border-box;
  border-right: 1px solid #ececec;
  background: #fff;
}

.pl-brand {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 6px 16px;
  text-decoration: none;
}

.pl-brand-logo {
  height: 26px;
}

.pl-brand-title {
  font-size: 15px;
  font-weight: 700;
  color: #1f2328;
  white-space: nowrap;
}

.pl-new-chat {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  height: 40px;
  border: 1px solid #e5e7eb;
  border-radius: 10px;
  background: #fff;
  color: #1f2328;
  font-size: 14px;
  cursor: pointer;
  transition: all 0.2s;
}

.pl-new-chat:hover:not(:disabled) {
  background: #f7f8fa;
  border-color: #d7dbe0;
}

.pl-new-chat:disabled {
  color: #b9c0ca;
  cursor: not-allowed;
}

.pl-history {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  margin-top: 18px;
}

.pl-history-label {
  padding: 0 8px 6px;
  font-size: 12px;
  color: #9aa1ac;
}

.pl-conv {
  display: flex;
  align-items: center;
  gap: 8px;
  height: 36px;
  padding: 0 8px;
  border-radius: 8px;
  color: #4b5563;
  font-size: 13px;
  cursor: pointer;
  transition: background 0.15s;
}

.pl-conv:hover {
  background: #f5f6f8;
}

.pl-conv.active {
  background: #eef4ff;
  color: #1677ff;
}

.pl-conv-icon {
  flex: 0 0 auto;
  font-size: 13px;
}

.pl-conv-title {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.pl-history-tip {
  padding: 6px 8px;
  font-size: 12px;
  color: #b0b6bf;
}

.pl-user {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 8px;
  padding: 10px 8px 6px;
  border-top: 1px solid #f0f1f3;
  border-radius: 8px;
  cursor: pointer;
}

.pl-user:hover {
  background: #f5f6f8;
}

.pl-user-name {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 14px;
  color: #1f2328;
}

/* ==================== 主区域 ==================== */
.pl-main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
}

.pl-topbar {
  flex: 0 0 auto;
  display: flex;
  align-items: center;
  gap: 10px;
  height: 64px;
  padding: 0 20px;
  border-bottom: 1px solid #eef0f2;
}

.pl-topbar-spacer {
  flex: 1;
}

.pl-topbar-hint {
  font-size: 12px;
  color: #9aa1ac;
  white-space: nowrap;
}

.mode-wrap {
  position: relative;
  display: inline-flex;
  align-items: center;
}

.mode-icon {
  position: absolute;
  left: 11px;
  z-index: 2;
  font-size: 14px;
  color: #6b7280;
  pointer-events: none;
}

.mode-select {
  width: 150px;
}

.mode-select :deep(.ant-select-selector) {
  padding-left: 30px !important;
}

.pl-select.wide {
  width: 340px;
}

.pl-select :deep(.ant-select-selector),
.mode-select :deep(.ant-select-selector) {
  height: 36px !important;
  border-radius: 8px !important;
  border-color: #e3e6ea !important;
}

.pl-select :deep(.ant-select-selection-item),
.mode-select :deep(.ant-select-selection-item) {
  line-height: 34px !important;
}

/* ---------- 模型下拉的分组标题（厂商 / 免费） ---------- */

/* 弹层挂在 body 上，scoped 选择器够不到，所以用 :global + 弹层类名限定范围 */
:global(.pl-select-popup .ant-select-item-group) {
  position: sticky;
  top: 0;
  z-index: 1;
  padding: 7px 12px;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.06em;
  color: #8a93a0;
  background: #f6f7f9;
  border-top: 1px solid #eceff3;
}

:global(.pl-select-popup .ant-select-item-group:first-child) {
  border-top: none;
}

:global(.pl-select-popup .ant-select-item-option) {
  padding-left: 22px;
}

:global(.pl-select-popup .ant-select-item-option-selected) {
  font-weight: 600;
}

/* ==================== 实验记录区 ==================== */
.pl-messages-wrap {
  position: relative;
  flex: 1;
  min-height: 0;
  display: flex;
}

.pl-messages {
  flex: 1;
  overflow-y: auto;
  padding: 28px 40px 16px;
}

.pl-empty {
  height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 10px;
  text-align: center;
}

.pl-empty-title {
  font-size: 16px;
  font-weight: 600;
  color: #4b5563;
}

.pl-empty-desc {
  max-width: 480px;
  font-size: 13px;
  line-height: 1.8;
  color: #9aa1ac;
}

.pl-row {
  margin-bottom: 26px;
}

.pl-user-line {
  display: flex;
  justify-content: flex-end;
  margin-bottom: 20px;
}

.pl-user-block {
  max-width: 72%;
  display: flex;
  flex-direction: column;
  gap: 8px;
  align-items: flex-end;
}

.pl-user-bubble {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 10px 14px;
  border-radius: 12px;
  background: #f2f3f5;
  font-size: 14px;
  line-height: 1.6;
}

.pl-user-tag {
  flex: 0 0 auto;
  margin-top: 1px;
  padding: 1px 8px;
  border-radius: 999px;
  background: #e6f4ff;
  color: #1677ff;
  font-size: 12px;
  white-space: nowrap;
}

.pl-user-text {
  white-space: pre-wrap;
  word-break: break-word;
}

/* ---------- 变体结果 ---------- */
.pl-responses {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.pl-results-grid {
  display: flex;
  flex-direction: row;
  flex-wrap: nowrap;
  align-items: stretch;
  gap: 20px;
  width: 100%;
  overflow-x: auto;
  padding-bottom: 4px;
}

.pl-card {
  flex: 1 1 0;
  min-width: 380px;
  box-sizing: border-box;
  padding: 16px 20px 18px;
  border: 1px solid #ececec;
  border-radius: 12px;
  background: #fff;
}

.pl-card-head {
  display: flex;
  align-items: center;
  gap: 6px;
  padding-bottom: 12px;
  margin-bottom: 14px;
  border-bottom: 1px solid #f2f3f5;
  font-size: 12px;
  color: #9aa1ac;
}

.pl-head-spacer {
  flex: 1;
}

.pl-variant-badge {
  padding: 2px 9px;
  border-radius: 999px;
  background: #f0f5ff;
  color: #2f54eb;
  font-size: 12px;
  font-weight: 600;
  white-space: nowrap;
}

.pl-metric {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  margin-left: 8px;
  white-space: nowrap;
}

.pl-icon-btn {
  width: 24px;
  height: 24px;
  margin-left: 4px;
  padding: 0;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: #9aa1ac;
  font-size: 13px;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s;
}

.pl-icon-btn:hover:not(:disabled) {
  background: #f4f5f7;
  color: #1677ff;
}

.pl-icon-btn:disabled {
  color: #d8dce1;
  cursor: not-allowed;
}

.pl-alert {
  margin-bottom: 12px;
}

.pl-reasoning {
  padding: 10px 12px;
  margin-bottom: 14px;
  border-radius: 8px;
  background: #f7f8fa;
}

.pl-reasoning-head {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  color: #6b7280;
  cursor: pointer;
  user-select: none;
}

.pl-caret {
  font-size: 10px;
  transition: transform 0.2s;
}

.pl-caret.collapsed {
  transform: rotate(-90deg);
}

.pl-reasoning-body {
  margin-top: 8px;
  font-size: 13px;
  line-height: 1.75;
  color: #6b7280;
}

.pl-dots {
  display: inline-flex;
  gap: 4px;
  padding-top: 6px;
}

.pl-dots span {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #bfbfbf;
  animation: pl-dot-blink 1.2s infinite ease-in-out;
}

.pl-dots span:nth-child(2) {
  animation-delay: 0.2s;
}

.pl-dots span:nth-child(3) {
  animation-delay: 0.4s;
}

@keyframes pl-dot-blink {
  0%,
  80%,
  100% {
    opacity: 0.3;
  }
  40% {
    opacity: 1;
  }
}

.pl-stopped-tip {
  margin-top: 10px;
  font-size: 12px;
  color: #fa8c16;
}

/* ---------- 评分 ---------- */
.pl-rating-section {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  padding: 10px 14px;
  border: 1px solid #ececec;
  border-radius: 12px;
  background: #fafbfc;
}

.pl-rating-title {
  font-size: 13px;
  color: #6b7280;
  white-space: nowrap;
}

.pl-rating-buttons {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.pl-rating-btn {
  padding: 6px 18px;
  border: 1px solid #e5e7eb;
  border-radius: 10px;
  background: #fff;
  color: #1f2328;
  font-size: 13px;
  white-space: nowrap;
  cursor: pointer;
  transition: all 0.2s;
}

.pl-rating-btn:hover {
  border-color: #1677ff;
  color: #1677ff;
}

.pl-rating-btn.selected {
  border-color: #1677ff;
  background: #e6f4ff;
  color: #1677ff;
}

/* ==================== 变体输入区 ==================== */
.pl-variants-wrap {
  flex: 0 0 auto;
  padding: 8px 40px 20px;
}

.pl-variants-panel {
  padding: 12px 14px 12px;
  border: 1px solid #e5e7eb;
  border-radius: 16px;
  background: #fff;
}

.pl-panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding-bottom: 10px;
}

.pl-panel-title {
  font-size: 13px;
  font-weight: 600;
  color: #4b5563;
}

.pl-header-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

/* AI 自动生成变体弹窗 */
.pl-generate-form {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.pl-generate-tip {
  font-size: 13px;
  color: #6b7280;
  background: #f3f4f6;
  border: 1px solid #e5e7eb;
  border-radius: 6px;
  padding: 10px 12px;
  line-height: 1.6;
}
.pl-generate-field {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.pl-generate-field label {
  font-size: 13px;
  color: #1f2937;
  font-weight: 500;
}

/* 多次运行：聚合指标与子卡片 */
.pl-metric-aggregate {
  background: #eef2ff;
  color: #4338ca;
  border: 1px solid #c7d2fe;
  font-weight: 500;
}
.pl-subrun {
  border-top: 1px dashed #e5e7eb;
  padding: 10px 0 4px;
  margin-top: 8px;
}
.pl-subrun:first-child {
  border-top: none;
  margin-top: 0;
  padding-top: 4px;
}
.pl-subrun-head {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 6px;
  font-size: 12px;
  color: #6b7280;
}

/* ==================== 变体卡片头部：优化按钮 ==================== */
.pl-variant-actions {
  display: flex;
  align-items: center;
  gap: 4px;
}

.pl-optimize-btn {
  padding: 0 4px;
  height: 24px;
  font-size: 12px;
}

/* ==================== 模板库抽屉 ==================== */
.template-library {
  display: flex;
  flex-direction: column;
  gap: 16px;
  height: 100%;
}

.strategy-filter {
  flex: 0 0 auto;
}

.template-list {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.template-item {
  padding: 14px 16px;
  border: 1px solid #e5e7eb;
  border-radius: 12px;
  background: #fff;
  cursor: pointer;
  transition: all 0.2s;
}

.template-item:hover {
  border-color: #1677ff;
  box-shadow: 0 2px 10px rgba(22, 119, 255, 0.12);
}

.template-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 8px;
}

.template-title-row {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.template-name {
  font-size: 14px;
  font-weight: 600;
  color: #1f2328;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.template-description {
  margin-bottom: 8px;
  font-size: 13px;
  color: #6b7280;
}

.template-preview {
  padding: 8px 10px;
  border-radius: 8px;
  background: #f7f8fa;
  font-size: 12px;
  line-height: 1.7;
  color: #8a93a0;
  white-space: pre-wrap;
  word-break: break-word;
}

.template-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-top: 8px;
  font-size: 12px;
  color: #b0b6bf;
}

.template-meta {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}

.template-author {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* 点赞 / 收藏按钮（功能扩展 2） */
.template-interactions {
  display: flex;
  align-items: center;
  gap: 6px;
  flex: 0 0 auto;
}

.template-interact-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 2px 8px;
  border: 1px solid #e5e7eb;
  border-radius: 999px;
  background: #fff;
  font-size: 12px;
  color: #8a93a0;
  cursor: pointer;
  transition: all 0.2s;
}

.template-interact-btn:hover {
  border-color: #1677ff;
  color: #1677ff;
}

.template-interact-btn.active {
  border-color: #1677ff;
  background: #e6f4ff;
  color: #1677ff;
}

/* 模板变量填写弹窗（功能扩展 1） */
.variable-form {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.variable-form-tip {
  padding: 10px 12px;
  border-radius: 8px;
  background: #f0f5ff;
  font-size: 13px;
  line-height: 1.7;
  color: #2f54eb;
}

.variable-form-field {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.variable-form-field label {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 12px;
  font-weight: 600;
  color: #5b6472;
}

.pl-generate-hint {
  margin-left: 8px;
  font-size: 12px;
  color: #8a93a0;
}

.template-actions {
  flex: 0 0 auto;
}

/* 质量评分卡片（功能扩展 4） */
.quality-score-card {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 14px 16px;
  border: 1px solid #e5e7eb;
  border-radius: 12px;
  background: #fafbfc;
}

.quality-score-left {
  display: flex;
  align-items: baseline;
  gap: 2px;
  flex: 0 0 auto;
}

.quality-score-value {
  font-size: 34px;
  font-weight: 700;
  line-height: 1;
}

.quality-score-value.quality-excellent {
  color: #52c41a;
}
.quality-score-value.quality-good {
  color: #1677ff;
}
.quality-score-value.quality-fair {
  color: #fa8c16;
}
.quality-score-value.quality-poor {
  color: #ff4d4f;
}

.quality-score-unit {
  font-size: 13px;
  color: #b0b6bf;
}

.quality-score-right {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.quality-score-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  font-weight: 600;
  color: #1f2328;
}

/* ==================== 优化历史抽屉（功能扩展 3） ==================== */
.history-drawer {
  display: flex;
  flex-direction: column;
}

.history-list {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.history-item {
  padding: 14px 16px;
  border: 1px solid #e5e7eb;
  border-radius: 12px;
  background: #fff;
}

.history-item-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 10px;
}

.history-item-title {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.history-time {
  font-size: 13px;
  font-weight: 600;
  color: #1f2328;
}

.history-item-actions {
  display: flex;
  align-items: center;
  gap: 2px;
  flex: 0 0 auto;
}

.history-original,
.history-optimized {
  margin-bottom: 8px;
  padding: 8px 10px;
  border-radius: 8px;
  font-size: 12px;
  line-height: 1.7;
  color: #5b6472;
  white-space: pre-wrap;
  word-break: break-word;
}

.history-original {
  background: #f7f8fa;
}

.history-optimized {
  background: #f6ffed;
}

.history-label {
  display: inline-block;
  margin-right: 6px;
  padding: 1px 6px;
  border-radius: 4px;
  background: #e6f4ff;
  font-size: 11px;
  color: #1677ff;
}

.history-item-foot {
  display: flex;
  align-items: center;
  gap: 12px;
  font-size: 12px;
  color: #b0b6bf;
}

.history-count {
  color: #8a93a0;
}

/* ==================== 优化结果抽屉 ==================== */
.optimization-result {
  display: flex;
  flex-direction: column;
  gap: 22px;
}

.optimization-section {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.section-title {
  margin: 0;
  font-size: 14px;
  font-weight: 600;
  color: #1f2328;
}

.issues-list,
.improvements-list {
  margin: 0;
  padding-left: 20px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.issue-item {
  font-size: 13px;
  line-height: 1.7;
  color: #cf1322;
}

.improvement-item {
  font-size: 13px;
  line-height: 1.7;
  color: #237804;
}

.optimized-prompt-box {
  padding: 12px 14px;
  border: 1px solid #e5e7eb;
  border-radius: 10px;
  background: #f7f8fa;
}

.optimized-prompt-text {
  margin: 0;
  font-family: inherit;
  font-size: 13px;
  line-height: 1.8;
  color: #1f2328;
  white-space: pre-wrap;
  word-break: break-word;
}
.pl-subrun-label {
  background: #f3f4f6;
  color: #374151;
  padding: 2px 8px;
  border-radius: 10px;
  font-weight: 500;
}
.pl-subrun-metric {
  display: inline-flex;
  align-items: center;
  gap: 2px;
}
.pl-icon-btn-sm {
  width: 22px;
  height: 22px;
  font-size: 11px;
}

.pl-variants-horizontal {
  display: flex;
  flex-direction: row;
  gap: 12px;
  overflow-x: auto;
  padding-bottom: 4px;
}

.pl-variant-card {
  flex: 1 1 0;
  min-width: 220px;
  box-sizing: border-box;
  padding: 8px 10px 10px;
  border: 1px solid #eef0f2;
  border-radius: 10px;
  background: #fbfcfd;
}

.pl-variant-card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 4px;
}

.pl-variant-label {
  font-size: 12px;
  font-weight: 600;
  color: #6b7280;
}

.pl-variant-input {
  display: block;
  width: 100%;
  min-height: 62px;
  max-height: 140px;
  padding: 0;
  border: none;
  outline: none;
  resize: none;
  background: transparent;
  font-family: inherit;
  font-size: 13px;
  line-height: 1.65;
  color: #1f2328;
}

.pl-variant-input::placeholder {
  color: #b0b6bf;
}

.pl-variant-input:disabled {
  color: #b0b6bf;
}

.pl-submit-row {
  display: flex;
  justify-content: flex-end;
  margin-top: 10px;
}

.pl-submit-btn {
  min-width: 120px;
  height: 36px;
  padding: 0 24px;
  border: none;
  border-radius: 10px;
  background: #1677ff;
  color: #fff;
  font-size: 14px;
  cursor: pointer;
  transition: all 0.2s;
}

.pl-submit-btn:hover:not(:disabled) {
  background: #4096ff;
}

.pl-submit-btn:disabled {
  background: #eef1f5;
  color: #b9c0ca;
  cursor: not-allowed;
}

.pl-submit-btn.stop {
  background: #ff4d4f;
}

.pl-submit-btn.stop:hover {
  background: #ff7875;
}

.pl-scroll-btn {
  position: absolute;
  left: 50%;
  bottom: 10px;
  transform: translateX(-50%);
  width: 30px;
  height: 30px;
  padding: 0;
  border: 1px solid #ececec;
  border-radius: 50%;
  background: #fff;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
  color: #6b7280;
  font-size: 12px;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

/* ==================== 放大编辑 ==================== */
.pl-expand-textarea {
  display: block;
  width: 100%;
  padding: 10px 12px;
  border: 1px solid #e5e7eb;
  border-radius: 10px;
  outline: none;
  resize: vertical;
  background: #fff;
  font-family: inherit;
  font-size: 14px;
  line-height: 1.7;
  color: #1f2328;
  box-sizing: border-box;
}

.pl-expand-textarea:focus {
  border-color: #1677ff;
}
</style>
