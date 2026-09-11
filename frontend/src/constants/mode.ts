/**
 * 平台功能模式的统一定义
 *
 * 三个页面（模型对比 / 提示词实验 / 代码模式）顶部的模式下拉共用这一份定义。
 * 每个页面只负责处理「切到别处」的跳转，避免各写一份选项导致文案和顺序不一致。
 */

/** 模型对比（多模型并排） */
export const MODE_COMPARE = 'compare'
/** 单模型对话 */
export const MODE_SINGLE = 'single'
/** 提示词实验（同模型多提示词变体） */
export const MODE_PROMPT_LAB = 'prompt-lab'
/** 代码模式（生成网页代码 + 沙箱预览） */
export const MODE_CODE = 'code-mode'

export interface ModeOption {
  value: string
  label: string
}

/** 下拉选项的顺序：普通对话 → 提示词实验 → 代码模式 */
export const MODE_OPTIONS: ModeOption[] = [
  { value: MODE_COMPARE, label: '模型对比' },
  { value: MODE_SINGLE, label: '单模型' },
  { value: MODE_PROMPT_LAB, label: '提示词实验' },
  { value: MODE_CODE, label: '代码模式' },
]

/** 每个模式落在哪个页面 */
export const MODE_ROUTES: Record<string, string> = {
  [MODE_COMPARE]: '/side-by-side',
  [MODE_SINGLE]: '/side-by-side',
  [MODE_PROMPT_LAB]: '/prompt-lab',
  [MODE_CODE]: '/code-mode',
}

/**
 * 处理模式下拉切换
 *
 * @param value 用户选中的模式
 * @param currentPage 当前页面承载的「大模式」（模型对比页是 compare/single，提示词实验页是 prompt-lab，代码模式页是 code-mode）
 * @returns 需要跳转的目标路径；不需要跳转时返回 null（调用方把下拉值改回当前页模式即可）
 */
export const resolveModeNavigation = (value: string, currentPage: string): string | null => {
  // 选中同一个页面内的模式（比如对比页里从「模型对比」切到「单模型」）不跳转
  if (MODE_ROUTES[value] === MODE_ROUTES[currentPage]) return null
  return MODE_ROUTES[value] ?? null
}
