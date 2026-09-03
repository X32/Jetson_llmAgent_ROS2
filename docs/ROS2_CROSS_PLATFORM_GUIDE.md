# ROS2 跨平台通信配置指南

## 概述

本文档详细说明如何在 Jetson Orin 上运行 LLM Agent 节点，并从 PC 远程发送 ROS2 消息进行控制。

## 网络拓扑

```
PC (192.168.1.100)          Jetson Orin (192.168.1.101)
     │                                │
     └──────── 同一网络 ──────────────┘
              │
              ▼
        ROS2 DDS 通信
        (ROS_DOMAIN_ID=0)
```

## 配置步骤

### Jetson 端配置

#### 1. 环境变量设置
```bash
# 设置统一的 ROS_DOMAIN_ID
export ROS_DOMAIN_ID=0
echo "export ROS_DOMAIN_ID=0" >> ~/.bashrc

# 网络配置
export ROS_LOCALHOST_ONLY=0
export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
```

#### 2. Python 环境激活
```bash
source ~/miniconda3/etc/profile.d/conda.sh
conda activate ros2_env
source install/setup.bash
```

#### 3. 启动 LLM Agent 节点
```bash
LLAMACPP=1 ros2 run robot_agent llm_agent
```

#### 预期输出
```
[INFO] [llm_agent]: llm_agent 就绪（后端=llama.cpp，模型=...），等待 /voice_text ...
```

### PC 端配置

#### 1. 环境变量设置
```bash
# 必须与 Jetson 使用相同的 ROS_DOMAIN_ID
export ROS_DOMAIN_ID=0

# 网络配置
export ROS_LOCALHOST_ONLY=0
export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp

# 设置 PC 的 IP 地址（推荐）
export ROS_IP=<PC的IP地址>
```

#### 2. 发送测试消息
```bash
# 测试连接
ros2 node list  # 应该能看到 /llm_agent

# 发送控制指令
ros2 topic pub --once /voice_text std_msgs/msg/String "data: '向前走半米'"

# 发送其他指令
ros2 topic pub --once /voice_text std_msgs/msg/String "data: '左转九十度'"
ros2 topic pub --once /voice_text std_msgs/msg/String "data: '停止'"
```

## 网络配置检查

### 基础连通性测试

#### Jetson 端
```bash
# 查看本机 IP 地址
ip addr show

# 查看网络接口
ip link show

# 测试与 PC 的连通性
ping <PC的IP地址>
```

#### PC 端
```bash
# 查看本机 IP 地址
ip addr show

# 测试与 Jetson 的连通性
ping <Jetson的IP地址>

# 检查节点发现
ros2 node list
```

### 网络接口配置

#### 查看网络接口
```bash
# 查看所有网络接口
ip addr show

# 查看路由表
route -n

# 查看多播路由
ip maddr show
```

#### 配置静态 IP（推荐）
```bash
# 编辑网络配置
sudo nano /etc/network/interfaces

# 添加静态 IP 配置
auto eth0
iface eth0 inet static
    address 192.168.1.101
    netmask 255.255.255.0
    gateway 192.168.1.1
```

## 防火墙配置

### 检查防火墙状态
```bash
# Ubuntu/Debian 系统
sudo ufw status

# CentOS/RHEL 系统
sudo firewall-cmd --list-all
```

### 临时关闭防火墙（测试用）
```bash
# Ubuntu/Debian
sudo ufw disable

# CentOS/RHEL
sudo systemctl stop firewalld
```

### 开放 ROS2 端口
```bash
# Ubuntu/Debian
sudo ufw allow 7400/udp
sudo ufw allow 7401/udp
sudo ufw allow 7410/udp
sudo ufw allow 7411/udp

# CentOS/RHEL
sudo firewall-cmd --add-port=7400/udp --permanent
sudo firewall-cmd --add-port=7401/udp --permanent
sudo firewall-cmd --reload
```

## 完整启动流程

### 终端1：Jetson - 启动节点
```bash
# 1. 激活环境
source ~/miniconda3/etc/profile.d/conda.sh
conda activate ros2_env
source install/setup.bash

# 2. 配置环境变量
export ROS_DOMAIN_ID=0
export ROS_LOCALHOST_ONLY=0
export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp

# 3. 启动节点
LLAMACPP=1 ros2 run robot_agent llm_agent
```

### 终端2：PC - 发送消息
```bash
# 1. 配置环境变量
export ROS_DOMAIN_ID=0
export ROS_LOCALHOST_ONLY=0
export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
export ROS_IP=<PC的IP地址>

# 2. 验证连接
ros2 node list
# 应该显示：/llm_agent

# 3. 发送控制指令
ros2 topic pub --once /voice_text std_msgs/msg/String "data: '向前走半米'"
```

### 终端3：PC - 监听输出（可选）
```bash
# 监听机器人指令
ros2 topic echo /robot_command

# 监听传感器查询答案
ros2 topic echo /agent_answer

# 监听延迟诊断
ros2 topic echo /latency_diag
```

