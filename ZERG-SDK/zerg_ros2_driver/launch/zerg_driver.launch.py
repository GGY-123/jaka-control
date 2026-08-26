from launch import LaunchDescription
from launch_ros.actions import Node
from ament_index_python.packages import get_package_share_directory
import os


def generate_launch_description():
    workspace_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    sdk_path = os.path.join(workspace_root, "zerg_sdk")
    config = os.path.join(
        get_package_share_directory("zerg_ros2_driver"),
        "config",
        "zerg_driver.yaml",
    )
    return LaunchDescription(
        [
            Node(
                package="zerg_ros2_driver",
                executable="zerg_driver",
                name="zerg_driver",
                output="screen",
                parameters=[config],
                additional_env={
                    "PYTHONPATH": sdk_path + os.pathsep + os.environ.get("PYTHONPATH", ""),
                },
            )
        ]
    )
