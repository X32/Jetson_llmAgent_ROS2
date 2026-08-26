#!/usr/bin/env python3
# 自定义多传感器机器人 launch 文件
# 包含：激光雷达 + 相机 + 里程计 + TF

import os
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node

def generate_launch_description():
    # 获取包路径
    pkg_ros_gz_sim = get_package_share_directory('ros_gz_sim')
    pkg_ros_gz_sim_demos = get_package_share_directory('ros_gz_sim_demos')

    # 启动 Gazebo（使用自定义的多传感器世界）
    gz_sim = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(pkg_ros_gz_sim, 'launch', 'gz_sim.launch.py')
        ),
        launch_arguments={
            'gz_args': '/mnt/apfs/workplace/ROS2/worlds/multi_sensor_robot.sdf'
        }.items(),
    )

    # 桥接所有传感器话题
    bridge = Node(
        package='ros_gz_bridge',
        executable='parameter_bridge',
        arguments=[
            # 激光雷达
            '/lidar@sensor_msgs/msg/LaserScan@gz.msgs.LaserScan',
            # 相机
            '/camera@sensor_msgs/msg/Image@gz.msgs.Image',
            '/camera_info@sensor_msgs/msg/CameraInfo@gz.msgs.CameraInfo',
            # 里程计（由差速驱动插件发布）
            '/model/robot/odometry@nav_msgs/msg/Odometry@gz.msgs.Odometry',
            # 速度控制
            '/model/robot/cmd_vel@geometry_msgs/msg/Twist@gz.msgs.Twist',
            # TF 坐标变换：Gazebo 的位姿话题 → ROS /tf（单向 GZ→ROS）
            '/model/robot/pose@tf2_msgs/msg/TFMessage[gz.msgs.Pose_V',
        ],
        parameters=[{
            'qos_overrides./model/robot.subscriber.reliability': 'reliable',
        }],
        # 关键：把桥接出来的 /model/robot/pose（TFMessage）重映射到 /tf，
        # 否则 view_frames / rviz2 监听的 /tf 永远是空的
        remappings=[('/model/robot/pose', '/tf')],
        output='screen'
    )

    # RViz（可选）
    rviz = Node(
        package='rviz2',
        executable='rviz2',
        condition=IfCondition(LaunchConfiguration('rviz')),
        arguments=['-d', os.path.join(pkg_ros_gz_sim_demos, 'rviz', 'camera.rviz')]
    )

    return LaunchDescription([
        DeclareLaunchArgument('rviz', default_value='false',
                              description='Open RViz'),
        gz_sim,
        bridge,
        rviz
    ])
