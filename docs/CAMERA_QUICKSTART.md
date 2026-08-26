# 🎥 USB摄像头快速启动指南

## 📋 摄像头检测状态

✅ **已检测到USB摄像头:**
- 设备路径: `/dev/video0`
- 设备名称: `USB Camera (usb-0000:00:14.0-5)`
- 接口类型: USB 2.0

## 🚀 立即启动（3个命令）

### 1. 编译摄像头节点
```bash
cd /mnt/apfs/workplace/ROS2
source /opt/ros/humble/setup.bash
colcon build --packages-select my_package
```

### 2. 启动摄像头发布者
```bash
source install/setup.bash
ros2 run my_package camera_publisher
```

### 3. 启动摄像头订阅者（新终端）
```bash
source /opt/ros/humble/setup.bash
source /mnt/apfs/workplace/ROS2/install/setup.bash
ros2 run my_package camera_subscriber
```

## 📺 实时监控（可选）

### 查看摄像头图像（GUI）
```bash
ros2 run rqt_image_view rqt_image_view
```

### 查看发布频率
```bash
ros2 topic hz /camera/image_raw
```

## 🔧 新增功能

改进的 `camera_publisher.cpp` 包含：

✅ **智能摄像头检测** - 自动检查设备是否存在
✅ **多种打开方式** - 尝试V4L2和默认API
✅ **像素格式选择** - 支持MJPEG (推荐) 和YUYV
✅ **错误恢复** - 自动重试和重新初始化
✅ **详细诊断** - 显示摄像头能力和参数
✅ **FPS计算** - 实时显示发布频率

## ⚙️ 参数配置

### 使用默认配置（推荐）
```bash
ros2 run my_package camera_publisher
```

### 自定义配置
```bash
# 指定摄像头设备
ros2 run my_package camera_publisher --ros-args -p camera_device:=0

# 设置更高分辨率
ros2 run my_package camera_publisher --ros-args -p image_width:=1280 -p image_height:=720

# 设置像素格式 (0=自动, 1=MJPG推荐, 2=YUYV)
ros2 run my_package camera_publisher --ros-args -p pixel_format:=1

# 降低CPU使用率
ros2 run my_package camera_publisher --ros-args -p publish_frequency:=15.0
```

## 🧪 快速测试

运行自动化测试脚本：
```bash
cd /mnt/apfs/workplace/ROS2
./camera_quick_test.sh
```

## 📊 性能对比

| 配置 | 分辨率 | 帧率 | CPU使用 | 带宽 |
|------|--------|------|---------|------|
| 默认 | 640x480 | 30 | 中等 | 低 |
| 高清 | 1280x720 | 30 | 较高 | 中等 |
| 性能 | 320x240 | 15 | 低 | 很低 |

## 🔍 故障排除

### 问题：无法打开摄像头
```bash
# 检查权限
ls -la /dev/video0

# 添加用户到video组
sudo usermod -a -G video $USER
# 重新登录
```

### 问题：摄像头被占用
```bash
# 检查占用进程
sudo lsof /dev/video0

# 停止其他程序
killall guvcview
killall cheese
```

### 问题：编译错误
```bash
# 清理并重新编译
rm -rf build install logs
colcon build --packages-select my_package
```

## 📱 下一步

1. **图像处理** - 在camera_subscriber.cpp中添加图像算法
2. **数据录制** - 使用`ros2 bag record`录制数据
3. **多摄像头** - 启动多个camera_publisher实例
4. **AI集成** - 集成YOLO进行物体检测

## 🎉 预期结果

成功启动后，你应该看到：

**发布者终端:**
```
========================================
摄像头发布者节点已启动
========================================
摄像头设备: /dev/video0
图像分辨率: 640x480
发布频率: 30.0 Hz
话题名称: /camera/image_raw
========================================
✓ 成功使用 V4L2 API 打开摄像头
✓ 摄像头测试读取成功
发布帧 #0 (640x480)
发布帧 #30 (640x480, FPS: 29.8)
```

**订阅者终端:**
```
摄像头订阅者节点已启动
订阅话题: /camera/image_raw
显示图像: 是
接收帧 #30 (FPS: 29.5)
```

**窗口显示:**
- OpenCV窗口显示实时摄像头画面
- 图像上有时间戳和FPS信息

开始探索你的USB摄像头吧！🚀