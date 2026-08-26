import math
import threading
import time
from typing import Optional

import rclpy
from diagnostic_msgs.msg import DiagnosticArray, DiagnosticStatus, KeyValue
from rclpy.action import ActionServer, CancelResponse, GoalResponse
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import JointState
from std_srvs.srv import SetBool, Trigger
from zerg_interfaces.action import CloseGripper, OpenGripper, RotateMotor
from zerg_sdk import (
    ByteOrder,
    GripStatus,
    RotationStatus,
    TransportError,
    ZergError,
    ZergGripper,
)


class ZergDriverNode(Node):
    def __init__(self) -> None:
        super().__init__("zerg_driver")
        self._declare_parameters()
        self._callback_group = ReentrantCallbackGroup()
        self._device_lock = threading.RLock()
        self._motion_lock = threading.Lock()
        self._gripper: Optional[ZergGripper] = None
        self._last_connect_attempt = 0.0
        self._last_error = "not connected"

        self._joint_pub = self.create_publisher(
            JointState, "joint_states", qos_profile_sensor_data
        )
        self._diagnostic_pub = self.create_publisher(
            DiagnosticArray, "/diagnostics", 10
        )
        poll_rate = self.get_parameter("poll_rate_hz").value
        self._poll_timer = self.create_timer(
            1.0 / poll_rate, self._poll, callback_group=self._callback_group
        )

        self._initialize_service = self.create_service(
            Trigger,
            "~/initialize",
            self._initialize_callback,
            callback_group=self._callback_group,
        )
        self._enable_service = self.create_service(
            SetBool,
            "~/enable",
            self._enable_callback,
            callback_group=self._callback_group,
        )
        self._open_action = ActionServer(
            self,
            OpenGripper,
            "~/open",
            execute_callback=self._execute_open,
            goal_callback=self._validate_open_close_goal,
            cancel_callback=self._cancel_goal,
            callback_group=self._callback_group,
        )
        self._close_action = ActionServer(
            self,
            CloseGripper,
            "~/close",
            execute_callback=self._execute_close,
            goal_callback=self._validate_open_close_goal,
            cancel_callback=self._cancel_goal,
            callback_group=self._callback_group,
        )
        self._rotate_action = ActionServer(
            self,
            RotateMotor,
            "~/rotate",
            execute_callback=self._execute_rotate,
            goal_callback=self._validate_rotate_goal,
            cancel_callback=self._cancel_goal,
            callback_group=self._callback_group,
        )
        self.get_logger().info("Z-ERG-20C driver started; waiting for serial device")

    def _declare_parameters(self) -> None:
        self.declare_parameter("port", "/dev/ttyUSB0")
        self.declare_parameter("baudrate", 115200)
        self.declare_parameter("slave_id", 1)
        self.declare_parameter("serial_timeout_s", 0.2)
        self.declare_parameter("byte_order", "big")
        self.declare_parameter("poll_rate_hz", 20.0)
        self.declare_parameter("reconnect_interval_s", 2.0)
        self.declare_parameter("motion_timeout_s", 15.0)
        self.declare_parameter("feedback_rate_hz", 10.0)
        self.declare_parameter("grip_tolerance_mm", 0.2)
        self.declare_parameter("rotation_tolerance_deg", 1.0)
        self.declare_parameter("default_grip_speed_mm_s", 50.0)
        self.declare_parameter("default_grip_current_a", 0.3)
        self.declare_parameter("default_rotation_speed_deg_s", 360.0)
        self.declare_parameter("default_rotation_current_a", 0.8)
        self.declare_parameter("grip_joint_name", "zerg_grip_joint")
        self.declare_parameter("rotation_joint_name", "zerg_rotation_joint")

        if self.get_parameter("poll_rate_hz").value <= 0:
            raise ValueError("poll_rate_hz must be positive")
        if self.get_parameter("feedback_rate_hz").value <= 0:
            raise ValueError("feedback_rate_hz must be positive")
        ByteOrder(self.get_parameter("byte_order").value)

    def _connect(self) -> Optional[ZergGripper]:
        with self._device_lock:
            if self._gripper is not None:
                return self._gripper
            now = time.monotonic()
            retry_interval = self.get_parameter("reconnect_interval_s").value
            if now - self._last_connect_attempt < retry_interval:
                return None
            self._last_connect_attempt = now
            try:
                self._gripper = ZergGripper.open(
                    port=self.get_parameter("port").value,
                    baudrate=self.get_parameter("baudrate").value,
                    slave_id=self.get_parameter("slave_id").value,
                    timeout=self.get_parameter("serial_timeout_s").value,
                    byte_order=ByteOrder(self.get_parameter("byte_order").value),
                )
                self._last_error = ""
                self.get_logger().info("connected to Z-ERG-20C")
            except (ZergError, OSError) as exc:
                self._last_error = str(exc)
                self.get_logger().warning(f"connection failed: {exc}")
            return self._gripper

    def _disconnect(self, reason: Exception) -> None:
        with self._device_lock:
            self._last_error = str(reason)
            if self._gripper is not None:
                try:
                    self._gripper.close()
                except Exception:
                    pass
                self._gripper = None

    def _read_state(self):
        gripper = self._connect()
        if gripper is None:
            return None
        try:
            with self._device_lock:
                return gripper.read_state()
        except (ZergError, OSError) as exc:
            self._disconnect(exc)
            raise

    def _poll(self) -> None:
        try:
            state = self._read_state()
        except (ZergError, OSError):
            state = None
        if state is None:
            self._publish_diagnostics(None)
            return
        stamp = self.get_clock().now().to_msg()
        joint_state = JointState()
        joint_state.header.stamp = stamp
        joint_state.name = [
            self.get_parameter("grip_joint_name").value,
            self.get_parameter("rotation_joint_name").value,
        ]
        joint_state.position = [
            state.grip_position_mm / 1000.0,
            math.radians(state.rotation_angle_deg),
        ]
        joint_state.velocity = [
            state.grip_speed_mm_s / 1000.0,
            math.radians(state.rotation_speed_deg_s),
        ]
        self._joint_pub.publish(joint_state)
        self._publish_diagnostics(state)

    def _publish_diagnostics(self, state) -> None:
        array = DiagnosticArray()
        array.header.stamp = self.get_clock().now().to_msg()
        status = DiagnosticStatus()
        status.name = f"{self.get_name()}: Z-ERG-20C"
        status.hardware_id = (
            f"modbus:{self.get_parameter('slave_id').value}@"
            f"{self.get_parameter('port').value}"
        )
        if state is None:
            status.level = DiagnosticStatus.ERROR
            status.message = self._last_error or "disconnected"
        elif state.error_flags:
            status.level = DiagnosticStatus.ERROR
            status.message = f"device error flags: 0x{state.error_flags:08X}"
        elif not state.initialized:
            status.level = DiagnosticStatus.WARN
            status.message = "device is not initialized"
        else:
            status.level = DiagnosticStatus.OK
            status.message = "ready"
        if state is not None:
            status.values = [
                KeyValue(key="initialization_code", value=str(state.initialization_code)),
                KeyValue(key="grip_status", value=str(state.grip_status_code)),
                KeyValue(key="rotation_status", value=str(state.rotation_status_code)),
                KeyValue(key="grip_current_a", value=f"{state.grip_current_a:.4f}"),
                KeyValue(
                    key="rotation_current_a", value=f"{state.rotation_current_a:.4f}"
                ),
                KeyValue(key="error_flags", value=f"0x{state.error_flags:08X}"),
            ]
        array.status = [status]
        self._diagnostic_pub.publish(array)

    def _initialize_callback(self, _request, response):
        try:
            gripper = self._require_device()
            with self._device_lock:
                gripper.initialize()
            response.success = True
            response.message = "initialization command accepted"
        except (ZergError, OSError) as exc:
            self._disconnect(exc)
            response.success = False
            response.message = str(exc)
        return response

    def _enable_callback(self, request, response):
        try:
            gripper = self._require_device()
            with self._device_lock:
                gripper.enable_motor(request.data)
            response.success = True
            response.message = "motor enabled" if request.data else "motor disabled"
        except (ZergError, OSError) as exc:
            self._disconnect(exc)
            response.success = False
            response.message = str(exc)
        return response

    def _validate_open_close_goal(self, goal) -> GoalResponse:
        speed = goal.speed_mm_s
        current = goal.current_a
        valid = (
            (speed <= 0.0 or 1.0 <= speed <= 100.0)
            and (current <= 0.0 or 0.1 <= current <= 0.5)
        )
        return GoalResponse.ACCEPT if valid else GoalResponse.REJECT

    def _validate_rotate_goal(self, goal) -> GoalResponse:
        valid = (
            -36000.0 <= goal.angle_deg <= 36000.0
            and (goal.speed_deg_s <= 0.0 or 1.0 <= goal.speed_deg_s <= 1080.0)
            and (goal.current_a <= 0.0 or 0.2 <= goal.current_a <= 1.0)
        )
        return GoalResponse.ACCEPT if valid else GoalResponse.REJECT

    @staticmethod
    def _cancel_goal(_goal_handle) -> CancelResponse:
        return CancelResponse.ACCEPT

    def _execute_open(self, goal_handle):
        return self._execute_grip_target(
            goal_handle, OpenGripper, target_position_mm=20.0, operation="open"
        )

    def _execute_close(self, goal_handle):
        return self._execute_grip_target(
            goal_handle, CloseGripper, target_position_mm=0.0, operation="close"
        )

    def _execute_grip_target(
        self, goal_handle, action_type, target_position_mm, operation
    ):
        result = action_type.Result()
        try:
            with self._motion_lock:
                gripper = self._require_ready_device()
                speed = (
                    goal_handle.request.speed_mm_s
                    if goal_handle.request.speed_mm_s > 0.0
                    else self.get_parameter("default_grip_speed_mm_s").value
                )
                current = (
                    goal_handle.request.current_a
                    if goal_handle.request.current_a > 0.0
                    else self.get_parameter("default_grip_current_a").value
                )
                with self._device_lock:
                    gripper.command_grip(target_position_mm, speed, current)
                return self._wait_for_grip(
                    goal_handle,
                    result,
                    action_type,
                    target_position_mm,
                    operation,
                )
        except (ZergError, OSError) as exc:
            self._disconnect(exc)
            goal_handle.abort()
            result.success = False
            result.message = str(exc)
            return result

    def _wait_for_grip(
        self, goal_handle, result, action_type, target_position_mm, operation
    ):
        deadline = time.monotonic() + self.get_parameter("motion_timeout_s").value
        started_at = time.monotonic()
        period = 1.0 / self.get_parameter("feedback_rate_hz").value
        tolerance = self.get_parameter("grip_tolerance_mm").value
        motion_observed = False
        while rclpy.ok() and time.monotonic() < deadline:
            if goal_handle.is_cancel_requested:
                goal_handle.canceled()
                result.success = False
                result.message = "goal canceled; device motion was not stopped"
                return result
            state = self._read_state()
            if state is None:
                raise TransportError("device disconnected")
            feedback = action_type.Feedback()
            feedback.position_mm = state.grip_position_mm
            feedback.status = state.grip_status_code
            goal_handle.publish_feedback(feedback)
            result.final_position_mm = state.grip_position_mm
            result.status = state.grip_status_code
            reached_target = abs(state.grip_position_mm - target_position_mm) <= tolerance
            if state.grip_status == GripStatus.MOVING:
                motion_observed = True
            if reached_target and state.grip_status != GripStatus.MOVING:
                goal_handle.succeed()
                result.success = True
                result.message = f"gripper fully {operation}"
                return result
            terminal_feedback_valid = motion_observed or time.monotonic() - started_at >= 0.5
            if terminal_feedback_valid and state.grip_status == GripStatus.GRIPPING:
                goal_handle.abort()
                result.success = False
                result.message = f"gripper blocked before fully {operation}"
                return result
            if terminal_feedback_valid and state.grip_status == GripStatus.DROPPED:
                goal_handle.abort()
                result.success = False
                result.message = "object dropped"
                return result
            time.sleep(period)
        goal_handle.abort()
        result.success = False
        result.message = "motion timed out"
        return result

    def _execute_rotate(self, goal_handle):
        result = RotateMotor.Result()
        try:
            with self._motion_lock:
                gripper = self._require_ready_device()
                initial_state = self._read_state()
                if initial_state is None:
                    raise TransportError("device disconnected")
                target_angle = (
                    initial_state.rotation_angle_deg + goal_handle.request.angle_deg
                )
                speed = (
                    goal_handle.request.speed_deg_s
                    if goal_handle.request.speed_deg_s > 0.0
                    else self.get_parameter("default_rotation_speed_deg_s").value
                )
                current = (
                    goal_handle.request.current_a
                    if goal_handle.request.current_a > 0.0
                    else self.get_parameter("default_rotation_current_a").value
                )
                with self._device_lock:
                    gripper.command_rotation(
                        goal_handle.request.angle_deg,
                        relative=True,
                        speed_deg_s=speed,
                        current_a=current,
                    )
                return self._wait_for_rotation(goal_handle, result, target_angle)
        except (ZergError, OSError) as exc:
            self._disconnect(exc)
            goal_handle.abort()
            result.success = False
            result.message = str(exc)
            return result

    def _wait_for_rotation(self, goal_handle, result, target_angle_deg):
        deadline = time.monotonic() + self.get_parameter("motion_timeout_s").value
        started_at = time.monotonic()
        period = 1.0 / self.get_parameter("feedback_rate_hz").value
        tolerance = self.get_parameter("rotation_tolerance_deg").value
        motion_observed = False
        while rclpy.ok() and time.monotonic() < deadline:
            if goal_handle.is_cancel_requested:
                goal_handle.canceled()
                result.success = False
                result.message = "goal canceled; device motion was not stopped"
                return result
            state = self._read_state()
            if state is None:
                raise TransportError("device disconnected")
            feedback = RotateMotor.Feedback()
            feedback.angle_deg = state.rotation_angle_deg
            feedback.status = state.rotation_status_code
            goal_handle.publish_feedback(feedback)
            result.final_angle_deg = state.rotation_angle_deg
            result.status = state.rotation_status_code
            reached_target = abs(state.rotation_angle_deg - target_angle_deg) <= tolerance
            if state.rotation_status == RotationStatus.MOVING:
                motion_observed = True
            if state.rotation_status == RotationStatus.REACHED and reached_target:
                goal_handle.succeed()
                result.success = True
                result.message = "reached"
                return result
            terminal_feedback_valid = motion_observed or time.monotonic() - started_at >= 0.5
            if terminal_feedback_valid and state.rotation_status in (
                RotationStatus.BLOCKED,
                RotationStatus.DROPPED,
                RotationStatus.STALL_STOPPED,
            ):
                goal_handle.abort()
                result.success = False
                result.message = state.rotation_status.name.lower()
                return result
            time.sleep(period)
        goal_handle.abort()
        result.success = False
        result.message = "motion timed out"
        return result

    def _require_device(self) -> ZergGripper:
        gripper = self._connect()
        if gripper is None:
            raise TransportError(self._last_error or "device is not connected")
        return gripper

    def _require_ready_device(self) -> ZergGripper:
        gripper = self._require_device()
        state = self._read_state()
        if state is None:
            raise TransportError("device disconnected")
        if not state.initialized:
            raise ZergError(
                f"device is not initialized (status {state.initialization_code})"
            )
        return gripper

    def destroy_node(self) -> bool:
        self._open_action.destroy()
        self._close_action.destroy()
        self._rotate_action.destroy()
        with self._device_lock:
            if self._gripper is not None:
                self._gripper.close()
                self._gripper = None
        return super().destroy_node()


def main(args=None) -> None:
    rclpy.init(args=args)
    node = ZergDriverNode()
    executor = MultiThreadedExecutor(num_threads=4)
    executor.add_node(node)
    try:
        executor.spin()
    except KeyboardInterrupt:
        pass
    finally:
        try:
            executor.shutdown()
        except KeyboardInterrupt:
            pass
        try:
            node.destroy_node()
        except KeyboardInterrupt:
            pass
        if rclpy.ok():
            try:
                rclpy.shutdown()
            except KeyboardInterrupt:
                pass


if __name__ == "__main__":
    main()
