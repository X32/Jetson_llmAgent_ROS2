# 摄像头发布者节点使用说明

## 📷 功能说明
从USB摄像头采集图像，通过ROS2话题发布实时视频流。

## 🔧 编译和安装
```bash
cd /mnt/apfs/workplace/ROS2
source /opt/ros/humble/setup.bash
colcon build --packages-select my_package
source install/setup.bash
```

## 🚀 运行命令

### 基础运行（默认640x480）
```bash
source /opt/ros/humble/setup.bash
source install/setup.bash
ros2 run my_package camera_publisher
```

### 自定义分辨率
```bash
ros2 run my_package camera_publisher --ros-args \
  -p image_width:=1280 \
  -p image_height:=720
```

### 设置发布频率
```bash
ros2 run my_package camera_publisher --ros-args \
  -p publish_frequency:=15.0
```

### 完整参数示例
```bash
ros2 run my_package camera_publisher --ros-args \
  -p image_width:=320 \
  -p image_height:=240 \
  -p publish_frequency:=30.0
```

## 📋 可用参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `image_width` | 640 | 图像宽度（像素） |
| `image_height` | 480 | 图像高度（像素） |
| `publish_frequency` | 30.0 | 发布频率（Hz） |
| `camera_device_path` | /dev/video0 | 摄像头设备路径 |

## 🔍 查看话题
```bash
# 查看发布的话题
ros2 topic list | grep camera

# 查看话题信息
ros2 topic info /camera/image_raw

# 查看实时图像（需要image_tools）
ros2 run image_tools showimage --ros-args -p image_topic:=/camera/image_raw
```

## 🛠️ 故障排除

### 摄像头无法打开
```bash
# 检查摄像头设备
ls -la /dev/video*

# 检查用户权限
sudo usermod -a -G video $USER

# 释放被占用的摄像头
pkill -f cheese
pkill -f guvcview
```

### 性能优化
```bash
# 降低分辨率提高性能
ros2 run my_package camera_publisher --ros-args \
  -p image_width:=320 -p image_height:=240

# 降低发布频率
ros2 run my_package camera_publisher --ros-args \
  -p publish_frequency:=15.0
```

## 📊 输出信息
```
[INFO] [camera_publisher]: 摄像头发布者节点已启动
[INFO] [camera_publisher]: 摄像头设备: /dev/video0
[INFO] [camera_publisher]: 图像分辨率: 640x480
[INFO] [camera_publisher]: 发布频率: 30.0 Hz
[INFO] [camera_publisher]: 话题名称: /camera/image_raw
[INFO] [camera_publisher]: 发布帧 #0 (640x480, FPS: 30.0)
```

## 💡 使用技巧

1. **首次使用**：先确认摄像头能正常工作
   ```bash
   # 测试摄像头
   v4l2-ctl --list-devices
   cheese  # 或其他摄像头软件
   ```

2. **多摄像头支持**：修改源码中的设备路径或添加参数

3. **性能监控**：查看日志中的FPS信息确认性能

4. **与其他节点配合**：
   ```bash
   # 终端1：启动摄像头
   ros2 run my_package camera_publisher

   # 终端2：启动订阅者
   ros2 run my_package camera_subscriber
   ```
