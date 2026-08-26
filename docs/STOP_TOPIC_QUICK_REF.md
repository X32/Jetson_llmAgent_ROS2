# 🛑 停止ROS2 Topic - 快速参考

## 最常用的方法

### 1. Ctrl+C（推荐）⭐
```bash
# 在运行节点的终端中直接按 Ctrl+C
# 最简单、最安全的方法
```

### 2. killall命令
```bash
# 停止特定节点
killall camera_publisher
killall camera_subscriber

# 停止所有摄像头节点
killall camera_publisher camera_subscriber simple_camera_publisher
```

### 3. 使用停止脚本
```bash
cd /mnt/apfs/workplace/ROS2
./stop_nodes.sh
```

## 快速命令列表

| 操作 | 命令 |
|------|------|
| 停止摄像头节点 | `killall camera_publisher` |
| 停止所有节点 | `killall -9 camera_publisher camera_subscriber` |
| 查看活跃节点 | `ros2 node list` |
| 查看活跃topic | `ros2 topic list` |
| 检查topic状态 | `ros2 topic info /camera/image_raw` |

## 实际应用场景

### 场景1：测试摄像头后停止
```bash
# 终端1：启动摄像头
ros2 run my_package camera_publisher

# 测试完成后，按 Ctrl+C 停止
# 或在另一个终端：
killall camera_publisher
```

### 场景2：停止所有ROS2活动
```bash
# 一键停止所有节点
killall -9 camera_publisher camera_subscriber simple_camera_publisher publisher_node subscriber_node
```

### 场景3：清理并重新开始
```bash
# 停止所有节点
killall -9 camera_publisher camera_subscriber

# 清理守护进程
ros2 daemon stop --rm

# 重新启动
ros2 daemon start
```

## 验证停止成功

```bash
# 检查节点是否已停止
ros2 node list

# 检查topic是否消失
ros2 topic list | grep camera

# 查看进程
ps aux | grep camera_publisher
```

## 💡 小贴士

1. **优先使用Ctrl+C** - 最优雅的停止方式
2. **killall更直接** - 适合快速清理
3. **-9参数强制停止** - 当正常停止失败时使用
4. **定期清理** - 使用 `./stop_nodes.sh` 维护环境

**记住：在ROS2中，你停止的是节点，而不是topic本身！**