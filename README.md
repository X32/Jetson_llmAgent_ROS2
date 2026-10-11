# 语音大模型机器人项目（LLM Agent × ROS2 × 机械臂抓取）

> 一条主线两段路：**阶段 1-3** 说中文指挥 Gazebo 仿真车（语音→LLM→ROS2）；
> **阶段 4（当前）** 同一条语音链末端接上机械臂——VLM 门禁 → YOLO 定位 → ACT 模仿学习抓取，双模型已全部部署进 Jetson 边缘板。
> 全程端侧离线：ASR / LLM / VLM / YOLO / ACT 均在本机或局域网内推理，不依赖任何云 API。

## 成果速览

### 阶段 4 · 机械臂抓取（E1-E11，2026-09 ~ 10，当前主线）

| 指标 | 数字 | 人话 |
| --- | --- | --- |
| 任务成功率 | **25% → 68% → 98%**，50 连全链实测 **100%** | 68% 是模型自己抓的，剩下的靠"抓空了重看一眼再抓"的营救环兜底 |
| 端到端延迟 | 12s → **5.29s**（50 把均值） | 从说完话到方块被举起来 |
| ACT 板上推理 | **4.16ms**（TRT-FP16，136MB） | 抓取动作模型，导出对齐 1.07e-06 零走样 |
| YOLO 板上推理 | **3.90ms**（TRT-FP16，8.4MB），全链含跨机 **34ms** | 定位小模型，比它还在 PC 上时（44-54ms）更快 |
| VLM 门禁 | ~3.2s（Jetson llama.cpp 量化 Qwen2.5-VL） | 干活前先问"桌上有方块吗"，答"没有"就拒绝执行 |
| 定位精度 | 0.61cm（自训 YOLO，自动标注零人工） | 换眼前先做了定价实验：误差 ≤1cm 不掉分 |

三块脑资产（VLM 门禁 + YOLO 定位 + ACT 抓取）现已全部常驻 Jetson Orin Nano 8GB；PC 只剩总指挥节点 + MuJoCo 仿真身体 + 一个契约桥。**真机形态已提前预演**：断掉任何一条跨机线都落在"拒绝执行"安全侧。

### 阶段 1-3 · 语音控制小车（截至 2026-08-26）

| 里程碑 | 内容 | 状态 |
| --- | --- | --- |
| ★1 文字闭环 | 终端输入"向前走半米" → 车前进 0.5m | ✅ Day7 |
| ★2 语音闭环 | 说"左转九十度" → 车左转 90° | ✅ Day8 |
| 感知问答 ★3 | "前方有障碍物吗" 基于激光雷达回答 | ✅ Day9 |

端到端实测延迟（说完→车动）：**1.16 ± 0.05 s**（VAD 0.50s + ASR 139ms + LLM FC 457ms + 控制 <50ms）。

## 阶段 4 · 快速开始

前提：PC（跑仿真+总指挥）+ Jetson Orin Nano（192.168.4.52，跑三个脑服务）同一局域网。
**完整步骤、故障速查、两个拒绝演示** → [`DOC/arm/E5v2串链操作指南.md`](DOC/arm/E5v2串链操作指南.md)，这里只放骨架：

```bash
# Jetson（常驻，一般不用动）：VLM 门禁 + 板上 ACT 服务
~/Desktop/workplace/jetson_vlm_start.sh                # ① VLM，:8000
cd ~/Desktop/workplace/e6_act && setsid nohup python3 e6b_act_infer_node_g2c.py \
  --engine act_fp16_g2c.engine > node_g2c.log 2>&1 < /dev/null &    # ①' ACT 服务
#   （YOLO 板上服务 yolo_board_serve_node.py 同理，见部署实录附录）

# PC 终端 A：YOLO 定位（PC 本地版 / 板上 TRT+桥版二选一）
ros2 run vision_agent yolo_grounding --ros-args -r /grounding:=/grounding_yolo   # ②

# PC 终端 B：镜像窗口（想亲眼看 3D 画面就先起它）
MUJOCO_GL=glfw /mnt/apfs/workplace/venvs/act/bin/python tools/arm/e7_mirror_viewer.py --topic /e5v2_mirror   # ③

# PC 终端 C：总指挥节点（一启动就自动执行 --text，干完挂机等下一条语音）
MUJOCO_GL=egl /mnt/apfs/workplace/venvs/act/bin/python tools/arm/e5_grasp_v3_node.py \
  --text "把桌上的方块抓起来" --mirror    # ④；v2 = 换 e5_grasp_v2_node.py（ACT 回 PC torch）
```

