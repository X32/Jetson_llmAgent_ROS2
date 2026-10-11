from setuptools import find_packages, setup

package_name = 'robot_agent'

setup(
    name=package_name,
    version='0.0.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
         # config 和 launch 跟包安装（节点从安装目录读配置，不依赖工作目录）
        ('share/robot_agent/config', ['robot_agent/config/llm_config.json']),
        ('share/robot_agent/config', ['robot_agent/config/llm_config_llamacpp.json']),
        ('share/robot_agent/launch', ['robot_agent/launch/robot_agent_bringup.launch.py']),
        ('share/robot_agent/launch', ['robot_agent/launch/full_system.launch.py']),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='x32',
    maintainer_email='x32skykid@hotmail.com',
    description='TODO: Package description',
    license='TODO: License declaration',
    extras_require={
        'test': [
            'pytest',
        ],
    },
    entry_points={
        'console_scripts': [
            'llm_agent = robot_agent.llm_agent_node:main',
            'robot_controller = robot_agent.robot_controller_node:main',
        ],
    },
)
