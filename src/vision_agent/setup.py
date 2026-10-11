from setuptools import find_packages, setup

package_name = 'vision_agent'

setup(
    name=package_name,
    version='0.0.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='x32',
    maintainer_email='x32skykid@hotmail.com',
    description='E1: Qwen2.5-VL grounding 节点（服务触发 + /detected_objects）',
    license='TODO: License declaration',
    extras_require={
        'test': [
            'pytest',
        ],
    },
    entry_points={
        'console_scripts': [
            'grounding = vision_agent.grounding_node:main',
            'yolo_grounding = vision_agent.yolo_grounding_node:main',
        ],
    },
)
