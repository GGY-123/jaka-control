import { useState, useRef } from 'react'
import { Octagon, Move3d, AlertTriangle, Info, Cog, Send, Crosshair } from 'lucide-react'
import Joystick from './Joystick'
import GripperPanel from './GripperPanel'
import PipettePanel from './PipettePanel'
import { api } from '../api'
import type { RobotStatus } from '../types'
import { btnAxis, btnDanger, btnGhost, btnPrimary, card, labelCls, inputCls } from '../ui'

const COORDS = [
  { k: 0, label: '基坐标' },
  { k: 1, label: '关节' },
  { k: 2, label: '工具' },
]
const AXES = [
  { axis: 0, label: 'X', vel: 'trans' },
  { axis: 1, label: 'Y', vel: 'trans' },
  { axis: 2, label: 'Z', vel: 'trans' },
  { axis: 3, label: 'RX', vel: 'rot' },
  { axis: 4, label: 'RY', vel: 'rot' },
  { axis: 5, label: 'RZ', vel: 'rot' },
] as const

const JOINTS = [
  { axis: 0, label: 'J1' },
  { axis: 1, label: 'J2' },
  { axis: 2, label: 'J3' },
  { axis: 3, label: 'J4' },
  { axis: 4, label: 'J5' },
  { axis: 5, label: 'J6' },
] as const

function HoldButton({
  label, onStart, onStop,
}: {
  label: string; onStart: () => void; onStop: () => void
}) {
  const [active, setActive] = useState(false)
  const start = () => { setActive(true); onStart() }
  const stop = () => { if (active) { setActive(false); onStop() } }
  return (
    <button
      disabled={!onStart}
      onPointerDown={start}
      onPointerUp={stop}
      onPointerLeave={stop}
      onPointerCancel={stop}
      className={`${btnAxis} ${active ? 'bg-brand-100 border-brand-400 text-brand-700' : ''} w-full`}
    >
      {label}
    </button>
  )
}

function AxisRow({
  label, onStartNeg, onStartPos, onStop,
}: {
  label: string
  onStartNeg: () => void; onStartPos: () => void; onStop: () => void
}) {
  return (
    <div className="flex items-center gap-2">
      <span className="w-9 text-xs font-medium text-slate-500">{label}</span>
      <HoldButton label="−" onStart={onStartNeg} onStop={onStop} />
      <HoldButton label="+" onStart={onStartPos} onStop={onStop} />
    </div>
  )
}

