import { useEffect, useState } from 'react'
import { ListChecks, MapPin, RefreshCw } from 'lucide-react'
import { api } from '../api'
import type { TransferSubflowRunState, Waypoint } from '../types'
import { btnGhost, card } from '../ui'

const EMPTY: TransferSubflowRunState = { status: 'idle', index: -1, steps: 123, current_step: '', error: null, logs: [], a5_ip: '192.168.1.102', mini_ip: '192.168.1.103' }

export default function CombinedSubflowPanel() {
  const [state, setState] = useState(EMPTY)
  const [points, setPoints] = useState<Waypoint[] | null>(null)
  const refresh = () => api.combinedSubflowState().then(setState).catch(() => {})
  useEffect(() => { refresh(); const timer = window.setInterval(refresh, 500); return () => window.clearInterval(timer) }, [])
  const viewPoints = async () => setPoints(await api.combinedSubflowPoints())
  return <section className={`${card} p-4 border-sky-200`}>
    <div className="flex items-start justify-between gap-3 flex-wrap"><div><div className="flex items-center gap-2"><ListChecks size={19} className="text-sky-600" /><h3 className="font-semibold text-slate-800">总流程：紫色取液 → 橙色试管 1/2/3</h3></div><p className="text-xs text-slate-500 mt-1">紫色试管吸取 600 uL 后，依次对三支橙色试管开盖、滴液、盖回并放回。</p></div><button className={btnGhost} onClick={refresh}><RefreshCw size={15} /> 刷新</button></div>
    <div className="mt-3 flex flex-wrap items-center gap-3 text-xs text-slate-600"><span>阶段：<b>{state.phase === 'transfer' ? '紫色取液' : state.phase === 'orange' ? '橙色开盖滴液盖回' : '待命'}</b></span><span>进度：<b>{Math.max(0, state.index + 1)} / {state.steps}</b></span><span>状态：<b>{state.status === 'running' ? '运行中' : state.status === 'paused' ? '已暂停' : state.error ? '异常' : '待命'}</b></span><button className={btnGhost} onClick={viewPoints}><MapPin size={15} /> 查看总流程点位</button></div>
    {state.error && <div className="mt-2 text-sm text-red-700 bg-red-50 border border-red-200 rounded-lg px-3 py-2 whitespace-pre-wrap">{state.error}</div>}
    {points && <div className="mt-3 text-xs text-slate-600 border border-slate-200 rounded-lg p-3">共 {points.length} 个点位：{points.map((point) => point.name).join('、')}</div>}
    <details className="mt-3 text-xs text-slate-600"><summary className="cursor-pointer select-none">总流程日志</summary><pre className="mt-2 max-h-40 overflow-auto rounded-lg bg-slate-950 text-slate-200 p-3 whitespace-pre-wrap">{state.logs.join('\n') || '尚未执行'}</pre></details>
  </section>
}
