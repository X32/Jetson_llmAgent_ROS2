import os
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch_ros.actions import Node


def generate_launch_description():
    pkg_robot = get_package_share_directory('robot_description')
    pkg_ros_gz_sim = get_package_share_directory('ros_gz_sim')

    world_file = os.path.join(pkg_robot, 'worlds', 'obstacles_world.sdf')
    urdf_file = os.path.join(pkg_robot, 'urdf', 'my_robot.urdf')

    # 角色1：Gazebo 引擎 + 世界（-r 自动运行）
    gz_sim = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(pkg_ros_gz_sim, 'launch', 'gz_sim.launch.py')),
        launch_arguments={'gz_args': f'-r {world_file}'}.items(),
    )

    # 角色2：把 URDF 车 spawn 进世界
    #   -world 必须与 SDF 里 <world name="obstacles_world"> 完全一致
    spawn = Node(
        package='ros_gz_sim', executable='create',
        arguments=['-world', 'obstacles_world',
                   '-file', urdf_file,
                   '-name', 'my_robot',
                   '-x', '0', '-y', '0', '-z', '0.3'],   # 稍微抬高落下，避免和地面穿插
        output='screen',
    )

    # 角色3：robot_state_publisher（读 URDF + joint_states → TF 树 + 车模描述）
    with open(urdf_file, 'r') as f:
        robot_description = f.read()
    rsp = Node(
        package='robot_state_publisher', executable='robot_state_publisher',
        parameters=[{'robot_description': robot_description}],
    )

    # 角色4：桥接。注意方向符号：
    #   [  = 只 GZ→ROS（传感器数据）
    #   ]  = 只 ROS→GZ（控制命令）
    #   @  = 双向
    bridge = Node(
        package='ros_gz_bridge', executable='parameter_bridge',
        arguments=[
            '/cmd_vel@geometry_msgs/msg/Twist]gz.msgs.Twist',
            '/scan@sensor_msgs/msg/LaserScan[gz.msgs.LaserScan',
            '/model/my_robot/odometry@nav_msgs/msg/Odometry[gz.msgs.Odometry',
            # joint_state 在 GZ 侧话题带 /world/<世界名>/ 前缀（Fortress 实测），
            # 写 /model/my_robot/joint_state 会桥不到数据——轮子 TF 失效、车模错乱的元凶
            '/world/obstacles_world/model/my_robot/joint_state@sensor_msgs/msg/JointState[gz.msgs.Model',
        ],
        remappings=[
            ('/model/my_robot/odometry', '/odom'),
            ('/world/obstacles_world/model/my_robot/joint_state', '/joint_states'),
        ],
    )

    return LaunchDescription([gz_sim, spawn, rsp, bridge])
