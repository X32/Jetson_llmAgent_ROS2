#!/bin/bash
# ============================================================================
# E7 实时渲染演示：决策+执行全链路，MuJoCo 原生窗口实时看机械臂抓方块（可旋转视角）
# ----------------------------------------------------------------------------
# 一条指令走完：/voice_text → orchestrator 意图 → act_node 快照 →
#   grounding_node 调 Jetson VLM(qwen2.5-vl-3b) 看图定位 → 坐标+门控 →
#   act_node 把观测经 DDS 发 Jetson(TRT-FP16 ACT) 拿动作 chunk → 20Hz 步进抓取
# 窗口（独立进程 e7_mirror_viewer.py）：act_node 每步发 qpos → /e5/mirror →
#   镜像进程 mj_forward+sync 原生渲染。为何独立进程：GLFW 窗口与 egl 离屏同进程
#   互斥、窗口永冻首帧（坑位#15）；分开进程 GLFW 单独跑健康。
# 你在窗口里看到：VLM 思考期静止在重置场景(~8s，终端有旁白) → 机械臂实时抓取
# 演示模式 act_node 带 --no-record：不渲染 512 显示帧、不落 mp4（省 GPU）。
#
# 用法：
#   tools/arm/e7_live_demo.sh                      # 默认指令"把桌上的方块抓起来"
#   tools/arm/e7_live_demo.sh "把红色方块提起来"    # 自定义指令
#   tools/arm/e7_live_demo.sh --headless "..."     # 不开窗口(冒烟/CI，仍走全链路)
#
# 前置：板上双服务已起（VLM :8000 + e6_act_infer_node FP16）。脚本会自动探活。
# 退出：关掉 MuJoCo 窗口，或 Ctrl+C。
# ============================================================================
set +u   # ROS setup.bash 有未定义变量，-u 会炸
CMD="把桌上的方块抓起来"
HEADLESS=0
for a in "$@"; do
  case "$a" in
    --headless) HEADLESS=1 ;;
    *) CMD="$a" ;;
  esac
done

BOARD=192.168.4.52
ROOT=/mnt/apfs/workplace/ROS2
VENV=/mnt/apfs/workplace/venvs/act/bin/python
TRTLIB=/mnt/apfs/workplace/trt-862/lib
TORCHLIB=/mnt/apfs/workplace/venvs/act/lib/python3.10/site-packages/torch/lib
CKPT_DIR=/mnt/apfs/workplace/act/ckpt_lift_ph_v2
CKPT=policy_epoch_2400_seed_0.ckpt
GLOG=/tmp/e7demo_grounding.log
ALOG=/tmp/e7demo_act.log
OLOG=/tmp/e7demo_orch.log
RLOG=/tmp/e7demo_recorder.log
MLOG=/tmp/e7demo_mirror.log
export DISPLAY=:0
export PYTHONUNBUFFERED=1   # 关键：print() 重定向到文件默认块缓冲，会让就绪探测/实时旁白全部失效

cd "$ROOT" || exit 1
PIDS=()   # 每个节点用 setsid 自成进程组，$! = PGID；cleanup 组杀穿透 ros2 run 的子进程
cleanup() { echo; echo "[demo] 收尾，停所有节点..."; for p in "${PIDS[@]}"; do kill -INT -- "-$p" 2>/dev/null; done; sleep 2; for p in "${PIDS[@]}"; do kill -9 -- "-$p" 2>/dev/null; done; }
trap cleanup EXIT INT TERM

echo "============================================================"
echo " E7 实时演示  指令：「$CMD」  $([ $HEADLESS = 1 ] && echo '(headless)' || echo '(MuJoCo 窗口)')"
echo "============================================================"

# ---- 0) 板上双服务探活 ----
echo "[demo] 探板端服务 $BOARD ..."
if curl -s --max-time 4 "http://$BOARD:8000/health" | grep -q ok; then echo "  ✓ VLM llama-server :8000"; else echo "  ✗ VLM 无响应——先在板上起 llama-server（见 DOC/arm/experiment_E7.md Step 0）"; exit 1; fi
if ssh -o ConnectTimeout=5 "zy@$BOARD" "pgrep -fc 'e6_act_infer_[n]ode'" 2>/dev/null | grep -qE '^[1-9]'; then echo "  ✓ ACT 推理节点 (TRT-FP16)"; else echo "  ✗ 板端 e6_act_infer_node 未跑——先起：python3 e6_act_infer_node.py --engine act_fp16_orin.engine"; exit 1; fi

# ---- 1) T1 grounding 节点（系统 python，E1 交付物原样） ----
echo "[demo] 起 grounding 节点 (T1) ..."
setsid bash -c 'unset PYTHONPATH; source /opt/ros/humble/setup.bash; source '"$ROOT"'/install/setup.bash
  exec ros2 run vision_agent grounding --ros-args -p server_url:=http://'"$BOARD"':8000 -p resize:=1000' > "$GLOG" 2>&1 &
PIDS+=($!)

