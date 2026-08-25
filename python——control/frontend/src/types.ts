export type MoveType = 'joint' | 'linear' | 'linear_z' | 'circular'

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

export interface ManualPointMotionProfile {
  move_type: MoveType
  speed: number
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

export interface CodedWorkflowAction {
  sequence: number
  action_code: string
  executor: string
  device: string
  action: string
  table_action: string
  config?: Record<string, unknown>
  internal_steps?: string[]
}

export interface Flow {
  id: string
  name: string
  segments?: FlowSegment[]
  actions?: CodedWorkflowAction[]
  flow_type?: string
  execution_mode?: string
  note: string
  created_at: string
}

export type RunStatus = 'idle' | 'running' | 'paused' | 'stopped'

export interface FlowRunState {
  status: RunStatus
  index: number
  flow_id: string | null
  segments: number
  error?: string | null
}

export interface CoordinationRunState {
  status: RunStatus
  index: number
  steps: number
  current_step: string
  error?: string | null
  logs: string[]
  a5_ip: string
  mini_ip: string
}

export interface TransferSubflowRunState extends CoordinationRunState {
  phase?: string
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

export interface ZergStatus {
  environment_ok: boolean
  workspace: string
  driver_managed: boolean
  driver_running: boolean
  ready: boolean
  actions: {
    open: boolean
    close: boolean
    rotate: boolean
  }
  error?: string | null
  logs: string[]
  started_at?: string | null
  message?: string
}

export interface ZergResult {
  ok: boolean
  action?: 'open' | 'close' | 'rotate'
  output: string
}

export interface PipetteStatus {
  connected: boolean
  port: string
  address: string
  baudrate: number
  initialized: boolean
  remaining_batches: number
  last_status: string
  last_error?: string | null
}
