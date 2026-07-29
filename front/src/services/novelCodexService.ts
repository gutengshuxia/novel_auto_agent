/**
 * novel_codex_agent Prompt 引擎 API 服务
 *
 * 封装与后端 /api/v1/novel-codex/ 的通信
 */

import { get, post } from './http'

const PREFIX = '/v1/novel-codex'

/** 生成请求参数 */
export interface NovelCodexGenerateParams {
  chapter_id: string
  director_ids?: string[] | null
  target_models?: string[]
  enable_storyboard_cards?: boolean
  text_model_id?: string | null
}

/** 任务启动响应 */
export interface NovelCodexTaskResponse {
  task_id: string
  status: string
  message: string
}

/** 任务状态响应 */
export interface NovelCodexStatusResponse {
  task_id: string
  status: 'pending' | 'running' | 'succeeded' | 'failed'
  current_step: string
  progress: number
  error: string
}

/** 单个镜头 Prompt */
export interface NovelCodexShotPrompt {
  shot_id: string
  shot_index: number
  shot_title: string
  prompt_text: string
  negative_prompt: string
  model: string
  quality_score: number
}

/** 故事板卡片 */
export interface NovelCodexCard {
  shot_id: string
  card_type: string
  title: string
  prompt: string
  image_url: string
}

/** 完整结果响应 */
export interface NovelCodexResultResponse {
  task_id: string
  status: string
  current_step: string
  progress: number
  shot_prompts: NovelCodexShotPrompt[]
  storyboard_cards: NovelCodexCard[]
  overall_score: number
  cast_updated: boolean
  elapsed_seconds: number
  error: string
}

/** 启动 Prompt 生成任务 */
export async function generatePrompts(
  params: NovelCodexGenerateParams,
): Promise<{ code: number; data: NovelCodexTaskResponse }> {
  return post(`${PREFIX}/generate`, params) as Promise<{
    code: number
    data: NovelCodexTaskResponse
  }>
}

/** 查询任务状态 */
export async function getTaskStatus(
  taskId: string,
): Promise<{ code: number; data: NovelCodexStatusResponse }> {
  return get(`${PREFIX}/status/${taskId}`) as Promise<{
    code: number
    data: NovelCodexStatusResponse
  }>
}

/** 获取任务结果 */
export async function getTaskResult(
  taskId: string,
): Promise<{ code: number; data: NovelCodexResultResponse }> {
  return get(`${PREFIX}/result/${taskId}`) as Promise<{
    code: number
    data: NovelCodexResultResponse
  }>
}
