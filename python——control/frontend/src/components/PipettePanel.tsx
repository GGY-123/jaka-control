import { useEffect, useState } from 'react'
import { Droplets, Plug, PlugZap, RefreshCw, RotateCw, Waves, Wind } from 'lucide-react'
import { api } from '../api'
import type { PipetteStatus } from '../types'
import { btnDanger, btnGhost, btnPrimary, btnSuccess, card, inputCls, labelCls } from '../ui'

export default function PipettePanel() {
  const [st, setSt] = useState<PipetteStatus | null>(null)
  const [port, setPort] = useState('')
  const [address, setAddress] = useState('02')
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')

  const refresh = () => api.pipetteInfo().then((value) => { setSt(value); if (!port && value.port) setPort(value.port) }).catch(() => {})
  useEffect(() => { refresh() }, [])

  const act = async (label: string, fn: () => Promise<PipetteStatus>) => {
    setBusy(true); setMessage('')
    try { setSt(await fn()); setMessage(`${label}完成`) }
    catch (e) { setMessage(`${label}失败: ${(e as Error).message}`); refresh() }
    finally { setBusy(false) }
  }
  const connected = !!st?.connected

  return (
    <div className={`${card} p-4`}>
      <div className="flex items-center justify-between gap-3 flex-wrap mb-3">
        <h3 className="font-semibold text-slate-700 flex items-center gap-2"><Droplets size={18} className="text-brand-600" /> ADP 移液枪（RS485）</h3>
        <span className={`text-xs px-2.5 py-1 rounded-full font-medium ${connected ? 'bg-emerald-100 text-emerald-700' : 'bg-slate-100 text-slate-500'}`}>{connected ? '已连接' : '未连接'}</span>
      </div>
      {message && <div className="text-xs text-brand-700 bg-brand-50 border border-brand-200 rounded px-2 py-1 mb-3 break-words">{message}</div>}
      <div className="flex flex-wrap items-end gap-2">
        <label><span className={`${labelCls} block mb-1`}>RS485 串口</span><input value={port} onChange={(e) => setPort(e.target.value)} placeholder="如 /dev/ttyUSB2" className={`${inputCls} w-44`} disabled={connected || busy} /></label>
        <label><span className={`${labelCls} block mb-1`}>设备地址</span><input value={address} onChange={(e) => setAddress(e.target.value)} className={`${inputCls} w-20`} disabled={connected || busy} /></label>
        {!connected ? <button className={btnSuccess} onClick={() => act('连接', () => api.pipetteConnect(port || undefined, address))} disabled={busy}><Plug size={15} /> 连接</button> : <button className={btnDanger} onClick={() => act('断开', api.pipetteDisconnect)} disabled={busy}><PlugZap size={15} /> 断开</button>}
        <button className={btnGhost} onClick={refresh} disabled={busy}><RefreshCw size={15} /> 刷新</button>
      </div>
      <div className="flex flex-wrap gap-2 mt-3">
        <button className={btnPrimary} onClick={() => act('初始化', api.pipetteInitialize)} disabled={!connected || busy}><RotateCw size={15} /> 初始化回原点</button>
        <button className={btnGhost} onClick={() => act('Tip 检查', api.pipetteTip)} disabled={!connected || busy}><Wind size={15} /> 检查 Tip</button>
        <button className={btnGhost} onClick={() => act('状态查询', () => api.pipetteAction('status'))} disabled={!connected || busy}>状态</button>
      </div>
      <div className="grid grid-cols-2 sm:grid-cols-3 gap-2 mt-3">
        <button className={btnGhost} onClick={() => act('首次空气回吸', () => api.pipetteAction('air'))} disabled={!connected || !st?.initialized || busy}><Waves size={15} /> 空气回吸 30uL</button>
        <button className={btnPrimary} onClick={() => act('吸液', () => api.pipetteAction('aspirate'))} disabled={!connected || !st?.initialized || busy}>吸液 600uL</button>
        <button className={btnGhost} onClick={() => act('二次回吸', () => api.pipetteAction('tail'))} disabled={!connected || !st?.initialized || busy}>二次回吸</button>
        <button className={btnSuccess} onClick={() => act('排液', () => api.pipetteAction('dispense'))} disabled={!connected || !st?.initialized || busy}>排液 200uL</button>
        <button className={btnDanger} onClick={() => act('排空', () => api.pipetteAction('flush'))} disabled={!connected || !st?.initialized || busy}>排空 Tip</button>
      </div>
      <div className="text-xs text-slate-500 mt-3">流程：初始化 → 检查 Tip → 空气回吸 → 将 Tip 放入液体 → 吸液 → 抬离液面 → 二次回吸 → 每次排液 200uL（共 3 次）。</div>
      <div className="text-xs text-slate-400 mt-1">{st ? `端口 ${st.port || '-'} · 地址 ${st.address} · 剩余排液批次 ${st.remaining_batches}` : '尚未读取状态'}</div>
    </div>
  )
}