**记住一件事：总指挥节点自己永远不弹窗**——它用 EGL 离屏渲染（为了同时录像），3D 画面在终端 B 的镜像窗口进程里。收工姿势：臂静止 ~3s（VLM 在看图）→ 一口气做完抓取 → 举起方块收工，全程录像自动落盘。

### 阶段 4 · 架构（E11 收官形态）

```
 一句话 /voice_text
     ▼
 e5_grasp_v3 总指挥(PC)
     ├─① VLM 门禁 ──HTTP──▶ Jetson llama-server:8000（"有方块吗？"答"没有"→拒绝执行）
     ├─② YOLO 定位 ──Grounding.srv──▶ PC桥 ──话题对──▶ Jetson yolo_board_serve（TRT 3.9ms）
     ├─③ ACT 抓取 ──话题对 /act/obs→/act/chunk──▶ Jetson e6b_act_infer（TRT 4.16ms）
     ▼
 MuJoCo 仿真身体(PC)：64 步开环抓取 → 夹爪指距判抓 → 抓空？营救环重看重抓（≤3 次）
```

三条跨机线（HTTP / ACT DDS / YOLO 话题对）断任何一条都拒绝执行，不静默降级。
真机形态 = 把"总指挥+仿真身体"搬上臂的控制器、桥退役（客户端直连话题对），三块脑资产原样随板走。

### 阶段 4 · 文档与脚本索引

**文档 `DOC/arm/`**（按读的顺序）：

| 文档 | 内容 |
| --- | --- |
| `E5v2串链操作指南.md` | **怎么跑**：四个终端、故障速查、拒绝演示 |
| `E5v3-ACT上板部署实录.md` | ACT + YOLO 上板逐步命令与坑（导出→建引擎→起服务→验证） |
| `系统节点图-E5v2串链落地版.html` | 架构图（含跨机线与复现命令） |
| `experiment_E1 ~ E11_report.md` | 22 篇实验报告：感知选型 → ACT 调优 → 上板 → 50 连 |
| `抓取营救机制详解.md` / `YOLO训练步骤详解.md` / `TRT_NGC镜像提取指南.md` | 三个专题详解 |
| `阶段4.md` / `阶段4成果博客.md` / `项目收获与简历素材.md` | 阶段总结、博客、简历素材 |

**脚本 `tools/arm/`**（按系列）：

| 系列 | 干什么 |
| --- | --- |
| `e1_*` + `annotate_bbox.py` + `parse_grounding.py` | E1：VLM grounding 验收（IoU 评测、画框、输出解析） |
| `e2_eval_g2c.py` 等全套 | E2/E10：ACT 评测主力（开环/感知版/重试/加噪全家族） |
| `e3_*` + `e3b_export_onnx_g2c.py` + `e3_layernorm_plugin/` | E3：ONNX 导出、TRT 引擎、插件 |
| `e5_grasp_v2/v3_node.py` | **总指挥节点**（v2=ACT 在 PC，v3=ACT 上板，随时切换） |
| `e5_orchestrator.py` / `e5_proto_drive.sh` / `e5_latency_recorder.py` | 编排、驱动、延迟采集 |
| `e6b_act_infer_node_g2c.py` | **板上 ACT 推理服务**（Jetson，维度自适应） |
| `e6_*` 其余 | 板上评测：bench、加载、冒烟、fixture |
| `e7_mirror_viewer.py` / `e7_live_demo.sh` | 镜像窗口（独立进程，GLFW）与一键演示 |
| `yolo_train_cube.sh` / `yolo_render_frames.py` / `yolo_val_world.py` | YOLO：训练 / 自动标注数据渲染 / 世界坐标验证 |
| `yolo_board_serve_node.py` + `align/bench/bridge` | **YOLO 上板四件**：板上 TRT 服务、对齐自检、CPU 计时、PC 契约桥 |
| `jetson_vlm_start.sh` | **Jetson VLM 门禁一键启动**（scp 到板上用） |

