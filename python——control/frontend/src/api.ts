import type {
  RobotStatus, Waypoint, Flow, FlowRunState, FlowSegment, MoveType,
  GripperInfo, GripperStatus,
} from './types'

const BASE = '/api'

async function req<T>(path: string, opts?: RequestInit): Promise<T> {
  const res = await fetch(BASE + path, {
    headers: { 'Content-Type': 'application/json' },
    ...opts,
  })
  if (!res.ok) {
    let msg = res.statusText
    try {
      const j = await res.json()
      msg = j.detail || msg
    } catch {
      /* ignore */
    }
    throw new Error(msg)
  }
  const ct = res.headers.get('content-type') || ''
  return (ct.includes('json') ? res.json() : res.text()) as Promise<T>
}

export const api = {
  info: () => req<{ sim: boolean; default_ip: string; move_types: string[] }>('/info'),
  connect: (ip: string) => req<{ connected: boolean }>('/connect', { method: 'POST', body: JSON.stringify({ ip }) }),
  disconnect: () => req<{ connected: boolean }>('/disconnect', { method: 'POST' }),
  powerOn: () => req<{ powered: boolean; enabled: boolean }>('/power_on', { method: 'POST' }),
  powerOff: () => req<{ powered: boolean; enabled: boolean }>('/power_off', { method: 'POST' }),
  enableRobot: () => req<{ powered: boolean; enabled: boolean }>('/enable', { method: 'POST' }),
  disableRobot: () => req<{ powered: boolean; enabled: boolean }>('/disable', { method: 'POST' }),
  status: () => req<RobotStatus>('/status'),
  jog: (axis: number, move_mode: number, coord: number, vel: number) =>
    req('/jog', { method: 'POST', body: JSON.stringify({ axis, move_mode, coord, vel, pos_cmd: 0 }) }),
  jogStop: () => req('/jog_stop', { method: 'POST' }),
  move: (p: {
    move_type: MoveType
    target: number[]
    move_mode?: number
    is_block?: boolean
    speed: number
    acc?: number
    tol?: number
    mid_pos?: number[]
  }) => req('/move', { method: 'POST', body: JSON.stringify(p) }),
  motionAbort: () => req('/motion_abort', { method: 'POST' }),

  points: () => req<Waypoint[]>('/points'),
  savePoint: (name: string, note: string, pose?: number[], joints?: number[]) =>
    req<Waypoint>('/points', { method: 'POST', body: JSON.stringify({ name, note, pose, joints }) }),
  updatePoint: (id: string, data: Partial<Waypoint>) =>
    req<Waypoint>(`/points/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
  renamePoint: (id: string, name: string) =>
    req<Waypoint>(`/points/${id}/rename`, { method: 'PUT', body: JSON.stringify({ name }) }),
  deletePoint: (id: string) => req(`/points/${id}`, { method: 'DELETE' }),
  previewPoint: (id: string, move_type: MoveType, speed: number) =>
    req(`/points/${id}/preview`, {
      method: 'POST',
      body: JSON.stringify({ move_type, target: [0, 0, 0, 0, 0, 0], speed, is_block: true }),
    }),

  flows: () => req<Flow[]>('/flows'),
  saveFlow: (name: string, segments: FlowSegment[], note = '') =>
    req<Flow>('/flows', { method: 'POST', body: JSON.stringify({ name, segments, note }) }),
  updateFlow: (id: string, name: string, segments: FlowSegment[], note = '') =>
    req<Flow>(`/flows/${id}`, { method: 'PUT', body: JSON.stringify({ name, segments, note }) }),
  deleteFlow: (id: string) => req(`/flows/${id}`, { method: 'DELETE' }),
  runFlow: (id: string) => req<FlowRunState>(`/flows/${id}/run`, { method: 'POST' }),
  flowControl: (action: 'pause' | 'resume' | 'stop') =>
    req<FlowRunState>('/flows/run/control', { method: 'POST', body: JSON.stringify({ action }) }),
  flowState: () => req<FlowRunState>('/flows/run/state'),

  gripperInfo: () => req<GripperInfo>('/gripper/info'),
  gripperConnect: (port?: string, slave = 1, baud = 115200) =>
    req<{ connected: boolean; port?: string; sim?: boolean }>('/gripper/connect', {
      method: 'POST', body: JSON.stringify({ port, slave, baud }),
    }),
  gripperDisconnect: () => req<{ connected: boolean }>('/gripper/disconnect', { method: 'POST' }),
  gripperInitialize: () =>
    req<{ initialized: boolean; state: number }>('/gripper/initialize', {
      method: 'POST', body: JSON.stringify({ wait: true, timeout: 5 }),
    }),
  gripperMove: (position: number) =>
    req<{ position: number; reached: boolean | null; state: number }>('/gripper/move', {
      method: 'POST', body: JSON.stringify({ position, wait: true, timeout: 10 }),
    }),
  gripperOpen: () => req('/gripper/open', { method: 'POST' }),
  gripperClose: () => req('/gripper/close', { method: 'POST' }),
  gripperSetParams: (force?: number, speed?: number) =>
    req<{ force?: number; speed?: number }>('/gripper/set_params', {
      method: 'POST', body: JSON.stringify({ force, speed }),
    }),
  gripperStatus: () => req<GripperStatus>('/gripper/status'),
}
