"""
Robot Agent 启动文件
启动 LLM Agent 和 Robot Controller 节点
"""
from launch import LaunchDescription
from launch_ros.actions import Node


def generate_launch_description():
    return LaunchDescription([
        # LLM Agent 节点：接收语音指令，发布 robot_command
        Node(
            package='robot_agent',
            executable='llm_agent',
            name='llm_agent',
            output='screen',
            parameters=[{
                'use_sim_time': False,  # 真实机器人设为 False
            }],
        ),

        # Robot Controller 节点：接收 robot_command，控制底层硬件
        Node(
            package='robot_agent',
            executable='robot_controller',
            name='robot_controller',
            output='screen',
            parameters=[{
                'use_sim_time': False,
            }],
        ),
    ])
