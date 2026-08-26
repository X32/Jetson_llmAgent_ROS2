cmake_minimum_required(VERSION 3.8)
project(my_package)

if(CMAKE_COMPILER_IS_GNUCXX OR CMAKE_CXX_COMPILER_ID MATCHES "Clang")
  add_compile_options(-Wall -Wextra -Wpedantic)
endif()

# find dependencies
find_package(ament_cmake REQUIRED)
find_package(rclcpp REQUIRED)
find_package(std_msgs REQUIRED)
find_package(example_interfaces REQUIRED)

# 优先使用系统的OpenCV，避免版本冲突
set(OpenCV_DIR "/usr/lib/x86_64-linux-gnu/cmake/opencv4")
find_package(sensor_msgs REQUIRED)
find_package(cv_bridge REQUIRED)
find_package(OpenCV REQUIRED)
# ===== Day7: 生成消息接口（本包没有 C++ 节点消费它，无需链接 typesupport）=====
find_package(rosidl_default_generators REQUIRED)
rosidl_generate_interfaces(${PROJECT_NAME}
  "msg/RobotCommand.msg"
)


# 添加可执行文件（暂时只编译基础节点，避免OpenCV冲突）
add_executable(publisher_node src/publisher_node.cpp)
add_executable(subscriber_node src/subscriber_node.cpp)
add_executable(comprehensive_node src/comprehensive_node.cpp)
add_executable(service_server src/service_server.cpp)
add_executable(service_client src/service_client.cpp)
# OpenCV冲突时暂时注释掉摄像头节点
add_executable(camera_publisher src/camera_publisher.cpp)
add_executable(camera_subscriber src/camera_subscriber.cpp)
add_executable(simple_camera_publisher src/simple_camera_publisher.cpp)

# 设置目标依赖项（包含ROS2头文件和库）
ament_target_dependencies(publisher_node
  rclcpp
  std_msgs
)

ament_target_dependencies(subscriber_node
  rclcpp
  std_msgs
)

ament_target_dependencies(comprehensive_node
  rclcpp
  std_msgs
)

ament_target_dependencies(service_server
  rclcpp
  example_interfaces
)

ament_target_dependencies(service_client
  rclcpp
  example_interfaces
)

# 摄像头节点需要额外链接OpenCV（暂时注释掉避免版本冲突）
ament_target_dependencies(camera_publisher
 rclcpp
 sensor_msgs
 cv_bridge
)

target_link_libraries(camera_publisher ${OpenCV_LIBS})

ament_target_dependencies(camera_subscriber
 rclcpp
 sensor_msgs
 cv_bridge
)

target_link_libraries(camera_subscriber ${OpenCV_LIBS})

# 简化版摄像头发布者（不依赖cv_bridge）
ament_target_dependencies(simple_camera_publisher
 rclcpp
 sensor_msgs
)

target_link_libraries(simple_camera_publisher ${OpenCV_LIBS})

# 安装Python脚本
install(PROGRAMS
  scripts/camera_subscriber_py.py
  scripts/camera_recognition_subscriber.py
  scripts/subscriber_node_py.py
  DESTINATION lib/${PROJECT_NAME}
)

# 安装识别相关文件（直接安装文件内容，避免嵌套目录）
install(FILES
  scripts/imgNet/resnet18_imagenet.onnx
  scripts/imgNet/imagenet_class_index.csv
  scripts/imgNet/SimHei.ttf
  DESTINATION share/${PROJECT_NAME}/imgNet
)

# 安装可执行文件到lib目录
install(TARGETS
  publisher_node
  subscriber_node
  comprehensive_node
  service_server
  service_client
 camera_publisher
 camera_subscriber
 simple_camera_publisher
  DESTINATION lib/${PROJECT_NAME}
)

if(BUILD_TESTING)
  find_package(ament_lint_auto REQUIRED)
  # the following line skips the linter which checks for copyrights
  # comment the line when a copyright and license is added to all source files
  set(ament_cmake_copyright_FOUND TRUE)
  # the following line skips cpplint (only works in a git repo)
  # comment the line when this package is in a git repo and when
  # a copyright and license is added to all source files
  set(ament_cmake_cpplint_FOUND TRUE)
  ament_lint_auto_find_test_dependencies()
endif()


ament_package()
