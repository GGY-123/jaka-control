import { Wifi, WifiOff, Cpu, MoveHorizontal, Hand, Gauge } from 'lucide-react'
import type { RobotStatus } from '../types'
import { card, labelCls } from '../ui'

function fmt(v: number | undefined, d = 3) {
  return v === undefined || v === null ? '--' : v.toFixed(d)
}

function Metric({
  icon: Icon, title, value, tone = 'slate',
}: {
  icon: typeof Wifi; title: string; value: string; tone?: 'slate' | 'emerald' | 'amber'
}) {
  const toneCls =
    tone === 'emerald'
      ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
      : tone === 'amber'
      ? 'bg-amber-50 text-amber-700 border-amber-200'
      : 'bg-slate-50 text-slate-700 border-slate-200'
  return (
    <div className={`rounded-xl border px-4 py-3 flex items-center gap-3 ${toneCls}`}>
      <Icon size={22} />
      <div>
        <div className="text-xs opacity-70">{title}</div>
        <div className="font-semibold">{value}</div>
      </div>
    </div>
  )
}

export default function StatusPanel({
  status, connected,
}: {
  status: RobotStatus; connected: boolean
}) {
  const tcp = status.tcp ?? [0, 0, 0, 0, 0, 0]
  const joints = status.joints ?? [0, 0, 0, 0, 0, 0]
  const cart = ['X', 'Y', 'Z', 'RX', 'RY', 'RZ']
  const jn = ['J1', 'J2', 'J3', 'J4', 'J5', 'J6']

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <Metric icon={connected ? Wifi : WifiOff} title="连接状态" value={connected ? '已连接' : '未连接'} tone={connected ? 'emerald' : 'slate'} />
        <Metric icon={Cpu} title="控制器 IP" value={status.ip ?? '--'} />
        <Metric icon={MoveHorizontal} title="运动状态" value={status.in_motion ? '运动中' : '静止'} tone={status.in_motion ? 'amber' : 'emerald'} />
        <Metric icon={Hand} title="拖拽模式" value={status.drag_mode ? '开启' : '关闭'} tone={status.drag_mode ? 'amber' : 'slate'} />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className={`${card} p-4`}>
          <div className="flex items-center justify-between mb-3">
            <h3 className="font-semibold text-slate-700 flex items-center gap-2">
              <Gauge size={18} className="text-brand-600" /> 末端位姿 (TCP)
            </h3>
            <span className={labelCls}>单位 mm / rad</span>
          </div>
          <div className="grid grid-cols-3 gap-2">
            {cart.map((l, i) => (
              <div key={l} className="rounded-lg bg-slate-50 px-3 py-2">
                <div className={labelCls}>{l}</div>
                <div className="font-mono text-slate-800 text-sm">{fmt(tcp[i])}</div>
              </div>
            ))}
          </div>
        </div>

        <div className={`${card} p-4`}>
          <div className="flex items-center justify-between mb-3">
            <h3 className="font-semibold text-slate-700 flex items-center gap-2">
              <Cpu size={18} className="text-brand-600" /> 关节角度
            </h3>
            <span className={labelCls}>单位 rad</span>
          </div>
          <div className="grid grid-cols-3 gap-2">
            {jn.map((l, i) => (
              <div key={l} className="rounded-lg bg-slate-50 px-3 py-2">
                <div className={labelCls}>{l}</div>
                <div className="font-mono text-slate-800 text-sm">{fmt(joints[i])}</div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {!connected && (
        <div className="text-sm text-slate-400 text-center py-2">
          未连接机械臂，请先在右上角输入 IP 并点击“连接”。
        </div>
      )}
    </div>
  )
}
