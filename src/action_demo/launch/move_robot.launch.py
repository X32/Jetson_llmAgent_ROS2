"""
Launch文件：一键启动 Action Server + Client
演示用launch组织多节点

用法:
  ros2 launch action_demo move_robot.launch.py                    # 默认移动2.5米
  ros2 launch action_demo move_robot.launch.py target:=5.0        # 移动5米
  ros2 launch action_demo move_robot.launch.py test_cancel:=true  # 演示中途取消
"""
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    # 可在命令行覆盖的参数
    target_arg = DeclareLaunchArgument(
        'target',
        default_value='2.5',
        description='目标移动距离（米）'
    )
    test_cancel_arg = DeclareLaunchArgument(
        'test_cancel',
        default_value='false',
        description='是否演示中途取消任务'
    )

    # Action Server节点
    server_node = Node(
        package='action_demo',
        executable='move_robot_server',
        name='move_robot_server',
        output='screen',
    )

    # Action Client节点
    client_node = Node(
        package='action_demo',
        executable='move_robot_client',
        name='move_robot_client',
        output='screen',
        # 把launch参数传给client作为命令行参数（target或cancel）
        arguments=[LaunchConfiguration('target')],
    )

    return LaunchDescription([
        target_arg,
        test_cancel_arg,
        server_node,
        client_node,
    ])
