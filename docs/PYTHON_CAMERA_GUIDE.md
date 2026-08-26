# 🐍 Python摄像头节点完整指南

## ✅ Python节点已成功创建和安装

你的Python摄像头订阅者节点已经准备就绪！

### 📁 文件位置
```
src: /mnt/apfs/workplace/ROS2/src/my_package/scripts/camera_subscriber_py.py
installed: /mnt/apfs/workplace/ROS2/install/my_package/lib/my_package/camera_subscriber_py.py
```

## 🚀 立即启动

### 方式1：直接运行Python脚本

**终端1 - 启动摄像头发布者：**
```bash
cd /mnt/apfs/workplace/ROS2
source /opt/ros/humble/setup.bash
source install/setup.bash
ros2 run my_package camera_publisher
```

**终端2 - 启动Python订阅者：**
```bash
cd /mnt/apfs/workplace/ROS2
source /opt/ros/humble/setup.bash
source install/setup.bash
ros2 run my_package camera_subscriber_py.py
```

### 方式2：直接运行源码

```bash
cd /mnt/apfs/workplace/ROS2
source /opt/ros/humble/setup.bash
python3 src/my_package/scripts/camera_subscriber_py.py
```

## 🎯 Python vs C++ 节点对比

| 特性 | Python节点 | C++节点 |
|------|-----------|---------|
| **代码简洁性** | ✅ 更简洁 | ⚠️ 较复杂 |
| **性能** | ⚠️ 较低 | ✅ 更高 |
| **启动速度** | ✅ 更快 | ⚠️ 较慢 |
| **内存使用** | ⚠️ 较高 | ✅ 较低 |
| **开发效率** | ✅ 更高 | ⚠️ 较低 |
| **适合场景** | 原型开发、测试 | 生产环境、性能要求高 |

## 🔧 Python节点特性

### 核心功能
- ✅ 订阅 `/camera/image_raw` 话题
- ✅ 使用cv_bridge进行图像转换
- ✅ OpenCV窗口实时显示
- ✅ FPS统计和性能监控
- ✅ 优雅的错误处理

### 图像处理
```python
def process_image(self, image):
    """处理图像，添加FPS信息等"""
    # 计算当前FPS
    fps_text = f'FPS: {int(current_fps)}'
    frame_text = f'Frame: {self.frame_count}'

    # 在图像上绘制文本
    cv2.putText(image, fps_text, (15, 35),
               cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
    cv2.putText(image, 'Python ROS2', (15, 70),
               cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
```

### 统计信息
- 每30帧更新FPS
- 每5秒打印详细统计
- 监控发布者状态
- 计算平均帧率

## 📊 预期运行输出

**Python订阅者终端：**
```
[INFO] [camera_subscriber_py]: Python摄像头订阅者节点已启动
[INFO] [camera_subscriber_py]: 订阅话题: /camera/image_raw
[INFO] [camera_subscriber_py]: 接收帧 #30 (FPS: 29.5)
[INFO] [camera_subscriber_py]: === 统计信息 ===
[INFO] [camera_subscriber_py]: 总帧数: 60
[INFO] [camera_subscriber_py]: 当前FPS: 29.8
[INFO] [camera_subscriber_py]: 平均FPS: 29.2
[INFO] [camera_subscriber_py]: 运行时间: 2.0秒
[INFO] [camera_subscriber_py]: 发布者状态: 活跃
```

## 🎨 扩展Python节点

### 添加图像处理功能

在`process_image()`方法中添加你的算法：

```python
def process_image(self, image):
    # 边缘检测
    edges = cv2.Canny(image, 50, 150)
    cv2.imshow('Edges', edges)

    # 高斯模糊
    blurred = cv2.GaussianBlur(image, (15, 15), 0)
    cv2.imshow('Blurred', blurred)

    # 颜色空间转换
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)

    # 人脸检测
    # face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
    # faces = face_cascade.detectMultiScale(gray, 1.3, 5)
```

### 添加图像保存功能

```python
def save_image(self, image, filename=None):
    """保存图像到文件"""
    if filename is None:
        filename = f"frame_{self.frame_count:04d}.png"
    cv2.imwrite(filename, image)
    self.get_logger().info(f"保存图像: {filename}")
```

## 🔍 故障排除

### 问题1：Python导入错误
```bash
# 检查Python依赖
pip3 install opencv-python
pip3 install sensor-msgs
```

### 问题2：权限问题
```bash
# 确保Python脚本有执行权限
chmod +x install/my_package/lib/my_package/camera_subscriber_py.py
```

### 问题3：cv_bridge错误
```bash
# 检查cv_bridge安装
sudo apt install ros-humble-cv-bridge python3-cv-bridge
```

## 🧪 测试对比

你可以同时运行Python和C++订阅者进行对比：

**终端1 - C++订阅者：**
```bash
ros2 run my_package camera_subscriber
```

**终端2 - Python订阅者：**
```bash
ros2 run my_package camera_subscriber_py.py
```

**对比性能和功能差异！**

## 📝 代码学习要点

### 1. ROS2 Python节点结构
```python
class CameraSubscriberPy(Node):
    def __init__(self):
        super().__init__('camera_subscriber_py')
        # 创建订阅者
        self.subscription = self.create_subscription(...)
```

### 2. 图像消息处理
```python
# ROS图像 → OpenCV图像
cv_image = self.bridge.imgmsg_to_cv2(msg, desired_encoding='bgr8')

# OpenCV图像 → ROS图像
ros_image = self.bridge.cv2_to_imgmsg(cv_image, encoding='bgr8')
```

### 3. 统计信息计算
```python
# FPS计算
elapsed = current_time - self.last_print_time
fps = frame_count / elapsed if elapsed > 0 else 0
```

## 🎯 下一步开发

1. **添加图像处理** - 在`process_image()`中添加算法
2. **集成AI模型** - 使用TensorFlow或PyTorch
3. **录制数据** - 使用rosbag录制摄像头数据
4. **多摄像头** - 订阅多个摄像头话题
5. **Web界面** - 添加Flask网页界面显示图像

## 💡 Python优势展示

**快速原型开发：**
- 代码更简洁易读
- 调试更方便
- 丰富的Python库支持
- 适合算法实验和测试

**🐍 开始你的Python ROS2之旅吧！**