/**
 * PipelineProgressModal - Pipeline 执行进度模态框
 *
 * 显示 4 步进度（Beat规划→Prompt生成→一致性审计→模型适配）、
 * 实时日志、完成后的审计评分和 Beat 序列。
 */

import { useEffect, useRef, useState } from 'react'
import { Progress, Steps, Tag, message } from 'antd'
import {
  LoadingOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
} from '@ant-design/icons'
import { FilmService, StudioShotDetailsService } from '../../../../services/generated'
import TaskLogPanel from '../../project/ProjectWorkbench/components/TaskLogPanel'

const PIPELINE_STEPS = [
  { title: 'Beat 规划', pct: 35 },
  { title: 'Prompt 生成', pct: 50 },
  { title: '一致性审计', pct: 80 },
  { title: '模型适配', pct: 100 },
]

type PipelineProgressContentProps = {
  taskId: string
  progress: number
  setProgress: (v: number) => void
  currentStep: string
  setCurrentStep: (v: string) => void
  status: string
  setStatus: (v: string) => void
  result: any
  setResult: (v: any) => void
  onComplete?: (detail: any) => void
  originalPrompt?: string
}

export default function PipelineProgressContent({
  taskId,
  progress,
  setProgress,
  currentStep,
  setCurrentStep,
  status,
  setStatus,
  result,
  setResult,
  onComplete,
  originalPrompt,
}: PipelineProgressContentProps) {
  const timerRef = useRef<number | null>(null)
  const shotIdRef = useRef<string>('')

  useEffect(() => {
    if (!taskId) return
    let cancelled = false

    const poll = async () => {
      try {
        const sr = await FilmService.getTaskStatusApiV1FilmTasksTaskIdStatusGet({ taskId })
        if (cancelled) return
        const data = sr.data
        if (!data) return

        setProgress(data.progress ?? 0)
        setCurrentStep(data.current_step ?? '')

        if (data.status === 'succeeded') {
          setStatus('succeeded')
          // Fetch result for audit / beat info
          try {
            const rr = await FilmService.getTaskResultApiV1FilmTasksTaskIdResultGet({ taskId })
            setResult(rr.data?.result ?? null)
            // Also fetch shot detail to get key_frame_prompt
            if (rr.data?.result) {
              const r = rr.data.result as any
              if (r.shot_id) {
                shotIdRef.current = r.shot_id
                const detailRes = await StudioShotDetailsService.getShotDetailApiV1StudioShotDetailsShotIdGet({ shotId: r.shot_id })
                onComplete?.(detailRes?.data)
              }
            }
          } catch { /* ignore */ }
          return
        }

        if (data.status === 'failed' || data.status === 'cancelled') {
          setStatus(data.status)
          return
        }

        timerRef.current = window.setTimeout(() => { void poll() }, 2000)
      } catch {
        if (!cancelled) {
          timerRef.current = window.setTimeout(() => { void poll() }, 3000)
        }
      }
    }

    void poll()
    return () => {
      cancelled = true
      if (timerRef.current !== null) window.clearTimeout(timerRef.current)
    }
  }, [taskId])

  // Determine current step index from progress
  const currentStepIndex = (() => {
    if (status === 'succeeded') return 4
    if (status === 'failed') return -1
    const p = Math.max(0, Math.min(100, progress || 0))
    for (let i = PIPELINE_STEPS.length - 1; i >= 0; i--) {
      if (p >= PIPELINE_STEPS[i].pct - 15) return i
    }
    return 0
  })()

  const isRunning = status === 'running' || status === ''
  const isSucceeded = status === 'succeeded'
  const isFailed = status === 'failed' || status === 'cancelled'

  const r = result as any

  return (
    <div className="space-y-4">
      {/* Step indicator */}
      <Steps
        size="small"
        current={currentStepIndex}
        status={isFailed ? 'error' : isSucceeded ? 'finish' : 'process'}
        items={PIPELINE_STEPS.map((s) => ({ title: s.title }))}
      />

      {/* Progress bar */}
      <Progress
        percent={Math.max(0, Math.min(100, (isSucceeded || isFailed) ? 100 : (progress || 0)))}
        status={isFailed ? 'exception' : isSucceeded ? 'success' : 'active'}
        strokeColor={isFailed ? '#ff4d4f' : isSucceeded ? '#52c41a' : '#1677ff'}
      />

      {/* Current step text */}
      {currentStep && (
        <div className="text-sm text-gray-600 flex items-center gap-2">
          {isRunning && <LoadingOutlined />}
          {isSucceeded && <CheckCircleOutlined style={{ color: '#52c41a' }} />}
          {isFailed && <CloseCircleOutlined style={{ color: '#ff4d4f' }} />}
          <span>{currentStep}</span>
        </div>
      )}

      {/* Completion summary */}
      {isSucceeded && r && (
        <div className="rounded-lg border border-emerald-200 bg-emerald-50 p-3 space-y-2">
          <div className="text-sm font-medium text-emerald-700">Pipeline 完成</div>
          <div className="flex flex-wrap gap-2 text-xs">
            <Tag color="blue">Beat 数量：{r.beat_count ?? '-'}</Tag>
            <Tag color={r.audit_passed ? 'green' : 'orange'}>
              审计评分：{r.audit_score ?? '-'} {r.audit_passed ? '✓' : '✗'}
            </Tag>
            <Tag>{r.target_model ?? '通用'}</Tag>
          </div>
          {r.audit_issues && r.audit_issues.length > 0 && (
            <div className="text-xs text-amber-700">
              <div className="font-medium">审计发现：</div>
              <ul className="list-disc list-inside">
                {(r.audit_issues as string[]).slice(0, 5).map((issue, i) => (
                  <li key={i}>{issue}</li>
                ))}
              </ul>
            </div>
          )}

          {/* Before/After comparison */}
          {originalPrompt && r?.prompt_text && (
            <div className="mt-3 pt-3 border-t border-emerald-200">
              <div className="text-xs font-medium text-emerald-700 mb-2">Prompt 对比</div>
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <div className="text-xs text-gray-500 mb-1">简单版（之前）</div>
                  <div className="text-xs bg-white rounded p-2 max-h-32 overflow-y-auto whitespace-pre-wrap break-all text-gray-600">
                    {originalPrompt}
                  </div>
                </div>
                <div>
                  <div className="text-xs text-emerald-600 mb-1">Pipeline 版（之后）</div>
                  <div className="text-xs bg-white rounded p-2 max-h-32 overflow-y-auto whitespace-pre-wrap break-all text-gray-800">
                    {r.prompt_text}
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Failure */}
      {isFailed && (
        <div className="rounded-lg border border-red-200 bg-red-50 p-3">
          <div className="text-sm text-red-700">
            Pipeline {status === 'failed' ? '执行失败' : '已取消'}
          </div>
        </div>
      )}

      {/* Live log */}
      <div className="text-xs text-gray-500 font-medium">执行日志</div>
      <TaskLogPanel taskId={taskId} maxHeight={200} />
    </div>
  )
}
