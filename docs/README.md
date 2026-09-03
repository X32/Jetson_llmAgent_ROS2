# 文档索引

本目录包含语音控制机器人项目的完整文档。

## 📚 文档列表

### 快速开始
- [**QUICKSTART.md**](../QUICKSTART.md) - 快速启动指南
  - 环境准备
  - 系统启动步骤
  - 基础测试方法
  - 故障排除

### 技术指南
- [**LLM_AGENT_TEST_GUIDE.md**](./LLM_AGENT_TEST_GUIDE.md) - LLM Agent 节点测试指南
  - 多种测试方法
  - 监控和调试工具
  - 性能基准
  - 故障排查

- [**LLM_BACKEND_GUIDE.md**](./LLM_BACKEND_GUIDE.md) - LLM 后端指南
  - 后端架构
  - 配置说明
  - 模型选择

- [**ROS2_CROSS_PLATFORM_GUIDE.md**](./ROS2_CROSS_PLATFORM_GUIDE.md) - ROS2 跨平台通信指南
  - Jetson ↔ PC 通信配置
  - 网络设置和防火墙
  - 故障排查和验证
  - 配置脚本使用

- [**LLAMACPP_FC_SOLUTION.md**](./LLAMACPP_FC_SOLUTION.md) - Function Calling 解决方案
  - 文本模式 FC 实现
  - 双模式支持
  - 测试结果

### 项目文档
- [**TROUBLESHOOTING_REPORT_2024-09-01.md**](./TROUBLESHOOTING_REPORT_2024-09-01.md) - 调试报告（2024-09-01）
  - 7 大类问题完整复盘
  - 根因分析与解决方案
  - 排查方法论与经验总结

- [**MEMORY.md**](../MEMORY.md) - 项目记忆和重要配置
  - 环境配置
  - 架构说明
  - 关键设计决策

### 主文档
- [**CLAUDE.md**](../CLAUDE.md) - 项目概览和架构
  - 系统架构
  - 构建运行命令
  - 设计模式

## 🎯 按需求查找文档

### 我想...
- **快速启动系统** → [QUICKSTART.md](../QUICKSTART.md)
- **测试节点功能** → [LLM_AGENT_TEST_GUIDE.md](./LLM_AGENT_TEST_GUIDE.md)
- **PC 远程控制 Jetson** → [ROS2_CROSS_PLATFORM_GUIDE.md](./ROS2_CROSS_PLATFORM_GUIDE.md)
- **了解 Function Calling** → [LLAMACPP_FC_SOLUTION.md](./LLAMACPP_FC_SOLUTION.md)
- **配置 LLM 后端** → [LLM_BACKEND_GUIDE.md](./LLM_BACKEND_GUIDE.md)
- **了解系统架构** → [CLAUDE.md](../CLAUDE.md)
- **查看项目配置** → [MEMORY.md](../MEMORY.md)

## 🔧 测试工具

### 工具脚本位置
```
tools/
├── test_llm_server.py              # LLM 服务器测试
├── test_fc.py                      # Function Calling 测试
├── test_llm_agent_node.py         # LLM Agent 节点测试
├── test_llm_agent.sh              # 交互式测试脚本
├── jetson_ros_config.sh           # Jetson ROS2 配置
├── pc_ros_config.sh               # PC ROS2 配置
└── diagnose_ros2_network.sh      # 网络诊断脚本
```

### 启动脚本
```
run_llamaccp_agent.sh          # LLM Agent 启动脚本
```

## 📊 文档使用建议

### 新用户
1. 阅读 [QUICKSTART.md](../QUICKSTART.md) 了解基础操作
2. 参考 [LLM_AGENT_TEST_GUIDE.md](./LLM_AGENT_TEST_GUIDE.md) 进行测试
3. 查看 [MEMORY.md](../MEMORY.md) 了解重要配置

### 开发者
1. 先读 [CLAUDE.md](../CLAUDE.md) 了解架构
2. 研究 [LLAMACPP_FC_SOLUTION.md](./LLAMACPP_FC_SOLUTION.md) 理解 FC 实现
3. 使用测试脚本验证修改

### 调试者
1. 使用 [LLM_AGENT_TEST_GUIDE.md](./LLM_AGENT_TEST_GUIDE.md) 中的监控工具
2. 参考 [MEMORY.md](../MEMORY.md) 中的环境配置
3. 运行工具脚本诊断问题

## 🔄 文档更新日志

### 2024-09-01
- ✅ 创建 LLM_AGENT_TEST_GUIDE.md
- ✅ 创建 LLAMACPP_FC_SOLUTION.md
- ✅ 创建 ROS2_CROSS_PLATFORM_GUIDE.md (PC ↔ Jetson 通信)
- ✅ 创建跨平台配置脚本 (jetson_ros_config.sh, pc_ros_config.sh)
- ✅ 更新 MEMORY.md
- ✅ 创建文档索引

### 2024-08-31
- ✅ 创建 QUICKSTART.md
- ✅ 初始项目文档

---

**维护者**: Claude Code Assistant
**项目**: 语音控制机器人 (Jetson_llmAgent_ROS2)