---

# 阶段 1-3 · 语音大模型机器人控制系统（LLM Agent × ROS2）

> 说一句中文 → 离线语音识别 → LLM Function Calling → ROS2 → Gazebo 仿真车真的动起来

## 系统架构（小车线）

```
 麦克风 ──▶ voice_input ──/voice_text──▶ llm_agent ──/robot_command──▶ robot_controller ──/cmd_vel──▶ Gazebo 差速车
            silero VAD 切段                │                                │                            (自写 URDF)
            SenseVoice 离线识别            │ Ollama Qwen2.5-3B              │ 20Hz 心跳发布               /scan /odom
            (sherpa-onnx int8)             │ Function Calling               │ 三条安全兜底
                                          └─ 拒绝规则前置（零 token）        └─ stop 最高优先级
            └────────── /latency_diag 诊断话题 ──────────┐
                                                        ▼
                                          tools/latency_recorder.py（延迟自动采集）
```

**核心设计（两层契约）**：LLM 层输出 JSON（灵活、可换模型），ROS 层用强类型 `RobotCommand.msg`（编译期检查）——转换边界只有 llm_agent 一个点。Day8 接入语音时下游**零改动**，这就是消息契约的价值。阶段 4 沿用了同一设计：`/voice_text` 话题没变，只是 llm_agent 换成了抓取总指挥。

## 技术栈（小车线）

| 组件 | 选型 | 说明 |
| --- | --- | --- |
| ROS2 | Humble（Ubuntu 22.04） | 全部 ament_python + 1 个 ament_cmake（消息生成） |
| 仿真 | Gazebo Fortress + 自写 URDF 差速车 | 2 轮差速 + 激光雷达，不依赖 turtlebot3 |
| LLM | Ollama + Qwen2.5-3B Int4 | 原生 Function Calling，多轮对话记忆 |
| ASR | sherpa-onnx + SenseVoice int8（~230MB） | 完全离线、CPU 实时、中文数字友好 |
| VAD | silero VAD（2MB） | 说话停顿 0.5s 自动断句 |
| 消息 | 自定义 `my_package/msg/RobotCommand` | action / distance(米) / angle(度) / sensor_type |

## 快速开始（小车线）

### 1. 依赖准备（一次性）

```bash
python3 -m pip install sherpa-onnx sounddevice ollama numpy
sudo apt install libportaudio2
ollama pull qwen2.5:3b

# ASR 模型（~230MB，放 models/asr/）
mkdir -p models/asr && cd models/asr
wget https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17.tar.bz2
tar xvf sherpa-onnx-sense-voice-*.tar.bz2 && mv sherpa-onnx-sense-voice-* sense-voice
wget https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/silero_vad.onnx
```

### 2. 编译

```bash
cd /mnt/apfs/workplace/ROS2
colcon build --packages-select my_package robot_description robot_agent voice_input
source install/setup.bash
```

### 3. 启动（3 个终端，均先 `source install/setup.bash`）

```bash
ros2 launch robot_description robot_bringup.launch.py     # Gazebo 仿真（差速车+激光雷达）
ros2 launch robot_agent robot_agent_bringup.launch.py     # 大脑 + 肌肉
ros2 run voice_input voice_input_node                     # 耳朵（麦克风）
```

