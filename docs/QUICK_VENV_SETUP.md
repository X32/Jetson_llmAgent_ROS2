# 🔧 ROS2虚拟环境设置解决方案

## 问题: python3-venv包未安装

### ✅ 推荐解决方案: 使用virtualenv（无需sudo）

```bash
cd /mnt/apfs/workplace/ROS2

# 1. 安装virtualenv（用户级，无需sudo）
pip3 install --user virtualenv

# 2. 创建虚拟环境
virtualenv ros2_camera_env

# 3. 激活环境
source ros2_camera_env/bin/activate

# 4. 升级pip
pip install --upgrade pip

# 5. 安装基础ROS2依赖
pip install rclpy sensor-msgs-cv

# 6. 安装图像处理依赖
pip install opencv-python numpy

# 7. 安装cv_bridge
pip install cv_bridge

# 8. 安装识别依赖（如果使用识别功能）
pip install onnxruntime torch torchvision pandas pillow

# 9. 运行节点
source /opt/ros/humble/setup.bash
source install/setup.bash
ros2 run my_package camera_recognition_subscriber.py
```

### ✅ 系统级解决方案: 安装python3-venv

```bash
# 安装python3-venv包
sudo apt update
sudo apt install -y python3-venv

# 然后重新运行
./create_ros2_venv.sh
```

## 🚀 一键启动（推荐）

选择virtualenv方法，一条命令解决：

```bash
# 安装并创建虚拟环境
pip3 install --user virtualenv && virtualenv ros2_camera_env && source ros2_camera_env/bin/activate

# 安装依赖
pip install rclpy sensor-msgs-cv cv_bridge opencv-python

# 运行节点
source /opt/ros/humble/setup.bash && source install/setup.bash && ros2 run my_package camera_recognition_subscriber.py
```

## 📋 依赖安装选项

### 选项1: 最小安装（基础节点）
```bash
source ros2_camera_env/bin/activate
pip install rclpy sensor-msgs-cv cv_bridge opencv-python
```

### 选项2: 基础+识别
```bash
source ros2_camera_env/bin/activate
pip install rclpy sensor-msgs-cv cv_bridge opencv-python \
            onnxruntime torch torchvision pandas pillow
```

### 选项3: 完整安装（推荐）
```bash
source ros2_camera_env/bin/activate
pip install rclpy sensor-msgs-cv cv_bridge opencv-python \
            onnxruntime torch torchvision pandas pillow \
            matplotlib jupyter ipython
```

## 🎯 虚拟环境使用流程

**启动流程:**
```bash
# 1. 激活虚拟环境
cd /mnt/apfs/workplace/ROS2
source ros2_camera_env/bin/activate

# 2. 加载ROS2环境
source /opt/ros/humble/setup.bash
source install/setup.bash

# 3. 运行节点
ros2 run my_package camera_recognition_subscriber.py
```

**退出虚拟环境:**
```bash
deactivate
```

## 💡 为什么推荐virtualenv？

1. **无需sudo** - 用户级安装
2. **更灵活** - 支持Python 2/3
3. **更稳定** - 成熟的工具
4. **更快** - 安装速度更快

## 🛠️ 故障排除

### 问题: virtualenv安装失败
```bash
# 使用pip安装到用户目录
pip3 install --user virtualenv
# 检查安装路径
~/.local/bin/virtualenv --version
```

### 问题: 依赖冲突
```bash
# 清理并重建虚拟环境
deactivate
rm -rf ros2_camera_env
virtualenv ros2_camera_env
source ros2_camera_env/bin/activate
pip install -r requirements.txt
```

## 🎉 完成后

**测试虚拟环境:**
```bash
source ros2_camera_env/bin/activate
python3 -c "import rclpy; print('ROS2 OK')"
python3 -c "import cv2; print('OpenCV OK')"
python3 -c "import torch; print('PyTorch OK')"
```

**🎊 选择virtualenv方法，可以立即开始使用虚拟环境，无需sudo权限！**