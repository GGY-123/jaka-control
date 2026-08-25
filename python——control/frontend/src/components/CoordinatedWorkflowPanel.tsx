import { useEffect, useState } from 'react'
import { AlertTriangle, CircleStop, ListChecks, Pause, Play, RefreshCw } from 'lucide-react'
import { api } from '../api'
import type { CoordinationRunState } from '../types'
import { btnDanger, btnGhost, btnSuccess, card } from '../ui'

const EMPTY: CoordinationRunState = {
  status: 'idle', index: -1, steps: 44, current_step: '', error: null, logs: [],
  a5_ip: '192.168.1.102', mini_ip: '192.168.1.103',
}

export default function CoordinatedWorkflowPanel({ connected }: { connected: boolean }) {
  const [state, setState] = useState<CoordinationRunState>(EMPTY)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')

  const refresh = async () => {
    try { setState(await api.coordinationState()) }
    catch (e) { setMessage((e as Error).message) }
  }
  useEffect(() => { refresh() }, [])
  useEffect(() => {
    if (state.status === 'running' || state.status === 'paused') {
      const timer = window.setInterval(refresh, 400)
      return () => window.clearInterval(timer)
    }
  }, [state.status])

  const start = async () => {
    if (!confirm('确认启动 A5 + JAKA Mini + 旋转夹爪协同流程？\n\n前提：A5 已位于“夹取点上方”；末端夹爪已连接并初始化；旋转夹爪已初始化、启用且 Action 就绪。\n\n任一步失败将立即停止后续步骤。')) return
    setBusy(true); setMessage('')
    try { setState(await api.runCoordination()); setMessage('协同流程已启动') }
    catch (e) { setMessage((e as Error).message) }
    finally { setBusy(false) }
  }
  const control = async (action: 'pause' | 'resume' | 'stop') => {
    setBusy(true); setMessage('')
    try { setState(await api.coordinationControl(action)) }
    catch (e) { setMessage((e as Error).message) }
    finally { setBusy(false) }
  }
  const active = state.status === 'running' || state.status === 'paused'

  return (
    <section className={`${card} p-4 border-brand-200`}>
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div>
          <div className="flex items-center gap-2">
            <ListChecks size={19} className="text-brand-600" />
            <h3 className="font-semibold text-slate-800">协同流程：紫色试管至橙色试管1</h3>
          </div>
          <p className="text-xs text-slate-500 mt-1">
            A5 ({state.a5_ip})、JAKA Mini ({state.mini_ip}) 与旋转夹爪严格串行；每一步完成成功后才执行下一步。
          </p>
        </div>
        <button className={btnGhost} onClick={refresh} disabled={busy || active} title="刷新协同流程状态">
          <RefreshCw size={15} /> 刷新
        </button>
      </div>

      {(message || state.error) && (
        <div className={`mt-3 text-sm border rounded-lg px-3 py-2 flex gap-2 ${state.error ? 'text-red-700 bg-red-50 border-red-200' : 'text-brand-700 bg-brand-50 border-brand-200'}`}>
          {state.error && <AlertTriangle size={16} className="shrink-0 mt-0.5" />}
          <span className="whitespace-pre-wrap">{state.error || message}</span>
        </div>
      )}

      <div className="mt-3 flex flex-wrap items-center gap-2">
        <button className={btnSuccess} onClick={start} disabled={!connected || busy || active}>
          <Play size={16} /> 启动协同流程
        </button>
        <button className={btnGhost} onClick={() => control('pause')} disabled={busy || state.status !== 'running'}>
          <Pause size={16} /> 暂停
        </button>
        <button className={btnGhost} onClick={() => control('resume')} disabled={busy || state.status !== 'paused'}>
          <Play size={16} /> 继续
        </button>
        <button className={btnDanger} onClick={() => control('stop')} disabled={busy || !active}>
          <CircleStop size={16} /> 停止
        </button>
        <span className={`ml-auto text-xs px-2.5 py-1 rounded-full font-medium ${
          state.status === 'running' ? 'bg-emerald-100 text-emerald-700' : state.status === 'paused' ? 'bg-amber-100 text-amber-700' : 'bg-slate-100 text-slate-500'
        }`}>
          {state.status === 'running' ? '运行中' : state.status === 'paused' ? '已暂停' : '待命'}
        </span>
      </div>

      <div className="mt-3 grid grid-cols-1 sm:grid-cols-2 gap-2 text-xs">
        <div className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2">
          当前步骤：<span className="font-medium text-slate-700">{state.current_step || '未启动'}</span>
        </div>
        <div className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2">
          进度：<span className="font-mono text-slate-700">{Math.max(0, state.index + 1)} / {state.steps}</span>
        </div>
      </div>

      <details className="mt-3 text-xs text-slate-600">
        <summary className="cursor-pointer select-none">执行日志与步骤清单</summary>
        <pre className="mt-2 max-h-40 overflow-auto rounded-lg bg-slate-950 text-slate-200 p-3 whitespace-pre-wrap">{state.logs.join('\n') || '尚未执行'}</pre>
      </details>
    </section>
  )
}