export default function ManualControl({ connected, status }: { connected: boolean; status: RobotStatus }) {
  const [coord, setCoord] = useState(0)
  const [transVel, setTransVel] = useState(20)
  const [rotVel, setRotVel] = useState(0.5)
  const [jointVel, setJointVel] = useState(0.5)
  const [target, setTarget] = useState<number[]>([0, 0, 0, 0, 0, 0])
  const [targetSpeed, setTargetSpeed] = useState(30)
  const [targetAcc, setTargetAcc] = useState(100)
  const [targetBusy, setTargetBusy] = useState(false)
  const [targetMessage, setTargetMessage] = useState('')
  const jogKey = useRef<string | null>(null)
  const tcp = status.tcp ?? [0, 0, 0, 0, 0, 0]
  const joints = status.joints ?? [0, 0, 0, 0, 0, 0]

  const startJog = (axis: number, dir: number, vel: number) => {
    if (jogKey.current) api.jogStop().catch(() => {})
    api.jog(axis, 2, coord, vel * dir).catch(() => {})
    jogKey.current = `${axis}:${dir}`
  }
  const stopJog = () => {
    api.jogStop().catch(() => {})
    jogKey.current = null
  }
  const startJointJog = (axis: number, dir: number) => {
    if (jogKey.current) api.jogStop().catch(() => {})
    api.jog(axis, 2, 1, jointVel * dir).catch(() => {})
    jogKey.current = `j${axis}:${dir}`
  }

  const onJoyMove = (dx: number, dy: number) => {
    if (!connected) return
    const mag = Math.hypot(dx, dy)
    let axis: number | undefined
    let dir = 0
    let active = false
    if (mag > 0.3) {
      if (Math.abs(dx) > Math.abs(dy)) { axis = 0; dir = Math.sign(dx) }
      else { axis = 1; dir = Math.sign(dy) }
      active = true
    }
    const key = active && axis !== undefined ? `${axis}:${dir}` : null
    if (key !== jogKey.current) {
      if (jogKey.current !== null) stopJog()
      if (key !== null && axis !== undefined) startJog(axis, dir, transVel)
    }
  }
  const onJoyEnd = () => { if (jogKey.current !== null) stopJog() }

  const velOf = (v: 'trans' | 'rot') => (v === 'trans' ? transVel : rotVel)
  const useCurrentTcp = () => setTarget(tcp.map((value) => Number(value.toFixed(6))))
  const updateTarget = (index: number, value: number) =>
    setTarget((current) => current.map((item, i) => i === index ? value : item))
  const moveToTarget = async () => {
    if (!connected || targetBusy) return
    if (!target.every(Number.isFinite)) {
      setTargetMessage('请输入有效的 TCP 数值')
      return
    }
    const formatted = target.map((value) => value.toFixed(3)).join(', ')
    if (!window.confirm(`将以直线运动到 TCP 位姿：\n[${formatted}]\n\n确认路径无碰撞后继续。`)) return
    setTargetBusy(true)
    setTargetMessage('')
    try {
      await api.move({ move_type: 'linear', target, speed: targetSpeed, acc: targetAcc, tol: 0.1, is_block: true })
      setTargetMessage('已到达目标位姿')
    } catch (error) {
      setTargetMessage(`运动失败: ${(error as Error).message}`)
    } finally {
      setTargetBusy(false)
    }
  }

  return (
    <div className="space-y-4">
      {!connected && <div className="text-sm text-slate-400">未连接机械臂，无法手动控制。</div>}

      <div className="flex flex-wrap gap-2">
        {['X', 'Y', 'Z', 'RX', 'RY', 'RZ'].map((l, i) => (
          <div key={l} className="rounded-lg bg-slate-50 border border-slate-200 px-3 py-1.5">
            <span className="text-xs text-slate-400 mr-1">{l}</span>
            <span className="font-mono text-sm text-slate-700">{(tcp[i] ?? 0).toFixed(2)}</span>
          </div>
        ))}
      </div>

      <div className="flex flex-wrap items-end gap-4">
        <div>
          <div className={`${labelCls} mb-1`}>坐标系</div>
          <div className="flex gap-1">
            {COORDS.map((c) => (
              <button
                key={c.k}
                disabled={!connected}
                onClick={() => { stopJog(); setCoord(c.k) }}
                className={coord === c.k ? `${btnAxis} bg-brand-100 border-brand-400 text-brand-700` : btnAxis}
              >
                {c.label}
              </button>
            ))}
          </div>
        </div>
        <div>
          <div className={`${labelCls} mb-1`}>平移速度 mm/s <span className="text-amber-600">（上限 200）</span></div>
          <input type="number" min={1} max={200} value={transVel}
            onChange={(e) => setTransVel(Math.min(200, Math.max(1, +e.target.value || 1)))}
            className={`${inputCls} w-24`} disabled={!connected} />
          <div className="text-xs text-slate-400 mt-0.5">建议调试 5~30，快速移动 ≤100</div>
        </div>
        <div>
          <div className={`${labelCls} mb-1`}>旋转速度 rad/s <span className="text-amber-600">（上限 2）</span></div>
          <input type="number" min={0.05} max={2} step={0.05} value={rotVel}
            onChange={(e) => setRotVel(Math.min(2, Math.max(0.05, +e.target.value || 0.05)))}
            className={`${inputCls} w-24`} disabled={!connected} />
          <div className="text-xs text-slate-400 mt-0.5">建议调试 0.1~0.5</div>
        </div>
        <div className="ml-auto">
          <button className={btnDanger} onClick={() => api.motionAbort().catch(() => {})} disabled={!connected}>
            <Octagon size={16} /> 急停
          </button>
        </div>
      </div>

      <div className={`${card} p-3 bg-sky-50 border-sky-200`}>
        <div className="flex items-start gap-2 text-xs text-slate-600">
          <Info size={16} className="text-sky-600 mt-0.5 shrink-0" />
          <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-x-4 gap-y-1.5 w-full">
            <div><span className="font-medium text-slate-700">点动 Jog 平移 (X/Y/Z)：</span>最大 <b className="text-amber-700">200 mm/s</b></div>
            <div><span className="font-medium text-slate-700">点动 Jog 旋转 (RX/RY/RZ)：</span>最大 <b className="text-amber-700">2 rad/s</b></div>
            <div><span className="font-medium text-slate-700">关节运动 joint_move：</span>速度比例 <b className="text-amber-700">0~1.0</b>（≈rad/s 上限 3.14）</div>
            <div><span className="font-medium text-slate-700">直线运动 linear_move：</span>最大 <b className="text-amber-700">500 mm/s</b></div>
            <div><span className="font-medium text-slate-700">圆弧运动 circular_move：</span>最大 <b className="text-amber-700">500 mm/s</b></div>
            <div className="flex items-start gap-1">
              <AlertTriangle size={14} className="text-amber-500 mt-0.5 shrink-0" />
              <span>高速运动前请确认周围空间足够并降低首次速度</span>
            </div>
          </div>
        </div>
      </div>

      <div className={`${card} p-4`}>
        <div className="flex items-start justify-between gap-3 flex-wrap mb-3">
          <div>
            <h3 className="font-semibold text-slate-700 flex items-center gap-2">
              <Crosshair size={18} className="text-brand-600" /> 移动到指定 TCP 位姿
            </h3>
            <p className="text-xs text-slate-500 mt-1">基坐标系，X/Y/Z 为 mm，RX/RY/RZ 为 rad。执行为阻塞直线运动。</p>
          </div>
          <button className={btnGhost} onClick={useCurrentTcp} disabled={!connected || targetBusy}>
            <Crosshair size={15} /> 使用当前位姿
          </button>
        </div>
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-2">
          {['X (mm)', 'Y (mm)', 'Z (mm)', 'RX (rad)', 'RY (rad)', 'RZ (rad)'].map((label, index) => (
            <label key={label} className="min-w-0">
              <span className={`${labelCls} block mb-1`}>{label}</span>
              <input type="number" step="0.001" value={target[index]}
                onChange={(event) => updateTarget(index, Number(event.target.value))}
                className={`${inputCls} w-full min-w-0`} disabled={!connected || targetBusy} />
            </label>
          ))}
        </div>
        <div className="flex flex-wrap items-end gap-3 mt-3">
          <label>
            <span className={`${labelCls} block mb-1`}>速度 (mm/s)</span>
            <input type="number" min={1} max={200} value={targetSpeed}
              onChange={(event) => setTargetSpeed(Math.min(200, Math.max(1, Number(event.target.value) || 1)))}
              className={`${inputCls} w-28`} disabled={!connected || targetBusy} />
          </label>
          <label>
            <span className={`${labelCls} block mb-1`}>加速度 (mm/s²)</span>
            <input type="number" min={1} max={5000} value={targetAcc}
              onChange={(event) => setTargetAcc(Math.min(5000, Math.max(1, Number(event.target.value) || 1)))}
              className={`${inputCls} w-32`} disabled={!connected || targetBusy} />
          </label>
          <button className={btnPrimary} onClick={moveToTarget} disabled={!connected || targetBusy}>
            <Send size={16} /> {targetBusy ? '运动执行中' : '直线移动到此点'}
          </button>
          {targetMessage && <span className={`text-sm ${targetMessage.startsWith('运动失败') ? 'text-red-600' : 'text-emerald-600'}`}>{targetMessage}</span>}
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className={`${card} p-4 flex flex-col items-center`}>
          <h3 className="font-semibold text-slate-700 mb-3 self-start flex items-center gap-2">
            <Move3d size={18} className="text-brand-600" /> X / Y 摇杆
          </h3>
          <Joystick onMove={onJoyMove} onEnd={onJoyEnd} />
          <div className="text-xs text-slate-400 mt-3">松手自动回中并停止运动</div>
        </div>

        <div className={`${card} p-4`}>
          <h3 className="font-semibold text-slate-700 mb-3">轴向点动（按住移动）</h3>
          <div className="grid grid-cols-2 gap-x-6 gap-y-3">
            {AXES.map((a) => (
              <AxisRow
                key={a.axis}
                label={a.label}
                onStartNeg={() => startJog(a.axis, -1, velOf(a.vel))}
                onStartPos={() => startJog(a.axis, 1, velOf(a.vel))}
                onStop={stopJog}
              />
            ))}
          </div>
        </div>
      </div>

      <div className={`${card} p-4`}>
        <div className="flex flex-wrap items-end justify-between gap-3 mb-3">
          <h3 className="font-semibold text-slate-700 flex items-center gap-2">
            <Cog size={18} className="text-brand-600" /> 关节独立控制
          </h3>
          <div className="flex items-center gap-2">
            <span className="text-xs text-slate-400">关节速度</span>
            <input type="number" min={0.05} max={3.14} step={0.05} value={jointVel}
              onChange={(e) => setJointVel(Math.min(3.14, Math.max(0.05, +e.target.value || 0.05)))}
              className={`${inputCls} w-24`} disabled={!connected} />
            <span className="text-xs text-slate-400">rad/s（上限 3.14 ≈180°/s）</span>
          </div>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
          {JOINTS.map((j) => {
            const rad = joints[j.axis] ?? 0
            const deg = (rad * 180 / Math.PI).toFixed(1)
            return (
              <div key={j.axis} className="border border-slate-200 rounded-lg p-2.5 bg-slate-50">
                <div className="flex items-center justify-between mb-1.5">
                  <span className="text-sm font-medium text-slate-700">{j.label}</span>
                  <div className="text-right">
                    <div className="font-mono text-sm text-slate-800">{rad.toFixed(3)} <span className="text-xs text-slate-400">rad</span></div>
                    <div className="font-mono text-xs text-slate-500">{deg}°</div>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <HoldButton label="−" onStart={() => startJointJog(j.axis, -1)} onStop={stopJog} />
                  <HoldButton label="+" onStart={() => startJointJog(j.axis, 1)} onStop={stopJog} />
                </div>
              </div>
            )
          })}
        </div>
        <div className="text-xs text-slate-400 mt-2">按住 −/+ 持续点动，松开自动停止。关节坐标系 coord=1，独立控制每个关节角度。</div>
      </div>

      <GripperPanel />
      <PipettePanel />
    </div>
  )
}