# ---- 2) T2 act_node：remote 后端 + qpos 镜像通道；演示模式不录像（venv python） ----
echo "[demo] 起 act_node 节点 (T2, backend=remote, no-record$([ $HEADLESS = 1 ] || echo ', live-view')) ..."
LIVEFLAG="--no-record"; [ $HEADLESS = 0 ] && LIVEFLAG="--live-view --no-record"
setsid bash -c 'source /opt/ros/humble/setup.bash; source '"$ROOT"'/install/setup.bash
  export LD_LIBRARY_PATH="'"$TRTLIB"':'"$TORCHLIB"':$LD_LIBRARY_PATH"
  exec env MUJOCO_GL=egl PYTHONUNBUFFERED=1 '"$VENV"' tools/arm/e5_act_node.py --backend remote '"$LIVEFLAG"' --ckpt_dir '"$CKPT_DIR"' --ckpt '"$CKPT"'' > "$ALOG" 2>&1 &
PIDS+=($!)

# ---- 2b) T5 原生窗口（独立进程，GLFW-only，坑位#15；headless 不起） ----
MPID=""
if [ $HEADLESS = 0 ]; then
  echo "[demo] 起 MuJoCo 原生窗口进程 (T5, e7_mirror_viewer) ..."
  setsid bash -c 'source /opt/ros/humble/setup.bash; source '"$ROOT"'/install/setup.bash
    exec env MUJOCO_GL=glfw DISPLAY=:0 PYTHONUNBUFFERED=1 '"$VENV"' tools/arm/e7_mirror_viewer.py' > "$MLOG" 2>&1 &
  MPID=$!
  PIDS+=($MPID)
fi

# ---- 3) T3 orchestrator（系统 python） ----
echo "[demo] 起 orchestrator 节点 (T3) ..."
setsid bash -c 'unset PYTHONPATH; source /opt/ros/humble/setup.bash; source '"$ROOT"'/install/setup.bash
  exec env PYTHONUNBUFFERED=1 python3 tools/arm/e5_orchestrator.py --auto-retry 2' > "$OLOG" 2>&1 &
PIDS+=($!)

# ---- 4) T4 recorder（零侵入，只订阅） ----
setsid bash -c 'unset PYTHONPATH; source /opt/ros/humble/setup.bash; source '"$ROOT"'/install/setup.bash
  exec env PYTHONUNBUFFERED=1 python3 tools/arm/e5_latency_recorder.py' > "$RLOG" 2>&1 &
PIDS+=($!)

# ---- 等 act_node 就绪（robosuite import + 建环境 + boot 预热 ~15-30s） ----
echo "[demo] 等 act_node 就绪（建仿真环境 + 远端预热）..."
for i in $(seq 1 60); do
  grep -q "预热完成" "$ALOG" 2>/dev/null && { echo "  ✓ act_node 就绪（$([ $HEADLESS = 1 ] && echo headless || echo '窗口已开')）"; break; }
  grep -qiE "Traceback|Error|assert" "$ALOG" 2>/dev/null && { echo "  ✗ act_node 起失败："; tail -15 "$ALOG"; exit 1; }
  sleep 1
done
grep -q "预热完成" "$ALOG" 2>/dev/null || { echo "  ✗ act_node 60s 未就绪"; tail -15 "$ALOG"; exit 1; }
if [ $HEADLESS = 0 ]; then
  echo "[demo] 等原生窗口进程就绪（自建 robosuite 环境 ~10-20s）..."
  for i in $(seq 1 60); do
    grep -q "窗口已开" "$MLOG" 2>/dev/null && { echo "  ✓ MuJoCo 窗口已开（可拖拽旋转视角）"; break; }
    grep -qiE "Traceback|assert" "$MLOG" 2>/dev/null && { echo "  ✗ 窗口进程起失败："; tail -15 "$MLOG"; exit 1; }
    sleep 1
  done
  grep -q "窗口已开" "$MLOG" 2>/dev/null || { echo "  ✗ 窗口进程 60s 未就绪"; tail -15 "$MLOG"; exit 1; }
fi
sleep 3   # 等 grounding/orchestrator 的 DDS discovery 稳定

# ---- 5) 发指令 ----
echo "[demo] 发指令 → /voice_text ..."; echo
( unset PYTHONPATH; source /opt/ros/humble/setup.bash; source "$ROOT/install/setup.bash"
  ros2 topic pub -w 1 --once /voice_text std_msgs/msg/String "data: '$CMD'" >/dev/null 2>&1 )

# ---- 6) 实时旁白：跟随 orchestrator 阶段日志，直到 result ----
echo "────── 全链路阶段（MuJoCo 窗口同步渲染中）──────"
timeout 180 tail -n +1 -f "$OLOG" &
TAIL=$!
for i in $(seq 1 180); do
  grep -qE "e2e|端到端|result|成功|失败|success|rejected|timeout" "$RLOG" 2>/dev/null && break
  sleep 1
done
sleep 3; kill $TAIL 2>/dev/null
echo "────────────────────────────────────────────"

# ---- 7) 结论 ----
echo "[demo] recorder 对账（末行）："
grep -E "\[指令|e2e|端到端|success|xy_err" "$RLOG" 2>/dev/null | tail -8
echo
if [ $HEADLESS = 0 ]; then
  echo "[demo] 演示完成。MuJoCo 窗口仍开着——可再发指令或直接关窗退出。"
  echo "       再发一条： ros2 topic pub -w 1 --once /voice_text std_msgs/msg/String \"data: '把红色方块提起来'\""
  echo "       （关窗或 Ctrl+C 结束）"
  while kill -0 "$MPID" 2>/dev/null; do sleep 1; done   # 关窗 → mirror 进程退 → 整栈收尾
  echo "[demo] 窗口已关，收尾..."
fi
