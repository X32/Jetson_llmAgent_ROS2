# ROS2 摄像头传感器节点系统

## 📹 快速开始

这是一个完整的ROS2摄像头传感器系统，支持从摄像头采集图像并发布到ROS2话题，同时提供实时显示和监控功能。

## 🚀 快速启动

### 1. 安装依赖（首次使用）

```bash
sudo ./install_camera_deps.sh
```

### 2. 编译项目

```bash
cd /mnt/apfs/workplace/ROS2
source /opt/ros/humble/setup.bash
colcon build --packages-select my_package
source install/setup.bash
```

### 3. 运行摄像头节点

**方法1：使用自动化测试脚本**
```bash
./camera_test.sh --demo      # 快速演示
./camera_test.sh --monitor   # 监控模式
./camera_test.sh              # 交互式菜单
```

**方法2：手动运行**
```bash
# 终端1：启动摄像头发布者
ros2 run my_package camera_publisher

# 终端2：启动摄像头订阅者（显示图像）
ros2 run my_package camera_subscriber
```

## 📁 项目结构

```
ROS2/
├── src/my_package/
│   ├── src/
│   │   ├── camera_publisher.cpp       # 摄像头发布者节点
│   │   ├── camera_subscriber.cpp      # 摄像头订阅者节点
│   │   ├── publisher_node.cpp         # 基础话题发布者
│   │   ├── subscriber_node.cpp        # 基础话题订阅者
│   │   ├── comprehensive_node.cpp     # 综合示例
│   │   ├── service_server.cpp         # 服务端示例
│   │   └── service_client.cpp         # 客户端示例
│   ├── config/
│   │   └── camera_params.yaml         # 摄像头参数配置
│   ├── CMakeLists.txt                 # 编译配置
│   └── package.xml                    # 包依赖声明
├── CAMERA_NODE_GUIDE.md              # 详细使用指南
├── camera_test.sh                    # 自动化测试脚本
├── install_camera_deps.sh            # 依赖安装脚本
└── ROS2_COMMUNICATION_GUIDE.md      # ROS2通信机制指南
```

## 🎯 功能特性

### Camera Publisher (摄像头发布者)
- ✅ 从USB摄像头采集图像
- ✅ 支持 `/dev/video0` 等多种摄像头设备
- ✅ 可配置分辨率和帧率
- ✅ 发布标准ROS2 Image消息
- ✅ 支持时间戳标记

### Camera Subscriber (摄像头订阅者)
- ✅ 实时订阅摄像头图像
- ✅ OpenCV窗口显示
- ✅ FPS统计和性能监控
- ✅ 可扩展的图像处理框架

## ⚙️ 参数配置

### 摄像头发布者参数
```bash
# 指定摄像头设备
ros2 run my_package camera_publisher --ros-args -p camera_device:=0

# 设置分辨率
ros2 run my_package camera_publisher --ros-args -p image_width:=1280 -p image_height:=720

# 设置发布频率
ros2 run my_package camera_publisher --ros-args -p publish_frequency:=30.0
```

### 摄像头订阅者参数
```bash
# 不显示窗口（仅数据处理）
ros2 run my_package camera_subscriber --ros-args -p show_image:=false

# 自定义窗口名称
ros2 run my_package camera_subscriber --ros-args -p window_name:="My Camera"
```

## 🔍 监控和调试

### 话题监控
```bash
# 查看所有话题
ros2 topic list

# 监控摄像头话题
ros2 topic hz /camera/image_raw         # 查看发布频率
ros2 topic info /camera/image_raw       # 查看话题信息
ros2 topic bw /camera/image_raw         # 查看带宽使用
```

### 图像显示
```bash
# 使用rqt_image_view（推荐）
ros2 run rqt_image_view rqt_image_view

# 使用image_view
ros2 run image_view image_view --ros-args -r image:=/camera/image_raw
```

### 节点信息
```bash
# 查看运行中的节点
ros2 node list

# 查看节点详细信息
ros2 node info /camera_publisher
ros2 node info /camera_subscriber
```

## 🛠️ 常见问题

### 问题：无法打开摄像头设备
```bash
# 检查设备权限
ls -la /dev/video0

# 添加用户到video组
sudo usermod -a -G video $USER
# 重新登录系统生效

# 测试摄像头
v4l2-ctl --device=/dev/video0 --all
```

### 问题：编译错误
```bash
# 清理并重新编译
cd /mnt/apfs/workplace/ROS2
rm -rf build install logs
colcon build --packages-select my_package
```

### 问题：摄像头被其他程序占用
```bash
# 检查占用进程
sudo lsof /dev/video0

# 停止其他摄像头程序
killall guvcview cheese
```

## 📊 系统要求

- **ROS2版本**: Humble
- **操作系统**: Ubuntu 22.04
- **摄像头**: USB摄像头或笔记本内置摄像头
- **内存**: 最少2GB
- **处理器**: 支持NEON指令集的ARM或x86处理器

## 🎓 学习资源

1. **基础概念**: 阅读 `ROS2_COMMUNICATION_GUIDE.md`
2. **详细指南**: 阅读 `CAMERA_NODE_GUIDE.md`
3. **自动化测试**: 运行 `./camera_test.sh`
4. **ROS2官方文档**: https://docs.ros.org/en/humble/

## 🚀 扩展应用

### 1. 图像处理
在 `camera_subscriber.cpp` 中的 `process_image()` 函数添加你的算法：
- 边缘检测
- 人脸识别
- 物体跟踪
- 颜色过滤

### 2. 数据录制
```bash
# 录制摄像头数据
ros2 bag record /camera/image_raw -o my_camera_data

# 回放数据
ros2 bag play my_camera_data
```

### 3. 多摄像头系统
```bash
# 启动多个摄像头节点
ros2 run my_package camera_publisher --ros-args -p camera_device:=0 -r __node:=camera_0
ros2 run my_package camera_publisher --ros-args -p camera_device:=1 -r __node:=camera_1
```

### 4. 与其他ROS2包集成
- **SLAM**: 结合激光雷达进行视觉SLAM
- **导航**: 使用摄像头进行路径规划
- **深度学习**: 集成YOLO、TensorFlow等模型

## 📝 代码示例

查看不同通信方式的完整示例：

- **话题通信**: `publisher_node.cpp` + `subscriber_node.cpp`
- **服务通信**: `service_server.cpp` + `service_client.cpp`
- **综合示例**: `comprehensive_node.cpp`
- **摄像头系统**: `camera_publisher.cpp` + `camera_subscriber.cpp`

## 🎉 总结

你现在拥有一个功能完整的ROS2摄像头传感器系统：

✅ **硬件支持**: USB摄像头、笔记本内置摄像头
✅ **软件完整**: 发布者、订阅者、监控工具
✅ **易于使用**: 自动化脚本、详细文档
✅ **高度可配置**: 参数配置、多种运行模式
✅ **可扩展**: 支持图像处理、AI集成

开始探索ROS2的视觉世界吧！🚀

## 📞 获取帮助

遇到问题？查看这些资源：
- 详细指南：`CAMERA_NODE_GUIDE.md`
- 自动化测试：`./camera_test.sh --help`
- ROS2官方文档：https://docs.ros.org/en/humble/