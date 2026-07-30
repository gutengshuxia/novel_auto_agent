/**
 * TaskLogPanel - 任务执行日志面板
 *
 * 轮询获取任务执行日志并以时间线形式展示。
 * 支持增量拉取（afterId），每 2 秒刷新一次。
 */

import { useEffect, useRef, useState } from 'react'
import { fetchTaskLogs, type TaskLogEntry } from '../chapterDivisionTasks'

type TaskLogPanelProps = {
  taskId: string | null
  maxHeight?: number
}

const LEVEL_STYLES: Record<string, { color: string; icon: string }> = {
  info: { color: '#1677ff', icon: '●' },
  success: { color: '#52c41a', icon: '✓' },
  warn: { color: '#faad14', icon: '⚠' },
  error: { color: '#ff4d4f', icon: '✗' },
}

function formatTime(ts: number): string {
  if (!ts) return ''
  const d = new Date(ts * 1000)
  return d.toLocaleTimeString('zh-CN', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' })
}

export default function TaskLogPanel({ taskId, maxHeight = 240 }: TaskLogPanelProps) {
  const [logs, setLogs] = useState<TaskLogEntry[]>([])
  const lastIdRef = useRef(0)
  const scrollRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!taskId) {
      setLogs([])
      lastIdRef.current = 0
      return
    }

    let cancelled = false
    let timer: number | null = null

    const poll = async () => {
      try {
        const newLogs = await fetchTaskLogs(taskId, lastIdRef.current)
        if (cancelled) return
        if (newLogs.length > 0) {
          setLogs((prev) => [...prev, ...newLogs])
          lastIdRef.current = newLogs[newLogs.length - 1].id
        }
        timer = window.setTimeout(() => { void poll() }, 2000)
      } catch {
        if (!cancelled) {
          timer = window.setTimeout(() => { void poll() }, 3000)
        }
      }
    }

    void poll()
    return () => {
      cancelled = true
      if (timer !== null) window.clearTimeout(timer)
    }
  }, [taskId])

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [logs])

  if (!taskId) return null
  if (logs.length === 0) {
    return (
      <div className="text-xs text-gray-400 py-2 px-3">
        等待执行日志...
      </div>
    )
  }

  return (
    <div
      ref={scrollRef}
      className="bg-gray-900 rounded-md overflow-y-auto text-xs font-mono"
      style={{ maxHeight }}
    >
      <div className="p-2 space-y-0.5">
        {logs.map((entry) => {
          const style = LEVEL_STYLES[entry.level] || LEVEL_STYLES.info
          return (
            <div key={entry.id} className="flex items-start gap-2 leading-5">
              <span className="text-gray-500 shrink-0">{formatTime(entry.timestamp)}</span>
              <span style={{ color: style.color }} className="shrink-0">{style.icon}</span>
              <span className="text-gray-200 break-all">{entry.message}</span>
            </div>
          )
        })}
      </div>
    </div>
  )
}
