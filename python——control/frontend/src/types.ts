export type MoveType = 'joint' | 'linear' | 'circular'

export interface RobotStatus {
  connected: boolean
  sim?: boolean
  ip?: string
  powered?: boolean
  enabled?: boolean
  tcp?: number[]
  joints?: number[]
  in_motion?: boolean
  drag_mode?: boolean
}

export interface Waypoint {
  id: string
  name: string
  pose: number[]
  joints: number[]
  note: string
  created_at: string
}

export type GripperActionType =
  | 'none' | 'initialize' | 'open' | 'close' | 'move_to' | 'set_force' | 'set_speed'

export interface GripperAction {
  type: GripperActionType
  position?: number | null
  force?: number | null
  speed?: number | null
  delay?: number
}

export interface FlowSegment {
  point_id: string
  move_type: MoveType
  speed: number
  acc: number
  tol: number
  wait_after_arrival?: number
  gripper?: GripperAction | null
}

export interface Flow {
  id: string
  name: string
  segments: FlowSegment[]
  note: string
  created_at: string
}

export type RunStatus = 'idle' | 'running' | 'paused' | 'stopped'

export interface FlowRunState {
  status: RunStatus
  index: number
  flow_id: string | null
  segments: number
}

export interface GripperRanges {
  force: [number, number]
  speed: [number, number]
  position: [number, number]
}

export interface GripperStatus {
  connected: boolean
  sim?: boolean
  port?: string
  initialized?: boolean
  init_state?: number
  force?: number
  speed?: number | null
  position?: number
  target?: number
  moving?: boolean
  grasp_state?: number
  error?: string
  ranges?: GripperRanges
}

export interface GripperInfo {
  sim: boolean
  default_port: string
  default_slave: number
  default_baud: number
  connected: boolean
  ranges: GripperRanges
}
