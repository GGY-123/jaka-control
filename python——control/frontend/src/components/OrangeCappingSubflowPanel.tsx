import { useEffect, useState } from 'react'
import { AlertTriangle, CircleStop, ListChecks, MapPin, Pause, Play, RefreshCw } from 'lucide-react'
import { api } from '../api'
import type { TransferSubflowRunState, Waypoint } from '../types'
import { btnDanger, btnGhost, btnSuccess, card } from '../ui'

const EMPTY: TransferSubflowRunState = { status: 'idle', index: -1, steps: 96, current_step: '', error: null, logs: [], a5_ip: '192.168.1.102', mini_ip: '192.168.1.103' }

export default function OrangeCappingSubflowPanel({ connected, showControls = true }: { connected: boolean; showControls?: boolean }) {
  const [state, setState] = useState(EMPTY)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  const [points, setPoints] = useState<Waypoint[] | null>(null)
  const refresh = () => api.orangeCappingState().then(setState).catch((e) => setMessage((e as Error).message))
  useEffect(() => { refresh() }, [])
  useEffect(() => { if (state.status === 'running' || state.status === 'paused') { const timer = window.setInterval(refresh, 400); return () => window.clearInterval(timer) } }, [state.status])
  const active = state.status === 'running' || state.status === 'paused'
  const start = async () => {
    if (!confirm('启动橙色试管 1/2/3 盖盖子流程？\n\n前提：A5 已连接 192.168.1.102 并使能；末端夹爪已初始化；旋转夹爪已初始化、启用且 Action 就绪。每一步完成后才会执行下一步。')) return
    setBusy(true); setMessage('')
    try { setState(await api.runOrangeCapping()) } catch (e) { setMessage((e as Error).message) } finally { setBusy(false) }
  }
  const control = async (action: 'pause' | 'resume' | 'stop') => {
    setBusy(true); setMessage('')
    try { setState(await api.orangeCappingControl(action)) } catch (e) { setMessage((e as Error).message) } finally { setBusy(false) }
  }
  const viewPoints = async () => { try { setPoints(await api.orangeCappingPoints()) } catch (e) { setMessage((e as Error).message) } }
  return <section className={`${card} p-4 border-orange-200`}>
    <div className="flex items-start justify-between gap-3 flex-wrap"><div><div className="flex items-center gap-2"><ListChecks size={19} className="text-orange-600" /><h3 className="font-semibold text-slate-800">取液子流程：橙色试管 1/2/3 盖盖并放回</h3></div><p className="text-xs text-slate-500 mt-1">关盖时到过渡点后先下压 2 mm，逆时针一圈；第二圈与 A5 Z 下探 1 mm 同步进行。</p></div><button className={btnGhost} onClick={refresh} disabled={busy || active}><RefreshCw size={15} /> 刷新</button></div>
    {(message || state.error) && <div className={`mt-3 text-sm border rounded-lg px-3 py-2 flex gap-2 ${state.error ? 'text-red-700 bg-red-50 border-red-200' : 'text-orange-700 bg-orange-50 border-orange-200'}`}>{state.error && <AlertTriangle size={16} />}<span className="whitespace-pre-wrap">{state.error || message}</span></div>}
    {showControls && <div className="mt-3 flex flex-wrap items-center gap-2"><button className={btnSuccess} onClick={start} disabled={!connected || busy || active}><Play size={16} /> 启动橙色试管流程</button><button className={btnGhost} onClick={viewPoints} disabled={busy || active}><MapPin size={16} /> 查看所用点位</button><button className={btnGhost} onClick={() => control('pause')} disabled={busy || state.status !== 'running'}><Pause size={16} /> 暂停</button><button className={btnGhost} onClick={() => control('resume')} disabled={busy || state.status !== 'paused'}><Play size={16} /> 继续</button><button className={btnDanger} onClick={() => control('stop')} disabled={busy || !active}><CircleStop size={16} /> 停止</button><span className="ml-auto text-xs text-slate-600">进度 {Math.max(0, state.index + 1)} / {state.steps} · {state.status === 'running' ? '运行中' : state.status === 'paused' ? '已暂停' : '待命'}</span></div>}
    {points && <div className="mt-3 border border-slate-200 rounded-lg p-3 text-xs text-slate-600"><div className="font-medium text-slate-700 mb-2">点位管理中本流程使用的点位（{points.length}）</div><div className="grid grid-cols-1 sm:grid-cols-2 gap-1.5">{points.map((point) => <div key={point.id} className="rounded border border-slate-100 bg-slate-50 px-2 py-1"><span className="font-medium">{point.name}</span><span className="ml-2 font-mono text-slate-400">X{point.pose[0]?.toFixed(1)} Y{point.pose[1]?.toFixed(1)} Z{point.pose[2]?.toFixed(1)}</span></div>)}</div></div>}
    <details className="mt-3 text-xs text-slate-600"><summary className="cursor-pointer select-none">执行日志与步骤清单</summary><pre className="mt-2 max-h-40 overflow-auto rounded-lg bg-slate-950 text-slate-200 p-3 whitespace-pre-wrap">{state.logs.join('\n') || '尚未执行'}</pre></details>
  </section>
}
