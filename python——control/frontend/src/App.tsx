import { useEffect, useState, useCallback } from 'react'
import {
  Activity, Gamepad2, MapPin, ListChecks, Bot, Plug, PlugZap, AlertCircle,
  Zap, ZapOff, Power, PowerOff, RotateCw,
} from 'lucide-react'
import { api } from './api'
import type { RobotStatus } from './types'
import { btnPrimary, btnDanger, btnGhost, btnSuccess, btn, inputCls, card } from './ui'
import StatusPanel from './components/StatusPanel'
import ManualControl from './components/ManualControl'
import WaypointManager from './components/WaypointManager'
import FlowEditor from './components/FlowEditor'
import ZergPanel from './components/ZergPanel'

type Tab = 'status' | 'manual' | 'points' | 'flow' | 'zerg'
const TABS: { key: Tab; label: string; icon: typeof Activity }[] = [
  { key: 'status', label: '状态监控', icon: Activity },
  { key: 'manual', label: '手动控制', icon: Gamepad2 },
  { key: 'points', label: '点位管理', icon: MapPin },
  { key: 'flow', label: '流程编辑', icon: ListChecks },
  { key: 'zerg', label: '旋转夹爪', icon: RotateCw },
]

export default function App() {
  const [tab, setTab] = useState<Tab>('status')
  const [connected, setConnected] = useState(false)
  const [sim, setSim] = useState(false)
  const [ip, setIp] = useState('10.5.5.100')
  const [status, setStatus] = useState<RobotStatus>({ connected: false })
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)
  const [pwBusy, setPwBusy] = useState(false)

  useEffect(() => {
    api.info().then((i) => { setSim(i.sim); setIp(i.default_ip) }).catch(() => {})
  }, [])

  const poll = useCallback(() => {
    api.status().then((s) => { setStatus(s); setConnected(s.connected) }).catch(() => {})
  }, [])

  useEffect(() => {
    if (!connected) return
    poll()
    const t = setInterval(poll, 500)
    return () => clearInterval(t)
  }, [connected, poll])

  const doConnect = async () => {
    setBusy(true); setErr('')
    try {
      await api.connect(ip)
      setConnected(true)
      poll()
    } catch (e) {
      setErr((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  const doDisconnect = async () => {
    setBusy(true)
    try {
      await api.disconnect()
    } catch {
      /* ignore */
    } finally {
      setConnected(false)
      setBusy(false)
      setStatus({ connected: false })
    }
  }

  const runPw = async (fn: () => Promise<unknown>, label: string) => {
    setPwBusy(true); setErr('')
    try {
      await fn()
      poll()
    } catch (e) {
      setErr(label + '：' + (e as Error).message)
    } finally {
      setPwBusy(false)
    }
  }

  const powered = !!status.powered
  const enabled = !!status.enabled

  return (
    <div className="min-h-screen flex flex-col">
      <header className="bg-white border-b border-slate-200 sticky top-0 z-10">
        <div className="max-w-7xl mx-auto px-4 py-3 flex items-center gap-3 flex-wrap">
          <div className="flex items-center gap-2">
            <div className="w-9 h-9 rounded-lg bg-brand-600 text-white flex items-center justify-center">
              <Bot size={20} />
            </div>
            <h1 className="text-lg font-semibold text-slate-800">机械臂控制与点位管理系统</h1>
            {sim && (
              <span className="text-xs px-2 py-0.5 rounded-full bg-amber-100 text-amber-700 font-medium">
                模拟模式
              </span>
            )}
          </div>
          <div className="ml-auto flex items-center gap-2 flex-wrap justify-end">
            <input
              value={ip}
              onChange={(e) => setIp(e.target.value)}
              disabled={connected || busy}
              className={`${inputCls} w-40`}
              placeholder="机械臂 IP"
            />
            {connected ? (
              <button className={btnDanger} onClick={doDisconnect} disabled={busy}>
                <PlugZap size={16} /> 断开
              </button>
            ) : (
              <button className={btnPrimary} onClick={doConnect} disabled={busy}>
                <Plug size={16} /> 连接
              </button>
            )}
            <button
              className={`${btn} ${powered ? 'bg-amber-100 text-amber-700 border-amber-300' : 'bg-slate-50 text-slate-500 border-slate-200'} border`}
              onClick={() => runPw(() => api.powerOn(), '上电')}
              disabled={!connected || pwBusy || powered}
            >
              <Power size={16} /> 上电
            </button>
            <button
              className={`${btn} ${enabled ? 'bg-emerald-100 text-emerald-700 border-emerald-300' : 'bg-slate-50 text-slate-500 border-slate-200'} border`}
              onClick={() => runPw(() => api.enableRobot(), '使能')}
              disabled={!connected || pwBusy || enabled || !powered}
            >
              <Zap size={16} /> 使能
            </button>
            <button
              className={btnGhost}
              onClick={() => runPw(() => api.disableRobot(), '失能')}
              disabled={!connected || pwBusy || !enabled}
            >
              <ZapOff size={16} /> 失能
            </button>
            <button
              className={btnGhost}
              onClick={() => runPw(() => api.powerOff(), '下电')}
              disabled={!connected || pwBusy || !powered}
            >
              <PowerOff size={16} /> 下电
            </button>
            <div className="flex flex-col gap-1 ml-1">
              <span
                className={`text-xs px-2.5 py-0.5 rounded-full font-medium ${
                  connected ? 'bg-emerald-100 text-emerald-700' : 'bg-slate-100 text-slate-500'
                }`}
              >
                {connected ? '已连接' : '未连接'}
              </span>
              <span
                className={`text-xs px-2.5 py-0.5 rounded-full font-medium ${
                  powered ? 'bg-amber-100 text-amber-700' : 'bg-slate-100 text-slate-400'
                }`}
              >
                {powered ? '已上电' : '未上电'}
              </span>
              <span
                className={`text-xs px-2.5 py-0.5 rounded-full font-medium ${
                  enabled ? 'bg-emerald-500 text-white' : 'bg-slate-100 text-slate-400'
                }`}
              >
                {enabled ? '已使能' : '未使能'}
              </span>
            </div>
          </div>
        </div>
        <nav className="max-w-7xl mx-auto px-4 flex gap-1 overflow-x-auto">
          {TABS.map((t) => {
            const Icon = t.icon
            const active = tab === t.key
            return (
              <button
                key={t.key}
                onClick={() => setTab(t.key)}
                className={`flex items-center gap-1.5 px-4 py-2.5 text-sm font-medium border-b-2 transition-colors whitespace-nowrap ${
                  active
                    ? 'border-brand-600 text-brand-700'
                    : 'border-transparent text-slate-500 hover:text-slate-700'
                }`}
              >
                <Icon size={16} /> {t.label}
              </button>
            )
          })}
        </nav>
      </header>

      {err && (
        <div className="max-w-7xl mx-auto w-full px-4 pt-3">
          <div className="flex items-center gap-2 text-sm text-red-600 bg-red-50 border border-red-200 rounded-lg px-3 py-2">
            <AlertCircle size={16} /> {err}
          </div>
        </div>
      )}

      <main className="flex-1 max-w-7xl w-full mx-auto px-4 py-4">
        <div className={card}>
          <div className="p-4">
            {tab === 'status' && <StatusPanel status={status} connected={connected} />}
            {tab === 'manual' && <ManualControl connected={connected} status={status} />}
            {tab === 'points' && <WaypointManager connected={connected} status={status} />}
            {tab === 'flow' && <FlowEditor connected={connected} />}
            {tab === 'zerg' && <ZergPanel />}
          </div>
        </div>
      </main>
    </div>
  )
}
