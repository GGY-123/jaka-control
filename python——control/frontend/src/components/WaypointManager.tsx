import { useEffect, useState } from 'react'
import { Plus, Eye, Pencil, Trash2, Save, X, MapPin, RotateCw, Crosshair } from 'lucide-react'
import { api } from '../api'
import type { Waypoint, RobotStatus, MoveType } from '../types'
import { btnPrimary, btnGhost, btnDanger, card, inputCls, labelCls } from '../ui'

const MOVE_OPTS: { k: MoveType; label: string }[] = [
  { k: 'joint', label: '关节' },
  { k: 'linear', label: '直线' },
]
const CART = ['X', 'Y', 'Z', 'RX', 'RY', 'RZ']
const JN = ['J1', 'J2', 'J3', 'J4', 'J5', 'J6']

function NumArray({
  value, onChange, labels,
}: {
  value: number[]; onChange: (v: number[]) => void; labels: string[]
}) {
  return (
    <div className="grid grid-cols-3 gap-2">
      {value.map((v, i) => (
        <div key={i}>
          <div className={labelCls}>{labels[i]}</div>
          <input
            type="number"
            step="0.001"
            value={Number.isFinite(v) ? +v.toFixed(4) : 0}
            onChange={(e) => { const n = [...value]; n[i] = +e.target.value || 0; onChange(n) }}
            className={`${inputCls} w-full`}
          />
        </div>
      ))}
    </div>
  )
}

