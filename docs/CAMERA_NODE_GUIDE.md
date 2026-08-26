# ROS2 摄像头传感器节点完整指南

## 概述

本指南帮助你使用ROS2创建摄像头传感器节点，用于采集摄像头帧并发布到话题，同时提供订阅者节点来接收和显示图像。

## 系统架构

```
┌─────────────────┐        /camera/image_raw         ┌─────────────────┐
│  Camera         │  ──────────────────────────────▶│  Image Display  │
│  Publisher      │   sensor_msgs/Image             │  Subscriber     │
└─────────────────┘                                   └─────────────────┘
       │                                                        │
       │                                                        │
   OpenCV                                                  OpenCV
   VideoCapture                                             imshow()
   /dev/video0                                             Window
```

## 节点功能

### Camera Publisher (摄像头发布者)
- 📹 从摄像头设备采集图像
- 🔄 转换为ROS2 Image消息格式
- 📡 发布到 `/camera/image_raw` 话题
- ⚙️ 支持参数配置（设备号、分辨率、频率）

### Camera Subscriber (摄像头订阅者)
- 📺 订阅摄像头图像话题
- 🖼️ 实时显示接收到的图像
- 📊 提供FPS统计信息
- 🎨 支持图像处理扩展

## 安装依赖

在编译之前，需要安装以下依赖包：

```bash
# 安装ROS2摄像头相关依赖
sudo apt update
sudo apt install -y \
  ros-humble-cv-bridge \
  ros-humble-vision-opencv \
  ros-humble-image-transport \
  ros-humble-camera-calibration-parsers \
  ros-humble-camera-info-manager

# 安装OpenCV开发库（如果还没安装）
sudo apt install -y libopencv-dev python3-opencv

# 安装USB摄像头相关工具
sudo apt install -y v4l-utils guvcview

# 检查摄像头设备
v4l2-ctl --list-devices
```

## 编译项目

```bash
# 进入工作空间
cd /mnt/apfs/workplace/ROS2

# 加载ROS2环境
source /opt/ros/humble/setup.bash

# 编译摄像头节点
colcon build --packages-select my_package

# 加载编译后的环境
source install/setup.bash
```

## 配置参数

编辑摄像头参数配置文件：

```bash
# 查看当前配置
cat src/my_package/config/camera_params.yaml

# 自定义配置（可选）
nano src/my_package/config/camera_params.yaml
```

### 可配置参数

**Camera Publisher参数：**
- `camera_device`: 摄像头设备号 (默认: 0，即 /dev/video0)
- `publish_frequency`: 发布频率 Hz (默认: 30.0)
- `image_width`: 图像宽度 (默认: 640)
- `image_height`: 图像高度 (默认: 480)

**Camera Subscriber参数：**
- `show_image`: 是否显示图像窗口 (默认: true)
- `window_name`: 窗口名称 (默认: "ROS2 Camera Subscriber")

## 使用方法

### 方法1：基本运行

**终端1 - 启动摄像头发布者：**
```bash
source /opt/ros/humble/setup.bash
source /mnt/apfs/workplace/ROS2/install/setup.bash
ros2 run my_package camera_publisher
```

**终端2 - 启动摄像头订阅者：**
```bash
source /opt/ros/humble/setup.bash
source /mnt/apfs/workplace/ROS2/install/setup.bash
ros2 run my_package camera_subscriber
```

### 方法2：使用参数配置

```bash
# 使用特定摄像头设备
ros2 run my_package camera_publisher --ros-args -p camera_device:=1

# 设置不同的发布频率
ros2 run my_package camera_publisher --ros-args -p publish_frequency:=15.0

# 设置更高分辨率
ros2 run my_package camera_publisher --ros-args -p image_width:=1280 -p image_height:=720

# 订阅者不显示窗口（仅处理数据）
ros2 run my_package camera_subscriber --ros-args -p show_image:=false
```

### 方法3：使用配置文件

```bash
# 启动带参数配置的发布者
ros2 run my_package camera_publisher --ros-args --params-file src/my_package/config/camera_params.yaml
```

## 监控和调试

### 检查话题

```bash
# 列出所有活跃话题
ros2 topic list

# 查看图像话题详情
ros2 topic info /camera/image_raw

# 监控图像消息（显示消息内容）
ros2 topic echo /camera/image_raw --field header.stamp

# 查看话题发布频率
ros2 topic hz /camera/image_raw

# 查看话题带宽使用
ros2 topic bw /camera/image_raw
```

