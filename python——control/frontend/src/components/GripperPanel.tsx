import { useEffect, useState } from 'react'
import { Grip, Plug, PlugZap, RotateCw, ChevronsUp, ChevronsDown, Move, SlidersHorizontal } from 'lucide-react'
import { api } from '../api'
import type { GripperInfo, GripperStatus } from '../types'
import { btnPrimary, btnGhost, btnSuccess, btnDanger, card, inputCls, labelCls } from '../ui'

export default function GripperPanel() {
  const [info, setInfo] = useState<GripperInfo | null>(null)
  const [st, setSt] = useState<GripperStatus | null>(null)
  const [port, setPort] = useState('')
  const [force, setForce] = useState(25)
  const [speed, setSpeed] = useState(50)
  const [pos, setPos] = useState(0)
  const [msg, setMsg] = useState('')
  const [busy, setBusy] = useState(false)

  const refresh = () => {
    api.gripperInfo().then(setInfo).catch(() => {})
    api.gripperStatus().then(setSt).catch(() => {})
  }
  useEffect(() => { refresh() }, [])
  useEffect(() => {
    if (st?.connected) {
      const t = setInterval(() => api.gripperStatus().then(setSt).catch(() => {}), 500)
      return () => clearInterval(t)
    }
  }, [st?.connected])
  useEffect(() => {
    if (info && !port) setPort(info.default_port || '')
  }, [info])

  const act = async (fn: () => Promise<unknown>, label: string) => {
    setBusy(true)
    try { await fn(); setMsg(`${label} 完成`); refresh() }
    catch (e) { setMsg(`${label} 失败: ${(e as Error).message}`) }
    finally { setBusy(false) }
  }

  const connected = st?.connected ?? false
  const ranges = info?.ranges ?? st?.ranges

  return (
    <div className={`${card} p-4`}>
      <h3 className="font-semibold text-slate-700 mb-3 flex items-center gap-2">
        <Grip size={18} className="text-brand-600" /> 末端夹爪控制
      </h3>

      {msg && <div className="text-xs text-brand-700 bg-brand-50 border border-brand-200 rounded px-2 py-1 mb-2">{msg}</div>}

      <div className="flex flex-wrap items-end gap-2 mb-3">
        <div>
          <div className={`${labelCls} mb-1`}>串口</div>
          <input value={port} onChange={(e) => setPort(e.target.value)} placeholder="如 COM5"
            className={`${inputCls} w-28`} disabled={connected} />
        </div>
        {!connected ? (
          <button className={btnSuccess} disabled={busy}
            onClick={() => act(() => api.gripperConnect(port || undefined), '连接夹爪')}>
            <Plug size={15} /> 连接
          </button>
        ) : (
          <button className={btnDanger} disabled={busy}
            onClick={() => act(() => api.gripperDisconnect(), '断开夹爪')}>
            <PlugZap size={15} /> 断开
          </button>
        )}
        <span className={`text-xs px-2.5 py-1 rounded-full font-medium ml-auto ${
          connected ? 'bg-emerald-100 text-emerald-700' : 'bg-slate-100 text-slate-500'}`}>
          {connected ? (info?.sim ? '已连接(仿真)' : '已连接') : '未连接'}
        </span>
      </div>

      <div className="flex flex-wrap items-end gap-2 mb-3">
        <div>
          <div className={`${labelCls} mb-1`}>力值 {ranges ? `(${ranges.force[0]}-${ranges.force[1]})` : '(20-100)'}</div>
          <input type="number" min={ranges?.force[0] ?? 20} max={ranges?.force[1] ?? 100}
            value={force} onChange={(e) => setForce(Math.max(ranges?.force[0] ?? 20, Math.min(ranges?.force[1] ?? 100, +e.target.value || 20)))}
            className={`${inputCls} w-20`} disabled={!connected || busy} />
        </div>
        <div>
          <div className={`${labelCls} mb-1`}>速度 {ranges ? `(${ranges.speed[0]}-${ranges.speed[1]})` : '(1-100)'}</div>
          <input type="number" min={ranges?.speed[0] ?? 1} max={ranges?.speed[1] ?? 100}
            value={speed} onChange={(e) => setSpeed(Math.max(ranges?.speed[0] ?? 1, Math.min(ranges?.speed[1] ?? 100, +e.target.value || 1)))}
            className={`${inputCls} w-20`} disabled={!connected || busy} />
        </div>
        <button className={btnGhost} disabled={!connected || busy}
          onClick={() => act(() => api.gripperSetParams(force, speed), '设参数')}>
          <SlidersHorizontal size={15} /> 应用
        </button>
      </div>

      <div className="flex flex-wrap items-end gap-2 mb-3">
        <div>
          <div className={`${labelCls} mb-1`}>位置 {ranges ? `(${ranges.position[0]}-${ranges.position[1]})` : '(0-1000)'}</div>
          <input type="number" min={ranges?.position[0] ?? 0} max={ranges?.position[1] ?? 1000}
            value={pos} onChange={(e) => setPos(+e.target.value || 0)}
            className={`${inputCls} w-20`} disabled={!connected || busy} />
        </div>
        <button className={btnPrimary} disabled={!connected || busy}
          onClick={() => act(() => api.gripperMove(pos), '移动到')}>
          <Move size={15} /> 移动到
        </button>
        <button className={btnGhost} disabled={!connected || busy}
          onClick={() => act(() => api.gripperOpen(), '张开')}>
          <ChevronsUp size={15} /> 张开
        </button>
        <button className={btnGhost} disabled={!connected || busy}
          onClick={() => act(() => api.gripperClose(), '闭合')}>
          <ChevronsDown size={15} /> 闭合
        </button>
        <button className={btnGhost} disabled={!connected || busy}
          onClick={() => act(() => api.gripperInitialize(), '初始化')}>
          <RotateCw size={15} /> 初始化
        </button>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs">
        <div className="rounded-lg bg-slate-50 border border-slate-200 px-2 py-1.5">
          <span className="text-slate-400 mr-1">位置</span>
          <span className="font-mono text-slate-700">{st?.position ?? '-'}</span>
        </div>
        <div className="rounded-lg bg-slate-50 border border-slate-200 px-2 py-1.5">
          <span className="text-slate-400 mr-1">力值</span>
          <span className="font-mono text-slate-700">{st?.force ?? '-'}</span>
        </div>
        <div className="rounded-lg bg-slate-50 border border-slate-200 px-2 py-1.5">
          <span className="text-slate-400 mr-1">速度</span>
          <span className="font-mono text-slate-700">{st?.speed ?? '-'}</span>
        </div>
        <div className="rounded-lg bg-slate-50 border border-slate-200 px-2 py-1.5">
          <span className="text-slate-400 mr-1">状态</span>
          <span className={`font-medium ${st?.moving ? 'text-amber-600' : 'text-emerald-600'}`}>
            {!connected ? '-' : st?.moving ? '运动中' : st?.initialized ? '就绪' : '未初始化'}
          </span>
        </div>
      </div>
    </div>
  )
}
