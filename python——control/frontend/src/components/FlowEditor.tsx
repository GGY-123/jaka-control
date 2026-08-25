import { useEffect, useState } from 'react'
import {
  Play, Pause, Square, Save, Trash2, ChevronUp, ChevronDown, ListChecks, Plus, Grip,
} from 'lucide-react'
import { api } from '../api'
import type { Waypoint, Flow, FlowSegment, FlowRunState, CoordinationRunState, MoveType, GripperActionType } from '../types'
import { btnPrimary, btnGhost, btnSuccess, btnDanger, card, inputCls, labelCls } from '../ui'
import TransferSubflowPanel from './TransferSubflowPanel'
import OrangeCappingSubflowPanel from './OrangeCappingSubflowPanel'
import CombinedSubflowPanel from './CombinedSubflowPanel'

const MOVE_OPTS: { k: MoveType; label: string }[] = [
  { k: 'joint', label: '关节' },
  { k: 'linear', label: '直线' },
  { k: 'linear_z', label: '直线-Z' },
  { k: 'circular', label: '圆弧' },
]

const GRIPPER_OPTS: { k: GripperActionType; label: string }[] = [
  { k: 'none', label: '无动作' },
  { k: 'initialize', label: '初始化' },
  { k: 'open', label: '张开' },
  { k: 'close', label: '闭合' },
  { k: 'move_to', label: '移动到' },
  { k: 'set_force', label: '设力值' },
  { k: 'set_speed', label: '设速度' },
]