### 4. 说话测试

```
"左转九十度"   → 车左转 90°        "向前走一米"   → 车前进 1m
"再走远一点"   → 对话记忆生效      "停下"        → 立即停车
"飞到月球"     → 拒绝，车不动（零 token）
```

无麦克风时：`ros2 topic pub --once /voice_text std_msgs/msg/String "data: '向前走半米'"`

### 5. 延迟数据采集（可选）

```bash
python3 tools/latency_recorder.py
# 热身（不记录）：ros2 topic pub --once /voice_text std_msgs/msg/String "data: '停止'"
```

## 性能实测（小车线，Day8）

| 指标 | 实测值 |
| --- | --- |
| ASR 识别耗时 | 139 ms 均值（12 条热态） |
| LLM Function Calling | 457 ms 均值（10 条热态） |
| **端到端（动作类）** | **1.16 ± 0.05 s**（7 条） |
| 拒绝路径 FC | ≈1 ms（规则前置，零 token） |
| 冷启动 FC | 2.4 s（首条指令，热身后消除） |

完整 13 条原始数据：[DOC/experiment_8.md](DOC/experiment_8.md) Step8 / [results/](results/) CSV。

## 安全设计（小车线，机器人系统 ≠ 纯软件）

1. **动作完成发零速**：每个动作到期归零
2. **20Hz 零速心跳（看门狗）**：控制器死掉车不能永远跑
3. **stop 最高优先级**：立即清空当前动作
4. **退出钩子**：Ctrl+C / kill 前最后发一次零速
5. **LLM 输出参数校验**：schema 只是提示，controller 侧再验一遍
6. **拒绝规则前置**：危险指令在 LLM 调用前拦截——安全设计同时是成本设计

核心思想：**LLM 可以卡死，车不能停不下来**（fail-safe）。阶段 4 的抓取链沿用同思想：门禁不过 / 服务不可达 / ACT 超时，一律拒绝执行。

## 仓库结构

```
ROS2/
├── src/
│   ├── my_package/        # RobotCommand.msg + DetectedObject(s).msg + Grounding.srv（消息定义）
│   ├── robot_description/ # [阶段1-3] 自写 URDF 差速车 + Gazebo 一键启动
│   ├── robot_agent/       # [阶段1-3] llm_agent（大脑）+ robot_controller（肌肉）+ llm_core
│   ├── voice_input/       # [阶段1-3] 语音输入节点（VAD + SenseVoice）
│   └── vision_agent/      # [阶段4] YOLO grounding 服务 + yolo_onnx 推理核心
├── tools/
│   ├── (根)               # [阶段1-3] test_asr / latency_recorder / test_llm_* / 环境脚本
│   └── arm/               # [阶段4] 机械臂全系列脚本（e1~e7 + yolo_* + 板上服务，见上表）
├── DOC/
│   ├── (根)               # [阶段1-3] experiment_4~11 实验手册 + day* 踩坑记录
│   └── arm/               # [阶段4] experiment_E1~E11 报告 + 操作指南 + 部署实录 + 节点图
├── results/               # 延迟 CSV / 评测结果
├── models/                # 模型文件（不入库）：asr/ 等
└── llm/                   # [阶段1-3] Day6 LLM Agent 原型与测试
```

## 已知限制

- 小车线：前进/转弯为**开环时间法**（±10% 误差）；`ros2 topic pub` 不带 `--once` 会 1Hz 重复发布
- 机械臂线：**全仿真**（YOLO 只见过仿真渲染图，真机方块照片微调未做）；真语音端到端未实测（至今全靠打字灌 /voice_text）；50 连 100% 含 16 把营救救活，历史大样本口径是 98%/96% 双档——诚实边界详见 [`DOC/arm/experiment_E11_report.md`](DOC/arm/experiment_E11_report.md)