### 检查节点

```bash
# 列出所有运行节点
ros2 node list

# 查看摄像头发布者节点详情
ros2 node info /camera_publisher

# 查看摄像头订阅者节点详情
ros2 node info /camera_subscriber
```

### 图像查看工具

```bash
# 使用rqt_image_view显示图像（推荐）
ros2 run rqt_image_view rqt_image_view

# 或使用image_view包
sudo apt install ros-humble-image-view
ros2 run image_view image_view --ros-args -r image:=/camera/image_raw

# 订阅并显示图像（命令行方式）
ros2 run image_tools showimage
```

## 系统测试

### 测试摄像头连接

```bash
# 检查摄像头设备
ls -la /dev/video*

# 测试摄像头（使用v4l工具）
v4l2-ctl --device=/dev/video0 --all

# 使用guvcview测试摄像头
guvcview -d /dev/video0

# 使用ffplay测试
ffplay /dev/video0
```

### 常见问题排查

**问题1：无法打开摄像头设备**
```bash
# 检查设备权限
ls -la /dev/video0
# 输出应该显示你的用户在video组中

# 如果权限不对，修复权限
sudo usermod -a -G video $USER
# 重新登录系统
```

**问题2：摄像头被其他程序占用**
```bash
# 检查是否有进程在使用摄像头
sudo lsof /dev/video0

# 停止其他摄像头应用
killall guvcview
killall cheese
```

**问题3：编译错误 - 找不到OpenCV**
```bash
# 重新安装OpenCV依赖
sudo apt install libopencv-dev python3-opencv

# 清理并重新编译
cd /mnt/apfs/workplace/ROS2
rm -rf build install logs
colcon build --packages-select my_package
```

## 性能优化

### 降低CPU使用率
```bash
# 降低帧率
ros2 run my_package camera_publisher --ros-args -p publish_frequency:=15.0

# 降低分辨率
ros2 run my_package camera_publisher --ros-args -p image_width:=320 -p image_height:=240
```

### 减少网络带宽（多机通信）
```bash
# 使用图像压缩
ros2 run image_transport republish raw compressed --ros-args -r in:=/camera/image_raw -r out:=/camera/compressed
```

## 扩展应用

### 1. 添加图像处理
在 `camera_subscriber.cpp` 的 `process_image()` 函数中添加：
```cpp
void process_image(cv::Mat& image) {
    // 边缘检测
    cv::Mat edges;
    cv::Canny(image, edges, 50, 150);

    // 人脸检测
    // 需要加载OpenCV的人脸检测模型

    // 物体追踪
    // 使用OpenCV的追踪算法
}
```

### 2. 录制视频
```bash
# 使用rosbag录制摄像头数据
ros2 bag record /camera/image_raw -o camera_data

# 回放录制的数据
ros2 bag play camera_data
```

### 3. 多摄像头系统
```bash
# 启动第一个摄像头
ros2 run my_package camera_publisher --ros-args -p camera_device:=0 -r __node:=camera_0 -r image_raw:=/camera_0/image_raw

# 启动第二个摄像头
ros2 run my_package camera_publisher --ros-args -p camera_device:=1 -r __node:=camera_1 -r image_raw:=/camera_1/image_raw
```

## 硬件推荐

**支持的摄像头类型：**
- ✅ USB摄像头 (UVC兼容)
- ✅ 笔记本内置摄像头
- ✅ 网络摄像头 (RTSP)
- ✅ 工业相机 (需要相应驱动)

**推荐配置：**
- 分辨率：640x480 - 1920x1080
- 帧率：15-30 FPS
- 接口：USB 2.0/3.0

## 下一步

1. **图像处理**: 在订阅者节点添加图像处理算法
2. **对象识别**: 集成YOLO、TensorFlow等AI模型
3. **SLAM**: 结合激光雷达进行视觉SLAM
4. **深度学习**: 使用ROS2深度学习包进行推理
5. **录制回放**: 使用rosbag进行数据录制和分析

## 总结

你现在拥有一个完整的ROS2摄像头传感器系统：
- 📹 **Camera Publisher**: 采集并发布摄像头数据
- 📺 **Camera Subscriber**: 接收并显示摄像头图像
- ⚙️ **可配置**: 支持多种参数配置
- 🔧 **可扩展**: 易于添加图像处理功能

开始探索ROS2的视觉世界吧！🚀