## 通信验证

### PC 端验证步骤

#### 1. 节点发现验证
```bash
ros2 node list
# 预期输出：
# /llm_agent
```

#### 2. 话题发现验证
```bash
ros2 topic list
# 预期输出：
# /agent_answer
# /latency_diag
# /robot_command
# /rosout
# /voice_text
```

#### 3. 话题订阅详情
```bash
ros2 topic info /voice_text
# 预期输出：
# Subscription count: 1
#   - Node: /llm_agent
```

#### 4. 消息发送测试
```bash
# 发送测试消息
ros2 topic pub --once /voice_text std_msgs/msg/String "data: '向前走半米'"

# 应该立即发送，不再等待订阅者
```

### Jetson 端验证

#### 日志输出
```bash
# 应该看到：
[INFO] [llm_agent]: 收到指令: 向前走半米
[INFO] [llm_agent]: 已发布 /robot_command: action=move_forward distance=0.5 angle=0.0
[延迟] FC=1270ms 填msg+发布=0.2ms
```

## 故障排查

### 问题1：PC 看不到 Jetson 节点

#### 诊断步骤
```bash
# 1. 检查 ROS_DOMAIN_ID 是否一致
# Jetson 端
echo $ROS_DOMAIN_ID

# PC 端
echo $ROS_DOMAIN_ID

# 必须相同！建议统一使用 ROS_DOMAIN_ID=0

# 2. 检查网络连通性
ping <Jetson_IP>

# 3. 检查防火墙
sudo ufw status
```

#### 解决方案
```bash
# 统一 ROS_DOMAIN_ID
export ROS_DOMAIN_ID=0

# 确保网络连通
ping <Jetson_IP>

# 临时关闭防火墙测试
sudo ufw disable
```

### 问题2：消息发送后无响应

#### 诊断步骤
```bash
# 1. 检查话题订阅情况
ros2 topic info /voice_text

# 2. 检查节点状态
ros2 node info /llm_agent

# 3. 查看实时日志
# Jetson 端应该有接收到消息的日志
```

#### 解决方案
```bash
# 确认节点正常运行
# 在 Jetson 端检查：
ros2 node list

# 手动发送消息测试
ros2 topic pub --once /voice_text std_msgs/msg/String "data: '测试消息'"

# 检查 LLM 服务器状态
curl http://localhost:8000/v1/models
```

### 问题3：网络配置问题

#### 诊断步骤
```bash
# 1. 检查网络接口
ip addr show

# 2. 检查路由表
route -n

# 3. 检查多播配置
ip maddr show
```

#### 解决方案
```bash
# 配置正确的网络接口
export ROS_INTERFACE=eth0

# 或者指定具体 IP
export ROS_IP=<Jetson_IP>

# 添加多播路由
sudo route add -net 224.0.0.0 netmask 240.0.0.0 dev eth0
```

### 问题4：时间同步问题

#### 诊断步骤
```bash
# 检查时间差
# 在 PC 和 Jetson 上分别运行
date
```

#### 解决方案
```bash
# 同步时间
sudo ntpdate -u time.nist.gov

# 或者安装 chrony
sudo apt install chrony
sudo systemctl start chronyd
```

## 配置脚本

### Jetson 配置脚本 (`jetson_ros_config.sh`)
```bash
#!/bin/bash
# Jetson ROS2 跨平台通信配置

# 设置环境变量
export ROS_DOMAIN_ID=0
export ROS_LOCALHOST_ONLY=0
export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp

# 显示网络信息
echo "=== Jetson ROS2 配置 ==="
echo "ROS_DOMAIN_ID: $ROS_DOMAIN_ID"
echo "ROS_LOCALHOST_ONLY: $ROS_LOCALHOST_ONLY"
echo "网络接口:"
ip addr show | grep "inet " | grep -v "127.0.0.1"
echo ""
echo "✅ Jetson 配置完成"
```

### PC 配置脚本 (`pc_ros_config.sh`)
```bash
#!/bin/bash
# PC ROS2 跨平台通信配置

# 设置环境变量
export ROS_DOMAIN_ID=0
export ROS_LOCALHOST_ONLY=0
export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp

# 自动获取本机 IP
PC_IP=$(ip route get 1 | awk '{print $3;exit}')
export ROS_IP=$PC_IP

# 显示网络信息
echo "=== PC ROS2 配置 ==="
echo "ROS_DOMAIN_ID: $ROS_DOMAIN_ID"
echo "ROS_LOCALHOST_ONLY: $ROS_LOCALHOST_ONLY"
echo "ROS_IP: $ROS_IP"
echo "网络接口:"
ip addr show | grep "inet " | grep -v "127.0.0.1"
echo ""
echo "✅ PC 配置完成"
```

