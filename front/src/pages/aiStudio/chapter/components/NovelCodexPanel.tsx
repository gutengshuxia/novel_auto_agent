/**
 * NovelCodexPanel — AI Prompt 一键生成组件
 *
 * 包含: 触发按钮 + 进度弹窗 + 结果展示面板
 */

import React, { useCallback, useEffect, useRef, useState } from 'react'
import {
  Button,
  Collapse,
  Drawer,
  Modal,
  Progress,
  Space,
  Tag,
  Tooltip,
  message,
} from 'antd'
import {
  ThunderboltOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  LoadingOutlined,
  RobotOutlined,
} from '@ant-design/icons'
import {
  generatePrompts,
  getTaskStatus,
  getTaskResult,
  type NovelCodexResultResponse,
  type NovelCodexStatusResponse,
} from '../../../../services/novelCodexService'

interface NovelCodexPanelProps {
  chapterId: string
  /** 生成完成后的回调 (可用于刷新镜头列表) */
  onComplete?: () => void
}

/** 步骤名中文映射 */
const STEP_LABELS: Record<string, string> = {
  start: '启动中',
  step1_analyze: 'Step 1/6 · 剧本分析',
  step1_5_review: 'Step 1.5 · 审核',
  step2_storyboard: 'Step 2/6 · 导演分镜',
  step2_5_review: 'Step 2.5 · 审核',
  step3_plan_prompts: 'Step 3/6 · Prompt 规划',
  step4_write_prompts: 'Step 4/6 · Prompt 撰写',
  step4_5_review: 'Step 4.5 · 审核',
  step5_consistency_check: 'Step 5/6 · 一致性检查',
  step6_model_adapter: 'Step 6/6 · 模型适配',
  generating_cards: '生成故事板卡片',
  pipeline_done: 'Pipeline 完成',
  done: '完成',
}

