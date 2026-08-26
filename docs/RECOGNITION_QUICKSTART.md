# 🤖 摄像头图像识别节点 - 快速启动

## ⚡ 30秒启动

### 终端1: 启动摄像头
```bash
cd /mnt/apfs/workplace/ROS2
source /opt/ros/humble/setup.bash
source install/setup.bash
ros2 run my_package camera_publisher
```

### 终端2: 启动识别
```bash
cd /mnt/apfs/workplace/ROS2
source /opt/ros/humble/setup.bash
source install/setup.bash
ros2 run my_package camera_recognition_subscriber.py
```

## 🎯 功能对比

| 节点类型 | 功能 | 适用场景 |
|---------|------|---------|
| **camera_subscriber** | 基础图像显示 | 简单显示 |
| **camera_recognition_subscriber.py** | **AI物体识别** | **智能应用** ⭐ |

## 🤖 识别能力

**支持的物体类别 (1000类):**
- 🐕 动物 (各种犬类、猫类等)
- 🚗 车辆 (汽车、自行车、火车等)
- 🏠 物品 (家具、电器等)
- 🍎 食物 (水果、蔬菜等)
- ⚽️ 运动器材 (球类、运动项目等)

## 📊 窗口显示

**识别结果显示:**
```
┌────────────────────────────────┐
│ FPS: 28                         │
│ ImageNet识别                    │
├────────────────────────────────┤
│                                │
│     📷 摄像头实时画面             │
│                                │
├────────────────────────────────┤
│ 金毛寻回犬: 0.892              │
│ 拉布拉多巡回犬: 0.078         │
│ 卷毛寻回犬: 0.012              │
└────────────────────────────────┘
```

## 🔧 性能优化

### 降低CPU使用
```bash
# 降低摄像头分辨率
ros2 run my_package camera_publisher --ros-args \
  -p image_width:=320 -p image_height:=240

# 降低发布频率
ros2 run my_package camera_publisher --ros-args \
  -p publish_frequency:=15.0
```

### 更高识别精度
```python
# 在识别节点中修改top_n参数
processed_image = self.recognition_system.process_frame(cv_image, top_n=5)
```

## 🛠️ 故障排除

**依赖问题:**
```bash
pip3 install onnxruntime torch torchvision pandas pillow
```

**摄像头被占用:**
```bash
killall cheese
killall guvciew
```

**性能太慢:**
```bash
# 降低分辨率和频率
ros2 run my_package camera_publisher --ros-args \
  -p image_width:=320 -p image_height:=240 -p publish_frequency:=15.0
```

## 🧪 快速测试

```bash
cd /mnt/apfs/workplace/ROS2
./test_recognition_node.sh
```

## 📚 完整文档

- **详细指南**: `CAMERA_RECOGNITION_GUIDE.md`
- **Python指南**: `PYTHON_CAMERA_GUIDE.md`
- **原始识别**: `src/my_package/scripts/imgNet/camera_recognition.py`

**🎊 开始你的AI视觉之旅吧！**