export default function FlowEditor({ connected }: { connected: boolean }) {
  const [points, setPoints] = useState<Waypoint[]>([])
  const [flows, setFlows] = useState<Flow[]>([])
  const [segs, setSegs] = useState<FlowSegment[]>([])
  const [name, setName] = useState('')
  const [curId, setCurId] = useState<string | null>(null)
  const [run, setRun] = useState<FlowRunState>({ status: 'idle', index: -1, flow_id: null, segments: 0, error: null })
  const [msg, setMsg] = useState('')
  const [transferState, setTransferState] = useState<CoordinationRunState>({ status: 'idle', index: -1, steps: 32, current_step: '', error: null, logs: [], a5_ip: '192.168.1.102', mini_ip: '192.168.1.103' })
  const [orangeState, setOrangeState] = useState<CoordinationRunState>({ status: 'idle', index: -1, steps: 96, current_step: '', error: null, logs: [], a5_ip: '192.168.1.102', mini_ip: '192.168.1.103' })
  const [combinedState, setCombinedState] = useState<CoordinationRunState>({ status: 'idle', index: -1, steps: 123, current_step: '', error: null, logs: [], a5_ip: '192.168.1.102', mini_ip: '192.168.1.103' })
  const [processTarget, setProcessTarget] = useState<'saved' | 'transfer' | 'orange' | 'combined'>('saved')
  const [processBusy, setProcessBusy] = useState(false)


  const loadAll = () => {
    api.points().then(setPoints).catch(() => {})
    api.flows().then(setFlows).catch(() => {})
  }
  useEffect(() => { loadAll() }, [])
  useEffect(() => {
    const refreshSubflows = () => {
      api.transferSubflowState().then(setTransferState).catch(() => {})
      api.orangeCappingState().then(setOrangeState).catch(() => {})
      api.combinedSubflowState().then(setCombinedState).catch(() => {})
    }
    refreshSubflows()
    const timer = window.setInterval(refreshSubflows, 500)
    return () => window.clearInterval(timer)
  }, [])
  useEffect(() => {
    if (run.status === 'running' || run.status === 'paused') {
      const t = setInterval(() => api.flowState().then(setRun).catch(() => {}), 400)
      return () => clearInterval(t)
    }
  }, [run.status])

  const addSeg = (p: Waypoint) =>
    setSegs((s) => [...s, { point_id: p.id, move_type: 'linear', speed: 50, acc: 100, tol: 0.1, wait_after_arrival: 0, gripper: { type: 'none', delay: 0 } }])
  const rmSeg = (i: number) => setSegs((s) => s.filter((_, j) => j !== i))
  const reorder = (i: number, d: number) => {
    const n = [...segs]
    const j = i + d
    if (j < 0 || j >= n.length) return
    ;[n[i], n[j]] = [n[j], n[i]]
    setSegs(n)
  }
  const updSeg = (i: number, patch: Partial<FlowSegment>) =>
    setSegs((s) => s.map((seg, j) => (j === i ? { ...seg, ...patch } : seg)))
  const updG = (i: number, patch: Partial<NonNullable<FlowSegment['gripper']>>) =>
    setSegs((s) => s.map((seg, j) => (j === i ? { ...seg, gripper: { type: 'none', delay: 0, ...seg.gripper, ...patch } } : seg)))
  const clearAll = () => { setSegs([]); setName(''); setCurId(null); setMsg('') }

  const importJakaMini = async () => {
    try {
      const result = await api.importJakaMiniFlow()
      setCurId(result.flow.id)
      setName(result.flow.name)
      setSegs(result.flow.segments.map((s) => ({ ...s })))
      setMsg(result.message)
      setFlows(await api.flows())
      setPoints(await api.points())
    } catch (e) { setMsg((e as Error).message) }
  }

  const saveFlow = async () => {
    if (!name.trim()) { setMsg('请输入流程名称'); return }
    if (segs.length === 0) { setMsg('流程至少需要 1 个点位'); return }
    try {
      if (curId) {
        await api.updateFlow(curId, name, segs)
        setMsg('流程已更新')
      } else {
        const f = await api.saveFlow(name, segs)
        setCurId(f.id)
        setMsg('流程已保存')
      }
      api.flows().then(setFlows)
    } catch (e) { setMsg((e as Error).message) }
  }

  const loadFlow = (f: Flow) => {
    setCurId(f.id); setName(f.name); setSegs(f.segments.map((s) => ({ ...s })))
    setMsg(`已加载流程「${f.name}」`)
  }

  const delFlow = async (f: Flow) => {
    if (!confirm(`删除流程「${f.name}」?`)) return
    await api.deleteFlow(f.id)
    if (curId === f.id) clearAll()
    api.flows().then(setFlows)
  }

  const start = async () => {
    if (!curId) { setMsg('请先保存流程'); return }
    if (!connected) { setMsg('未连接机械臂'); return }
    try {
      setRun(await api.runFlow(curId))
      setMsg('流程开始执行')
    } catch (e) { setMsg((e as Error).message) }
  }
  const processState = processTarget === 'saved' ? run : processTarget === 'transfer' ? transferState : processTarget === 'orange' ? orangeState : combinedState
  const processActive = processState.status === 'running' || processState.status === 'paused'
  const processControl = async (action: 'start' | 'pause' | 'resume' | 'stop') => {
    setProcessBusy(true); setMsg('')
    try {
      if (processTarget === 'saved') {
        if (action === 'start') setRun(await api.runFlow(curId!))
        else setRun(await api.flowControl(action))
      } else if (processTarget === 'transfer') {
        if (action === 'start') setTransferState(await api.runTransferSubflow())
        else setTransferState(await api.transferSubflowControl(action))
      } else if (processTarget === 'orange') {
        if (action === 'start') setOrangeState(await api.runOrangeCapping())
        else setOrangeState(await api.orangeCappingControl(action))
      } else {
        if (action === 'start') setCombinedState(await api.runCombinedSubflow())
        else setCombinedState(await api.combinedSubflowControl(action))
      }
    } catch (e) { setMsg((e as Error).message) }
    finally { setProcessBusy(false) }
  }

  const ptName = (id: string) => points.find((p) => p.id === id)?.name ?? '?'

  return (
      <div className="space-y-4">
      {msg && <div className="text-sm text-brand-700 bg-brand-50 border border-brand-200 rounded-lg px-3 py-2">{msg}</div>}
      {run.error && <div className="text-sm text-red-700 bg-red-50 border border-red-200 rounded-lg px-3 py-2 whitespace-pre-wrap">{run.error}</div>}

      {/* 运行控制条 */}
      <div className={`${card} p-4`}>
        <div className="flex flex-wrap items-center gap-3">
          <div className="flex items-center gap-2">
            <select value={processTarget} onChange={(e) => setProcessTarget(e.target.value as typeof processTarget)} className={`${inputCls} py-1.5`} disabled={processBusy || processActive}>
              <option value="saved">当前已加载流程</option><option value="transfer">取液子流程：紫色试管</option><option value="orange">橙色流程：开盖 → 滴液 → 盖回（1/2/3）</option><option value="combined">总流程：紫色取液 → 橙色三管开盖滴液盖回</option>
            </select>
            <button className={btnSuccess} onClick={() => processControl('start')} disabled={!connected || processBusy || processActive || (processTarget === 'saved' && !curId)}>
              <Play size={16} /> 开始
            </button>
            <button className={btnGhost} onClick={() => processControl('pause')} disabled={processBusy || processState.status !== 'running'}>
              <Pause size={16} /> 暂停
            </button>
            <button className={btnGhost} onClick={() => processControl('resume')} disabled={processBusy || processState.status !== 'paused'}>
              <Play size={16} /> 继续
            </button>
            <button className={btnDanger} onClick={() => processControl('stop')} disabled={processBusy || !processActive}>
              <Square size={16} /> 停止
            </button>
          </div>
          <div className="ml-auto flex items-center gap-3">
            <span className={`text-xs px-2.5 py-1 rounded-full font-medium ${
              processState.status === 'running' ? 'bg-emerald-100 text-emerald-700'
              : processState.status === 'paused' ? 'bg-amber-100 text-amber-700'
              : processState.status === 'stopped' ? 'bg-red-100 text-red-700'
              : 'bg-slate-100 text-slate-500'}`}>
              {processState.status === 'idle' ? '空闲' : processState.status === 'running' ? '运行中' : processState.status === 'paused' ? '已暂停' : '已停止'}
            </span>
            {processActive && <span className="text-sm text-slate-600">进度 {processState.index + 1} / {'steps' in processState ? processState.steps : processState.segments}</span>}
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* 点位选择 */}
        <div className={`${card} p-4`}>
          <h3 className="font-semibold text-slate-700 mb-3 flex items-center gap-2">
            <Plus size={18} className="text-brand-600" /> 点位选择
          </h3>
          <div className="text-xs text-slate-400 mb-2">点击点位追加到流程</div>
          <div className="space-y-1 max-h-96 overflow-y-auto">
            {points.length === 0 && <div className="text-sm text-slate-400 py-4 text-center">暂无点位</div>}
            {points.map((p) => (
              <button key={p.id} onClick={() => addSeg(p)}
                className="w-full text-left px-3 py-2 rounded-lg border border-slate-200 hover:bg-brand-50 hover:border-brand-300 text-sm">
                <div className="flex items-baseline gap-2">
                  <span className="font-medium text-slate-700">{p.name}</span>
                  <span className="text-xs text-slate-400 font-mono">
                    X{p.pose[0]?.toFixed(0)} Y{p.pose[1]?.toFixed(0)} Z{p.pose[2]?.toFixed(0)}
                  </span>
                </div>
                {p.note && <div className="text-xs text-slate-500 mt-0.5 truncate">📝 {p.note}</div>}
              </button>
            ))}
          </div>
        </div>

        {/* 流程段编辑 */}
        <div className={`${card} p-4 lg:col-span-2`}>
          <div className="flex items-center justify-between mb-3">
            <h3 className="font-semibold text-slate-700 flex items-center gap-2">
              <ListChecks size={18} className="text-brand-600" /> 运动流程
            </h3>
            <button className={btnGhost} onClick={clearAll}><Trash2 size={15} /> 清空</button>
          </div>

          <div className="space-y-2 max-h-[28rem] overflow-y-auto">
            {segs.length === 0 && <div className="text-sm text-slate-400 py-8 text-center">从左侧点选点位以编排流程</div>}
            {segs.map((s, i) => {
              const pt = points.find((p) => p.id === s.point_id)
              return (
              <div key={i} className={`border rounded-lg p-2 flex flex-col gap-2 ${run.status === 'running' && run.index === i ? 'border-brand-400 bg-brand-50' : 'border-slate-200'}`}>
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="w-6 h-6 rounded-full bg-slate-100 text-slate-500 text-xs flex items-center justify-center font-medium">{i + 1}</span>
                  <span className="font-medium text-slate-700 min-w-[80px]">{ptName(s.point_id)}</span>
                  <select value={s.move_type} onChange={(e) => updSeg(i, { move_type: e.target.value as MoveType })}
                    className={`${inputCls} py-1`}>
                    {MOVE_OPTS.map((m) => <option key={m.k} value={m.k}>{m.label}</option>)}
                  </select>
                  <div className="flex items-center gap-1">
                    <span className="text-xs text-slate-400">速度</span>
                    <input type="number" min={1} max={3000} value={s.speed} onChange={(e) => updSeg(i, { speed: Math.max(1, +e.target.value || 1) })} className={`${inputCls} w-20 py-1`} />
                  </div>
                  <div className="flex items-center gap-1">
                    <span className="text-xs text-slate-400">到位等待</span>
                    <input type="number" min={0} max={60} step={0.5} value={s.wait_after_arrival ?? 0}
                      onChange={(e) => updSeg(i, { wait_after_arrival: Math.max(0, +e.target.value || 0) })}
                      className={`${inputCls} w-16 py-1`} />
                    <span className="text-xs text-slate-400">s</span>
                  </div>
                  <div className="ml-auto flex items-center gap-1">
                    <button className={btnGhost} onClick={() => reorder(i, -1)} disabled={i === 0}><ChevronUp size={15} /></button>
                    <button className={btnGhost} onClick={() => reorder(i, 1)} disabled={i === segs.length - 1}><ChevronDown size={15} /></button>
                    <button className={btnDanger} onClick={() => rmSeg(i)}><Trash2 size={15} /></button>
                  </div>
                </div>
                {pt?.note && <div className="text-xs text-slate-500 pl-8">📝 {pt.note}</div>}
                <div className="flex items-center gap-2 flex-wrap pl-8">
                  <Grip size={14} className="text-brand-600" />
                  <span className="text-xs text-slate-400">夹爪</span>
                  <select value={s.gripper?.type ?? 'none'} onChange={(e) => updG(i, { type: e.target.value as GripperActionType })}
                    className={`${inputCls} py-1`}>
                    {GRIPPER_OPTS.map((g) => <option key={g.k} value={g.k}>{g.label}</option>)}
                  </select>
                  {s.gripper?.type === 'move_to' && (
                    <div className="flex items-center gap-1">
                      <span className="text-xs text-slate-400">位置(0-1000)</span>
                      <input type="number" min={0} max={1000} value={s.gripper.position ?? 0}
                        onChange={(e) => updG(i, { position: Math.max(0, Math.min(1000, +e.target.value || 0)) })}
                        className={`${inputCls} w-24 py-1`} />
                    </div>
                  )}
                  {s.gripper?.type === 'set_force' && (
                    <div className="flex items-center gap-1">
                      <span className="text-xs text-slate-400">力值(20-100)</span>
                      <input type="number" min={20} max={100} value={s.gripper.force ?? 30}
                        onChange={(e) => updG(i, { force: Math.max(20, Math.min(100, +e.target.value || 20)) })}
                        className={`${inputCls} w-24 py-1`} />
                    </div>
                  )}
                  {s.gripper?.type === 'set_speed' && (
                    <div className="flex items-center gap-1">
                      <span className="text-xs text-slate-400">速度(1-100)</span>
                      <input type="number" min={1} max={100} value={s.gripper.speed ?? 50}
                        onChange={(e) => updG(i, { speed: Math.max(1, Math.min(100, +e.target.value || 1)) })}
                        className={`${inputCls} w-24 py-1`} />
                    </div>
                  )}
                  {s.gripper && s.gripper.type !== 'none' && (
                    <div className="flex items-center gap-1">
                      <span className="text-xs text-slate-400">延迟(s)</span>
                      <input type="number" min={0} max={30} step={0.1} value={s.gripper.delay ?? 0}
                        onChange={(e) => updG(i, { delay: Math.max(0, +e.target.value || 0) })}
                        className={`${inputCls} w-20 py-1`} />
                    </div>
                  )}
                </div>
              </div>
              );
            })}
          </div>

          <div className="mt-4 flex flex-wrap items-center gap-2 pt-3 border-t border-slate-100">
            <div className={labelCls}>流程名称</div>
            <input value={name} onChange={(e) => setName(e.target.value)} className={`${inputCls} flex-1 min-w-[160px]`} placeholder="如: 取放循环1" />
            <button className={btnPrimary} onClick={saveFlow}><Save size={16} /> 保存流程</button>
          </div>
        </div>
      </div>

      <div className={`${card} p-4`}>
        <h3 className="font-semibold text-slate-700 mb-3">流程库与子流程</h3>
        <div className="space-y-3">
          <div className="flex items-center justify-between gap-3 flex-wrap"><span className="font-medium text-slate-700">已保存流程 ({flows.length})</span><button className={btnGhost} onClick={importJakaMini}><Plus size={15} /> 导入 JAKA Mini 点位流程</button></div>
          <div className="space-y-2">{flows.length === 0 && <div className="text-sm text-slate-400 py-2 text-center">暂无保存的流程</div>}{flows.map((f) => <div key={f.id} className="flex items-center gap-3 border border-slate-200 rounded-lg px-3 py-2"><div className="flex-1"><span className="font-medium text-slate-700">{f.name}</span><span className="ml-2 text-xs text-slate-400">{f.segments.length} 段 · {f.created_at}</span></div><button className={btnGhost} onClick={() => loadFlow(f)}>加载</button><button className={btnDanger} onClick={() => delFlow(f)}><Trash2 size={15} /></button></div>)}</div>
          <TransferSubflowPanel connected={connected} showControls={false} />
          <OrangeCappingSubflowPanel connected={connected} showControls={false} />
          <CombinedSubflowPanel />
        </div>
      </div>
    </div>
  )
}