export default function WaypointManager({
  connected, status,
}: {
  connected: boolean; status: RobotStatus
}) {
  const [points, setPoints] = useState<Waypoint[]>([])
  const [name, setName] = useState('')
  const [note, setNote] = useState('')
  const [pvMode, setPvMode] = useState<MoveType>('linear')
  const [pvSpeed, setPvSpeed] = useState(50)
  const [editId, setEditId] = useState<string | null>(null)
  const [editName, setEditName] = useState('')
  const [editNote, setEditNote] = useState('')
  const [editPose, setEditPose] = useState<number[]>([0, 0, 0, 0, 0, 0])
  const [editJoints, setEditJoints] = useState<number[]>([0, 0, 0, 0, 0, 0])
  const [msg, setMsg] = useState('')

  const load = () => api.points().then(setPoints).catch(() => {})
  useEffect(() => { load() }, [])

  const save = async () => {
    if (!name.trim()) { setMsg('请输入点位名称'); return }
    if (!connected) { setMsg('未连接机械臂，无法读取当前位姿'); return }
    try {
      await api.savePoint(name.trim(), note, status.tcp, status.joints)
      setName(''); setNote(''); setMsg('已保存当前位姿为点位')
      load()
    } catch (e) { setMsg((e as Error).message) }
  }

  const preview = async (p: Waypoint) => {
    if (!connected) { setMsg('未连接机械臂'); return }
    if (pvSpeed <= 0) { setMsg('速度需大于 0'); return }
    try {
      await api.previewPoint(p.id, pvMode, pvSpeed)
      setMsg(`预览移动至 ${p.name}`)
    } catch (e) { setMsg((e as Error).message) }
  }

  const del = async (p: Waypoint) => {
    if (!confirm(`确认删除点位「${p.name}」?`)) return
    await api.deletePoint(p.id); load()
  }

  const startEdit = (p: Waypoint) => {
    setEditId(p.id); setEditName(p.name); setEditNote(p.note)
    setEditPose([...p.pose]); setEditJoints([...p.joints])
  }
  const applyCurrentPos = () => {
    if (!connected) { setMsg('未连接机械臂，无法读取当前位姿'); return }
    const curTcp = status.tcp ?? [0, 0, 0, 0, 0, 0]
    const curJoints = status.joints ?? [0, 0, 0, 0, 0, 0]
    const tcpStr = `TCP(${curTcp.slice(0, 3).map(v => v.toFixed(1)).join(', ')})`
    const jStr = `关节(${curJoints.slice(0, 3).map(v => v.toFixed(2)).join(', ')}...)`
    if (!confirm(`确认用当前设备实时位置替换该点位的原有位置数据？\n\n当前位姿：\n${tcpStr}\n${jStr}\n\n原有数据将被覆盖，此操作不可撤销。`)) return
    setEditPose([...curTcp]); setEditJoints([...curJoints])
    setMsg('已应用当前实时位姿（点击"保存"以持久化）')
  }
  const saveEdit = async () => {
    if (!editId) return
    if (!editName.trim()) { setMsg('名称不能为空'); return }
    try {
      await api.updatePoint(editId, { name: editName.trim(), note: editNote, pose: editPose, joints: editJoints })
      setEditId(null); setMsg('点位已更新'); load()
    } catch (e) { setMsg((e as Error).message) }
  }
  const rename = async (p: Waypoint) => {
    const n = prompt('重命名点位', p.name)
    if (n && n.trim()) { await api.renamePoint(p.id, n.trim()); load() }
  }

  return (
    <div className="space-y-4">
      {msg && <div className="text-sm text-brand-700 bg-brand-50 border border-brand-200 rounded-lg px-3 py-2">{msg}</div>}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className={`${card} p-4 lg:col-span-1`}>
          <h3 className="font-semibold text-slate-700 mb-3 flex items-center gap-2">
            <Plus size={18} className="text-brand-600" /> 保存当前位姿
          </h3>
          <div className="space-y-2">
            <div>
              <div className={labelCls}>点位名称</div>
              <input value={name} onChange={(e) => setName(e.target.value)} className={`${inputCls} w-full`} placeholder="如: 取料点A" />
            </div>
            <div>
              <div className={labelCls}>备注</div>
              <input value={note} onChange={(e) => setNote(e.target.value)} className={`${inputCls} w-full`} placeholder="可选说明" />
            </div>
            <button className={btnPrimary} onClick={save} disabled={!connected}>
              <Save size={16} /> 保存点位
            </button>
            {!connected && <div className="text-xs text-slate-400">需先连接机械臂</div>}
          </div>
        </div>

        <div className={`${card} p-4 lg:col-span-2`}>
          <h3 className="font-semibold text-slate-700 mb-3">预览运动设置</h3>
          <div className="flex flex-wrap items-end gap-3">
            <div>
              <div className={labelCls}>运动方式</div>
              <div className="flex gap-1">
                {MOVE_OPTS.map((m) => (
                  <button key={m.k} onClick={() => setPvMode(m.k)}
                    className={pvMode === m.k ? `${btnGhost} bg-brand-100 border-brand-400 text-brand-700` : btnGhost}>
                    {m.label}
                  </button>
                ))}
              </div>
            </div>
            <div>
              <div className={labelCls}>速度</div>
              <input type="number" min={1} max={3000} value={pvSpeed} onChange={(e) => setPvSpeed(Math.max(1, +e.target.value || 1))} className={`${inputCls} w-28`} />
            </div>
            <span className="text-xs text-slate-400">{pvMode === 'joint' ? 'rad/s (≤3.14)' : 'mm/s'}</span>
          </div>
        </div>
      </div>

      <div className={`${card} p-4`}>
        <div className="flex items-center justify-between mb-3">
          <h3 className="font-semibold text-slate-700 flex items-center gap-2">
            <MapPin size={18} className="text-brand-600" /> 点位列表 ({points.length})
          </h3>
          <button className={btnGhost} onClick={load}><RotateCw /> 刷新</button>
        </div>
        <div className="space-y-2">
          {points.length === 0 && <div className="text-sm text-slate-400 py-6 text-center">暂无点位</div>}
          {points.map((p) => (
            <div key={p.id} className="border border-slate-200 rounded-lg p-3">
              {editId === p.id ? (
                <div className="space-y-3">
                  <div className="flex gap-2 flex-wrap">
                    <input value={editName} onChange={(e) => setEditName(e.target.value)} className={`${inputCls} flex-1 min-w-[160px]`} />
                    <button className={btnPrimary} onClick={saveEdit}><Save size={16} /> 保存</button>
                    <button className={btnGhost} onClick={applyCurrentPos} disabled={!connected} title="用当前设备实时位姿替换该点位的位姿/关节数据">
                      <Crosshair size={15} /> 应用当前位置
                    </button>
                    <button className={btnGhost} onClick={() => setEditId(null)}><X size={16} /> 取消</button>
                  </div>
                  {!connected && <div className="text-xs text-slate-400">连接机械臂后可使用"应用当前位置"功能</div>}
                  <div>
                    <div className={labelCls}>备注</div>
                    <input value={editNote} onChange={(e) => setEditNote(e.target.value)} className={`${inputCls} w-full`} />
                  </div>
                  <div>
                    <div className={`${labelCls} mb-1`}>位姿 (mm / rad)</div>
                    <NumArray value={editPose} onChange={setEditPose} labels={CART} />
                  </div>
                  <div>
                    <div className={`${labelCls} mb-1`}>关节角 (rad)</div>
                    <NumArray value={editJoints} onChange={setEditJoints} labels={JN} />
                  </div>
                </div>
              ) : (
                <div className="flex items-center gap-3 flex-wrap">
                  <div className="flex-1 min-w-[200px]">
                    <div className="font-medium text-slate-800">{p.name}</div>
                    <div className="text-xs text-slate-400 font-mono">
                      X{p.pose[0]?.toFixed(1)} Y{p.pose[1]?.toFixed(1)} Z{p.pose[2]?.toFixed(1)} · {p.created_at}
                      {p.note && ` · ${p.note}`}
                    </div>
                  </div>
                  <button className={btnGhost} onClick={() => preview(p)} disabled={!connected}><Eye size={15} /> 预览</button>
                  <button className={btnGhost} onClick={() => startEdit(p)}><Pencil size={15} /> 编辑</button>
                  <button className={btnGhost} onClick={() => rename(p)}>重命名</button>
                  <button className={btnDanger} onClick={() => del(p)}><Trash2 size={15} /> 删除</button>
                </div>
              )}
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
