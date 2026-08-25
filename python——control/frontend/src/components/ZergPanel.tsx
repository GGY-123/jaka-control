import { useCallback, useEffect, useState } from 'react'
import {
  AlertTriangle, CheckCircle2, CircleStop, Loader2, Power, PowerOff,
  RefreshCw, RotateCcw, RotateCw, Unplug, Waves,
} from 'lucide-react'
import { api } from '../api'
import type { ZergResult, ZergStatus } from '../types'
import { btnDanger, btnGhost, btnPrimary, btnSuccess, inputCls, labelCls } from '../ui'

const EMPTY_STATUS: ZergStatus = {
  environment_ok: false,
  workspace: '',
  driver_managed: false,
  driver_running: false,
  ready: false,
  actions: { open: false, close: false, rotate: false },
  logs: [],
}

function resultSummary(result: ZergResult) {
  const message = result.output.match(/message[=:]\s*['"]?([^'"\n,}]+)/i)?.[1]
  return message?.trim() || '动作执行完成'
}

export default function ZergPanel() {
  const [status, setStatus] = useState<ZergStatus>(EMPTY_STATUS)
  const [busy, setBusy] = useState('')
  const [notice, setNotice] = useState('')
  const [error, setError] = useState('')
  const [gripSpeed, setGripSpeed] = useState(20)
  const [gripCurrent, setGripCurrent] = useState(0.5)
  const [angle, setAngle] = useState(30)
  const [rotateSpeed, setRotateSpeed] = useState(180)
  const [rotateCurrent, setRotateCurrent] = useState(0.5)

  const refresh = useCallback(async () => {
    try {
      setStatus(await api.zergStatus())
    } catch (e) {
      setError((e as Error).message)
    }
  }, [])

  useEffect(() => {
    refresh()
    const timer = window.setInterval(refresh, 2000)
    return () => window.clearInterval(timer)
  }, [refresh])

  const run = async (name: string, action: () => Promise<ZergResult | ZergStatus>) => {
    setBusy(name); setError(''); setNotice('')
    try {
      const result = await action()
      setNotice('output' in result ? resultSummary(result) : result.message || `${name}命令已发送`)
      await refresh()
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy('')
    }
  }

  const ready = status.ready
  const disabled = !!busy

  return (
    <div className="space-y-5">
      <div className="flex items-start justify-between gap-4 flex-wrap border-b border-slate-200 pb-4">
        <div>
          <div className="flex items-center gap-2">
            <h2 className="text-base font-semibold text-slate-800">Z-ERG-20C 旋转电爪</h2>
            <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${
              ready ? 'bg-emerald-100 text-emerald-700' : 'bg-slate-100 text-slate-500'
            }`}>
              {ready ? 'ROS2 Action 就绪' : '未就绪'}
            </span>
          </div>
          <div className="text-xs text-slate-500 mt-1 font-mono break-all">{status.workspace || '正在读取 ROS2 驱动状态'}</div>
        </div>
        <div className="flex items-center gap-2">
          <button className={btnGhost} onClick={refresh} disabled={disabled} title="刷新状态">
            <RefreshCw size={16} /> 刷新
          </button>
          <button className={btnGhost}
            onClick={() => {
              if (window.confirm('清理以前终端残留的 ZERG ROS 驱动？\n\n不会停止当前由网页管理的驱动；清理后需点击“启动驱动”。')) {
                run('清理旧驱动', api.zergCleanupDrivers)
              }
            }}
            disabled={disabled || status.driver_managed}
            title={status.driver_managed ? '请先停止当前网页管理的驱动' : '结束当前用户残留的 ZERG ROS 驱动进程'}>
            <CircleStop size={16} /> 清理旧驱动
          </button>
          {!status.driver_running ? (
            <button className={btnSuccess} onClick={() => run('启动 ROS 驱动', api.zergStartDriver)} disabled={disabled}>
              <Power size={16} /> 启动驱动
            </button>
          ) : (
            <button className={btnDanger} onClick={() => run('停止驱动', api.zergStopDriver)}
              disabled={disabled || !status.driver_managed}
              title={status.driver_managed ? '停止由本页面启动的 ROS 驱动' : '当前驱动由终端启动，网页不会停止它'}>
              <CircleStop size={16} /> 停止驱动
            </button>
          )}
        </div>
      </div>

      {(error || notice) && (
        <div className={`text-sm border rounded-lg px-3 py-2 flex items-start gap-2 ${
          error ? 'text-red-700 bg-red-50 border-red-200' : 'text-emerald-700 bg-emerald-50 border-emerald-200'
        }`}>
          {error ? <AlertTriangle size={16} className="mt-0.5 shrink-0" /> : <CheckCircle2 size={16} className="mt-0.5 shrink-0" />}
          <span className="break-words min-w-0">{error || notice}</span>
        </div>
      )}

      <div className="grid grid-cols-2 md:grid-cols-4 gap-px bg-slate-200 border border-slate-200 rounded-lg overflow-hidden">
        <StatusCell label="ROS2 环境" ok={status.environment_ok} />
        <StatusCell label="张开 Action" ok={status.actions.open} />
        <StatusCell label="闭合 Action" ok={status.actions.close} />
        <StatusCell label="旋转 Action" ok={status.actions.rotate} />
      </div>

      <section className="space-y-3">
        <div className="flex items-center justify-between gap-3 flex-wrap">
          <h3 className="text-sm font-semibold text-slate-700">设备准备</h3>
          <span className="text-xs text-slate-500">初始化会使夹指向外运动；停用电机可能释放负载</span>
        </div>
        <div className="flex flex-wrap gap-2">
          <button className={btnPrimary} disabled={!ready || disabled} onClick={() => run('初始化', api.zergInitialize)}>
            <RefreshCw size={16} /> 初始化
          </button>
          <button className={btnSuccess} disabled={!ready || disabled} onClick={() => run('启用电机', () => api.zergEnable(true))}>
            <Power size={16} /> 启用电机
          </button>
          <button className={btnGhost} disabled={!ready || disabled} onClick={() => run('停用电机', () => api.zergEnable(false))}>
            <PowerOff size={16} /> 停用电机
          </button>
        </div>
      </section>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5 border-t border-slate-200 pt-5">
        <section className="space-y-3">
          <h3 className="text-sm font-semibold text-slate-700 flex items-center gap-2"><Unplug size={16} /> 夹指开合</h3>
          <div className="grid grid-cols-2 gap-3">
            <NumberField label="速度 (mm/s)" value={gripSpeed} min={1} max={100} step={1} onChange={setGripSpeed} />
            <NumberField label="电流 (A)" value={gripCurrent} min={0.1} max={0.5} step={0.05} onChange={setGripCurrent} />
          </div>
          <div className="grid grid-cols-2 gap-2">
            <button className={btnSuccess} disabled={!ready || disabled}
              onClick={() => run('张开', () => api.zergOpen(gripSpeed, gripCurrent))}>
              <Waves size={16} /> 张开至 20 mm
            </button>
            <button className={btnDanger} disabled={!ready || disabled}
              onClick={() => run('闭合', () => api.zergClose(gripSpeed, gripCurrent))}>
              <Unplug size={16} /> 闭合至 0 mm
            </button>
          </div>
        </section>

        <section className="space-y-3 lg:border-l lg:border-slate-200 lg:pl-5">
          <h3 className="text-sm font-semibold text-slate-700 flex items-center gap-2"><RotateCw size={16} /> 相对旋转</h3>
          <div className="grid grid-cols-3 gap-3">
            <NumberField label="角度 (deg)" value={angle} min={-36000} max={36000} step={10} onChange={setAngle} />
            <NumberField label="速度 (deg/s)" value={rotateSpeed} min={1} max={1080} step={10} onChange={setRotateSpeed} />
            <NumberField label="电流 (A)" value={rotateCurrent} min={0.2} max={1} step={0.1} onChange={setRotateCurrent} />
          </div>
          <div className="grid grid-cols-2 gap-2">
            <button className={btnPrimary} disabled={!ready || disabled}
              onClick={() => run('顺时针旋转', () => api.zergRotate(Math.abs(angle), rotateSpeed, rotateCurrent))}>
              <RotateCw size={16} /> 顺时针 {Math.abs(angle)}°
            </button>
            <button className={btnGhost} disabled={!ready || disabled}
              onClick={() => run('逆时针旋转', () => api.zergRotate(-Math.abs(angle), rotateSpeed, rotateCurrent))}>
              <RotateCcw size={16} /> 逆时针 {Math.abs(angle)}°
            </button>
          </div>
        </section>
      </div>

      {busy && <div className="flex items-center gap-2 text-sm text-brand-700"><Loader2 size={16} className="animate-spin" /> {busy}执行中，等待 ROS2 返回结果</div>}

      {(status.error || status.logs.length > 0) && (
        <details className="border-t border-slate-200 pt-4">
          <summary className="text-sm text-slate-600 cursor-pointer select-none">ROS2 驱动日志与诊断</summary>
          <pre className="mt-2 max-h-48 overflow-auto bg-slate-950 text-slate-200 rounded-lg p-3 text-xs whitespace-pre-wrap break-all">{status.error || status.logs.join('\n')}</pre>
        </details>
      )}
    </div>
  )
}

function StatusCell({ label, ok }: { label: string; ok: boolean }) {
  return (
    <div className="bg-white px-3 py-3 flex items-center gap-2 min-w-0">
      <span className={`w-2 h-2 rounded-full shrink-0 ${ok ? 'bg-emerald-500' : 'bg-slate-300'}`} />
      <div className="min-w-0">
        <div className="text-xs text-slate-500 truncate">{label}</div>
        <div className={`text-sm font-medium ${ok ? 'text-emerald-700' : 'text-slate-500'}`}>{ok ? '可用' : '不可用'}</div>
      </div>
    </div>
  )
}

function NumberField({ label, value, min, max, step, onChange }: {
  label: string; value: number; min: number; max: number; step: number; onChange: (value: number) => void
}) {
  return (
    <label className="min-w-0">
      <span className={`${labelCls} block mb-1`}>{label}</span>
      <input type="number" value={value} min={min} max={max} step={step}
        onChange={(e) => onChange(Math.max(min, Math.min(max, Number(e.target.value) || min)))}
        className={`${inputCls} w-full min-w-0`} />
    </label>
  )
}
