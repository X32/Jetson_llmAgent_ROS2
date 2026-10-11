#!/bin/bash
# E5 十指令协议驱动（手册 §6.2）：发一条指令 → 等 recorder 打出对应 [指令#N] → 下一条
# 前置：T1(grounding, resize=1000) + T2(e5_act_node) + T4(recorder) 全部在跑
# 注意：不能 set -u —— ROS setup.bash 有未定义变量（AMENT_TRACE_SETUP_FILES），-u 会炸
cd "$(dirname "$0")"
unset PYTHONPATH
source /opt/ros/humble/setup.bash
source ../install/setup.bash

REC_OUT=$1                                    # recorder 的输出文件（数 [指令#N] 行）
LOG=/tmp/e5_proto.log

INSTRS=("把桌上的方块抓起来" "抓一下方块" "请把方块拿起来" "帮我把方块举起来"
        "把那个红色方块抓起来" "把方块夹起来" "把桌上的正方体拿起来" "抓起桌上的木块"
        "把红色方块提起来" "把方块捡起来")

python3 e5_orchestrator.py --auto-retry 3 > "$LOG" 2>&1 &
OPID=$!
sleep 6

for i in $(seq 1 10); do
  ros2 topic pub -w 1 --once /voice_text std_msgs/msg/String "data: '${INSTRS[$((i-1))]}'" > /dev/null
  echo "[drive] 指令$i/${INSTRS[$((i-1))]} 已发 $(date +%H:%M:%S)"
  # 等 recorder 出现第 i 条 [指令#i]（上限 170s ≈ 4 次全失败+VLM）
  for t in $(seq 1 170); do
    n=$(grep -c "\[指令#${i}\]" "$REC_OUT" 2>/dev/null || true)
    [ "${n:-0}" -ge 1 ] && break
    sleep 1
  done
  sleep 2
done

echo "[drive] 10 条发完，等最后收尾 $(date +%H:%M:%S)"
sleep 5
kill -INT $OPID 2>/dev/null
wait $OPID 2>/dev/null
echo "[drive] 完成 $(date +%H:%M:%S)"
grep -E "指令:|done|rejected|vlm|大框" "$LOG" | tail -50
