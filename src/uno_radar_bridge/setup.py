from setuptools import find_packages, setup

package_name = 'uno_radar_bridge'

setup(
    name=package_name,
    version='0.1.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='x32',
    maintainer_email='x32@localhost',
    description='Arduino Uno HC-SR04 + SG90 radar serial-to-LaserScan bridge',
    license='MIT',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'radar_bridge = uno_radar_bridge.radar_bridge_node:main',
        ],
    },
)