### 测试脚本 (`test_cross_comm.sh`)
```bash
#!/bin/bash
# 跨平台通信测试脚本

echo "=== ROS2 跨平台通信测试 ==="

# 检查 ROS_DOMAIN_ID
echo "1. 检查 ROS_DOMAIN_ID:"
echo "   当前值: $ROS_DOMAIN_ID"
echo "   推荐值: 0"

# 检查网络接口
echo ""
echo "2. 检查网络接口:"
ip addr show | grep "inet " | grep -v "127.0.0.1"

# 提示输入 Jetson IP
echo ""
echo "3. 测试网络连通性:"
read -p "请输入 Jetson IP 地址: " JETSON_IP

if [ -n "$JETSON_IP" ]; then
    echo "   测试连接到 $JETSON_IP..."
    if ping -c 2 $JETSON_IP > /dev/null; then
        echo "   ✅ 网络连通正常"
    else
        echo "   ❌ 网络不通，请检查网络配置"
        exit 1
    fi
fi

# 检查节点发现
echo ""
echo "4. 检查节点发现:"
NODES=$(ros2 node list)
if echo "$NODES" | grep -q "llm_agent"; then
    echo "   ✅ 发现 /llm_agent 节点"
else
    echo "   ❌ 未发现 /llm_agent 节点"
    echo "   可用节点: $NODES"
fi

# 检查话题
echo ""
echo "5. 检查话题:"
TOPICS=$(ros2 topic list)
if echo "$TOPICS" | grep -q "voice_text"; then
    echo "   ✅ 发现 /voice_text 话题"
else
    echo "   ❌ 未发现 /voice_text 话题"
fi

# 发送测试消息
echo ""
echo "6. 发送测试消息:"
echo "   发送指令: '向前走半米'"
ros2 topic pub --once /voice_text std_msgs/msg/String "data: '向前走半米'"

echo ""
echo "=== 测试完成 ==="
echo "如果 Jetson 端显示接收到消息，说明通信正常！"
```

## 性能优化

### 网络优化
```bash
# 设置 MTU 大小
sudo ip link set dev eth0 mtu 9000

# 禁用 IPv6（如果不需要）
sudo sysctl -w net.ipv6.conf.all.disable_ipv6=1
```

### ROS2 参数调优
```bash
# 设置 DDS 配置
export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp

# 设置共享内存大小
export CYCLONEDDS_URI=file:///tmp/cyclonedds.xml
```

## 常见使用场景

### 场景1：日常开发
```bash
# Jetson 端
./jetson_ros_config.sh
LLAMACPP=1 ros2 run robot_agent llm_agent

# PC 端
./pc_ros_config.sh
ros2 topic pub --once /voice_text std_msgs/msg/String "data: '测试指令'"
```

### 场景2：远程调试
```bash
# PC 端监控
ros2 topic echo /robot_command
ros2 topic echo /agent_answer
ros2 topic echo /latency_diag

# 同时发送指令
ros2 topic pub --once /voice_text std_msgs/msg/String "data: '左转九十度'"
```

### 场景3：多机器人控制
```bash
# 为每个机器人设置不同的 DOMAIN_ID
# 机器人1
export ROS_DOMAIN_ID=1

# 机器人2
export ROS_DOMAIN_ID=2

# 机器人3
export ROS_DOMAIN_ID=3
```

## 安全建议

### 网络安全
```bash
# 使用防火墙规则
sudo ufw allow from 192.168.1.0/24 to any

# 限制 DDS 通信范围
export ROS_LOCALHOST_ONLY=0
export ROS_INTERFACE=eth0
```

### 访问控制
```bash
# 使用 VPN 进行远程访问
# 配置网络隔离
# 监控网络流量
```

## 附录

### ROS_DOMAIN_ID 对比

| DOMAIN_ID | 用途 | 隔离级别 |
|-----------|------|----------|
| 0 | 默认/开发 | 低 |
| 1-10 | 测试环境 | 中 |
| 11-99 | 生产环境 | 高 |
| 100+ | 特殊用途 | 完全隔离 |

### 网络配置参数

| 参数 | 说明 | 推荐值 |
|------|------|--------|
| ROS_DOMAIN_ID | 通信域标识 | 0 |
| ROS_LOCALHOST_ONLY | 限制本地通信 | 0 |
| ROS_IP | 本机 IP 地址 | 自动检测 |
| ROS_INTERFACE | 网络接口 | eth0 |
| RMW_IMPLEMENTATION | DDS 实现 | rmw_cyclonedds_cpp |

### 常用命令速查

```bash
# 检查节点
ros2 node list
ros2 node info /llm_agent

# 检查话题
ros2 topic list
ros2 topic info /voice_text

# 发送消息
ros2 topic pub --once /voice_text std_msgs/msg/String "data: '指令'"

# 监听话题
ros2 topic echo /robot_command

# 检查网络
ip addr show
ping <目标IP>
```

---

**文档维护**: 本文档应随着系统配置变化及时更新
**最后更新**: 2024-09-01
**适用版本**: ROS2 Humble, Python 3.10, Jetson Orin