const NovelCodexPanel: React.FC<NovelCodexPanelProps> = ({ chapterId, onComplete }) => {
  const [modalOpen, setModalOpen] = useState(false)
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [status, setStatus] = useState<NovelCodexStatusResponse | null>(null)
  const [result, setResult] = useState<NovelCodexResultResponse | null>(null)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const taskIdRef = useRef<string>('')

  // 清理轮询
  const stopPolling = useCallback(() => {
    if (pollRef.current) {
      clearInterval(pollRef.current)
      pollRef.current = null
    }
  }, [])

  // 轮询任务状态
  const startPolling = useCallback(
    (taskId: string) => {
      stopPolling()
      pollRef.current = setInterval(async () => {
        try {
          const resp = await getTaskStatus(taskId)
          const data = resp.data
          setStatus(data)
          if (data.status === 'succeeded' || data.status === 'failed') {
            stopPolling()
            if (data.status === 'succeeded') {
              // 获取完整结果
              const resultResp = await getTaskResult(taskId)
              setResult(resultResp.data)
              message.success(`Prompt 生成完成！评分: ${resultResp.data.overall_score}`)
              onComplete?.()
            } else {
              message.error(`Prompt 生成失败: ${data.error}`)
            }
          }
        } catch {
          // 忽略轮询错误, 继续重试
        }
      }, 2000)
    },
    [stopPolling, onComplete],
  )

  // 启动生成
  const handleGenerate = useCallback(async () => {
    setModalOpen(true)
    setStatus(null)
    setResult(null)
    try {
      const resp = await generatePrompts({
        chapter_id: chapterId,
        enable_storyboard_cards: true,
      })
      taskIdRef.current = resp.data.task_id
      startPolling(resp.data.task_id)
    } catch (err: unknown) {
      const errMsg = err instanceof Error ? err.message : String(err)
      message.error(`启动失败: ${errMsg}`)
      setModalOpen(false)
    }
  }, [chapterId, startPolling])

  // 组件卸载时清理
  useEffect(() => stopPolling, [stopPolling])

  const stepLabel = status ? (STEP_LABELS[status.current_step] || status.current_step) : ''
  const isRunning = status?.status === 'pending' || status?.status === 'running'
  const isDone = status?.status === 'succeeded'
  const isFailed = status?.status === 'failed'

  return (
    <>
      {/* 触发按钮 */}
      <Tooltip title="AI 一键生成视频 Prompt (novel_codex_agent)">
        <Button
          type="primary"
          icon={<ThunderboltOutlined />}
          onClick={handleGenerate}
          loading={isRunning}
        >
          AI Prompt
        </Button>
      </Tooltip>

      {/* 进度弹窗 */}
      <Modal
        title={
          <Space>
            <RobotOutlined />
            AI Prompt 生成
          </Space>
        }
        open={modalOpen}
        onCancel={() => {
          stopPolling()
          setModalOpen(false)
          if (isDone) setDrawerOpen(true)
        }}
        footer={
          isDone
            ? [
                <Button key="close" onClick={() => setModalOpen(false)}>
                  关闭
                </Button>,
                <Button key="result" type="primary" onClick={() => setDrawerOpen(true)}>
                  查看结果
                </Button>,
              ]
            : isFailed
              ? [
                  <Button key="retry" type="primary" onClick={handleGenerate}>
                    重试
                  </Button>,
                ]
              : null
        }
        maskClosable={false}
        width={480}
      >
        <div className="py-4">
          {/* 进度条 */}
          <Progress
            percent={status?.progress ?? 0}
            status={isFailed ? 'exception' : isDone ? 'success' : 'active'}
            strokeColor={{ from: '#108ee9', to: '#87d068' }}
          />

          {/* 当前步骤 */}
          <div className="mt-3 text-sm text-gray-600">
            {isRunning && <LoadingOutlined className="mr-2" />}
            {isDone && <CheckCircleOutlined className="mr-2 text-green-500" />}
            {isFailed && <CloseCircleOutlined className="mr-2 text-red-500" />}
            {isRunning && stepLabel && `正在执行: ${stepLabel}`}
            {isDone && '全部完成！'}
            {isFailed && `执行失败: ${status?.error || '未知错误'}`}
            {!status && '正在启动...'}
          </div>

          {/* 结果摘要 (完成时显示) */}
          {isDone && result && (
            <div className="mt-4 rounded-lg bg-gray-50 p-3">
              <div className="flex items-center justify-between text-sm">
                <span>质量评分</span>
                <Tag color={result.overall_score >= 80 ? 'green' : 'orange'}>
                  {result.overall_score} 分
                </Tag>
              </div>
              <div className="mt-2 flex items-center justify-between text-sm">
                <span>镜头 Prompt</span>
                <span>{result.shot_prompts?.length || 0} 条</span>
              </div>
              <div className="mt-2 flex items-center justify-between text-sm">
                <span>故事板卡片</span>
                <span>{result.storyboard_cards?.length || 0} 张</span>
              </div>
              <div className="mt-2 flex items-center justify-between text-sm">
                <span>耗时</span>
                <span>{result.elapsed_seconds?.toFixed(1)}s</span>
              </div>
            </div>
          )}
        </div>
      </Modal>

      {/* 结果抽屉 */}
      <Drawer
        title="AI Prompt 生成结果"
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        width={640}
      >
        {result && (
          <div className="flex flex-col gap-4">
            {/* 总览 */}
            <div className="rounded-lg bg-blue-50 p-4">
              <div className="text-lg font-medium">
                总评分: {result.overall_score} / 100
              </div>
              <div className="mt-1 text-sm text-gray-600">
                {result.shot_prompts?.length || 0} 个镜头 · {result.storyboard_cards?.length || 0} 张卡片 ·{' '}
                {result.elapsed_seconds?.toFixed(1)}s
              </div>
            </div>

            {/* 各镜头 Prompt */}
            <Collapse
              items={(result.shot_prompts || []).map((sp) => ({
                key: sp.shot_id,
                label: (
                  <Space>
                    <Tag>Shot {sp.shot_index}</Tag>
                    <span>{sp.shot_title || sp.shot_id}</span>
                    <Tag color="blue">{sp.model}</Tag>
                    <Tag color={sp.quality_score >= 80 ? 'green' : 'orange'}>
                      {sp.quality_score}分
                    </Tag>
                  </Space>
                ),
                children: (
                  <div className="flex flex-col gap-2">
                    <div>
                      <div className="text-xs text-gray-500 mb-1">视频 Prompt</div>
                      <div className="rounded bg-gray-50 p-2 text-sm whitespace-pre-wrap">
                        {sp.prompt_text || '(空)'}
                      </div>
                    </div>
                    <div>
                      <div className="text-xs text-gray-500 mb-1">负面提示词</div>
                      <div className="rounded bg-red-50 p-2 text-sm text-red-700 whitespace-pre-wrap">
                        {sp.negative_prompt || '(空)'}
                      </div>
                    </div>
                  </div>
                ),
              }))}
            />

            {/* 故事板卡片 */}
            {result.storyboard_cards && result.storyboard_cards.length > 0 && (
              <>
                <div className="text-base font-medium mt-2">故事板卡片</div>
                <div className="grid grid-cols-2 gap-3">
                  {result.storyboard_cards.map((card, i) => (
                    <div key={i} className="rounded-lg border border-gray-200 p-3">
                      <div className="flex items-center gap-2 mb-1">
                        <Tag color={card.card_type === 'character' ? 'blue' : card.card_type === 'scene' ? 'green' : 'purple'}>
                          {card.card_type}
                        </Tag>
                        <span className="text-sm font-medium truncate">{card.title}</span>
                      </div>
                      <div className="text-xs text-gray-600 line-clamp-3">{card.prompt}</div>
                    </div>
                  ))}
                </div>
              </>
            )}
          </div>
        )}
      </Drawer>
    </>
  )
}

export default NovelCodexPanel
