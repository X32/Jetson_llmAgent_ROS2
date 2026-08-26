cmake_minimum_required(VERSION 3.8)
project(action_demo)

if(CMAKE_COMPILER_IS_GNUCXX OR CMAKE_CXX_COMPILER_ID MATCHES "Clang")
  add_compile_options(-Wall -Wextra -Wpedantic)
endif()

find_package(ament_cmake REQUIRED)
find_package(rclcpp REQUIRED)
find_package(rclcpp_action REQUIRED)
find_package(action_msgs REQUIRED)

# 优先使用系统的OpenCV，避免/usr/local下旧版本冲突
set(OpenCV_DIR "/usr/lib/x86_64-linux-gnu/cmake/opencv4")
find_package(OpenCV REQUIRED)

# ===== 生成 Action 接口代码（C++头文件等） =====
find_package(rosidl_default_generators REQUIRED)
rosidl_generate_interfaces(${PROJECT_NAME}
  "action/MoveRobot.action"
)

# ===== Action Server =====
add_executable(move_robot_server src/move_robot_server.cpp)
target_compile_features(move_robot_server PUBLIC c_std_17 cxx_std_17)
ament_target_dependencies(move_robot_server rclcpp rclcpp_action action_msgs OpenCV)

# ===== Action Client =====
add_executable(move_robot_client src/move_robot_client.cpp)
target_compile_features(move_robot_client PUBLIC c_std_17 cxx_std_17)
ament_target_dependencies(move_robot_client rclcpp rclcpp_action action_msgs)

# 让可执行文件链接本包生成的接口（关键！）
rosidl_get_typesupport_target(cpp_typesupport_target ${PROJECT_NAME} rosidl_typesupport_cpp)
target_link_libraries(move_robot_server "${cpp_typesupport_target}")
target_link_libraries(move_robot_client "${cpp_typesupport_target}")

# 安装launch文件
install(DIRECTORY launch
  DESTINATION share/${PROJECT_NAME}
)

install(TARGETS
  move_robot_server
  move_robot_client
  DESTINATION lib/${PROJECT_NAME}
)

if(BUILD_TESTING)
  find_package(ament_lint_auto REQUIRED)
  set(ament_cmake_copyright_FOUND TRUE)
  set(ament_cmake_cpplint_FOUND TRUE)
  ament_lint_auto_find_test_dependencies()
endif()

ament_package()
