import { useRef, useState, useCallback } from 'react'

interface Props {
  size?: number
  onMove?: (dx: number, dy: number) => void
  onEnd?: () => void
}

export default function Joystick({ size = 180, onMove, onEnd }: Props) {
  const ref = useRef<HTMLDivElement>(null)
  const [pos, setPos] = useState({ x: 0, y: 0 })
  const dragging = useRef(false)
  const R = size / 2 - 24

  const handle = useCallback(
    (clientX: number, clientY: number) => {
      const el = ref.current
      if (!el) return
      const r = el.getBoundingClientRect()
      const cx = r.left + r.width / 2
      const cy = r.top + r.height / 2
      let dx = clientX - cx
      let dy = clientY - cy
      const dist = Math.hypot(dx, dy)
      if (dist > R) {
        dx = (dx / dist) * R
        dy = (dy / dist) * R
      }
      setPos({ x: dx, y: dy })
      onMove?.(dx / R, dy / R)
    },
    [onMove, R],
  )

  const onDown = (e: React.PointerEvent) => {
    dragging.current = true
    e.currentTarget.setPointerCapture(e.pointerId)
    handle(e.clientX, e.clientY)
  }
  const onMoveEvt = (e: React.PointerEvent) => {
    if (dragging.current) handle(e.clientX, e.clientY)
  }
  const onUp = () => {
    dragging.current = false
    setPos({ x: 0, y: 0 })
    onEnd?.()
  }

  return (
    <div
      ref={ref}
      onPointerDown={onDown}
      onPointerMove={onMoveEvt}
      onPointerUp={onUp}
      onPointerLeave={onUp}
      className="relative rounded-full bg-slate-100 border border-slate-200 touch-none cursor-grab active:cursor-grabbing shadow-inner"
      style={{ width: size, height: size }}
    >
      <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
        <div className="absolute left-2 right-2 h-px bg-slate-200" />
        <div className="absolute top-2 bottom-2 w-px bg-slate-200" />
      </div>
      <div
        className="absolute rounded-full bg-red-500 shadow-md border-2 border-white"
        style={{
          width: 44,
          height: 44,
          left: size / 2 - 22 + pos.x,
          top: size / 2 - 22 + pos.y,
          transition: dragging.current ? 'none' : 'all 0.18s ease-out',
        }}
      />
    </div>
  )
}
