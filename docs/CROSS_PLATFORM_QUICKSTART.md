# ROS2 跨平台通信快速开始

## 🚀 30秒配置指南

### Jetson 端 (3步)
```bash
# 1. 运行配置脚本
cd tools
./jetson_ros_config.sh

# 2. 启动节点
LLAMACPP=1 ros2 run robot_agent llm_agent

# ✅ 完成！节点已启动
```

### PC 端 (2步)
```bash
# 1. 运行配置脚本
cd tools
./pc_ros_config.sh

# 2. 发送消息
ros2 topic pub --once /voice_text std_msgs/msg/String "data: '向前走半米'"

# ✅ 完成！消息已发送
```

## 🔧 关键配置要点

### 必须相同
- **ROS_DOMAIN_ID**：两端都必须是 `0`
- **网络连通性**：同一网段，能互相 ping 通

### 自动配置
- **ROS_IP**：脚本自动检测
- **网络接口**：自动选择合适的接口

## 📋 完整流程

### 1. 检查网络连通性
```bash
# PC 端测试
ping <Jetson_IP>

# 应该能 ping 通
```

### 2. 配置环境 (使用脚本)
```bash
# Jetson 端
./tools/jetson_ros_config.sh

# PC 端
./tools/pc_ros_config.sh
```

### 3. 启动服务
```bash
# Jetson 端启动节点
LLAMACPP=1 ros2 run robot_agent llm_agent

# PC 端验证连接
ros2 node list  # 应该看到 /llm_agent
```

### 4. 发送控制指令
```bash
# PC 端发送指令
ros2 topic pub --once /voice_text std_msgs/msg/String "data: '向前走半米'"
ros2 topic pub --once /voice_text std_msgs/msg/String "data: '左转九十度'"
ros2 topic pub --once /voice_text std_msgs/msg/String "data: '停止'"
```

## ⚡ 一键测试脚本

```bash
# 使用快速测试
cd tools
./quick_test.sh
```

## 🔍 常见问题解决

### PC 看不到 Jetson 节点
```bash
# 确认 ROS_DOMAIN_ID 相同
echo $ROS_DOMAIN_ID  # 两端都应该显示 0

# 确认网络连通
ping <Jetson_IP>
```

### 消息发送后无响应
```bash
# 检查节点状态
ros2 node list
ros2 topic info /voice_text

# 查看 Jetson 日志
# 应该显示：[INFO] [llm_agent]: 收到指令: ...
```

## 📚 详细文档

完整配置指南请参考：[ROS2_CROSS_PLATFORM_GUIDE.md](./ROS2_CROSS_PLATFORM_GUIDE.md)

---

**快速开始，5分钟内完成配置！** 🎯
