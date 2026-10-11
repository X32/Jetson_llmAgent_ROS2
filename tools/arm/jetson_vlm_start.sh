#!/bin/bash
# ============================================================================
# Jetson VLM 门禁服务一键启动（llama-server · Qwen2.5-VL-3B q4_k_m + mmproj-f16）
# ----------------------------------------------------------------------------
# 用途：E5-v2 串链的 VLM 门禁（是/否问答）。PC 侧 e5_grasp_v2_node 默认连
#       http://192.168.4.52:8000（--vlm-url 默认值），端口必须 8000 不是 8080。
# 位置：放 Jetson 上，如 ~/Desktop/workplace/start_vlm.sh，chmod +x 后直接跑。
#
# 用法：
#   ./start_vlm.sh        # 后台启动 + 等 health 就绪（已在跑则提示后退出）
#   ./start_vlm.sh -r     # 重启：先杀旧 llama-server 再启动（换模型/卡死时用）
#   ./start_vlm.sh -f     # 前台跑，实时看日志（Ctrl+C 停）
#   ./start_vlm.sh -s     # 只探活，不启动
# 日志：~/vlm_server.log（后台模式，tail -f 看）
# ============================================================================
set -u

BIN="$HOME/Desktop/workplace/llama.cpp/build/bin/llama-server"
MODEL="$HOME/Desktop/workplace/models/qwen_vl_gguf/qwen2.5-vl-3b-instruct-q4_k_m.gguf"
MMPROJ="$HOME/Desktop/workplace/models/qwen_vl_gguf/Qwen2.5-VL-3B-Instruct-mmproj-f16.gguf"
PORT=8000
LOG="$HOME/vlm_server.log"

health() { curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:$PORT/health" 2>/dev/null; }

case "${1:-}" in
  -s)
    code=$(health)
    if [ "$code" = "200" ]; then echo "[vlm] 在线（health 200，端口 $PORT）"
    else echo "[vlm] 不在线（health=$code，端口 $PORT）"; fi
    exit 0 ;;
  -r)
    echo "[vlm] 杀旧进程 ..."
    pkill -f llama-server && sleep 2 ;;
esac

if [ "$(health)" = "200" ]; then
  echo "[vlm] 已在跑（health 200），不用重复启动。要重启用 $0 -r"
  exit 0
fi
if pgrep -f llama-server > /dev/null; then
  echo "[vlm] 有 llama-server 进程但 health 不通（端口占用/卡死）——用 $0 -r 强制重启"
  exit 1
fi
for f in "$BIN" "$MODEL" "$MMPROJ"; do
  [ -f "$f" ] || { echo "[vlm] 缺文件：$f"; exit 1; }
done

ARGS=( -m "$MODEL"
       --mmproj "$MMPROJ"
       -ngl 99
       --ctx-size 3072
       --cache-type-k q8_0 --cache-type-v q8_0
       --flash-attn on
       --mlock
       -np 1
       -t 4
       --cache-ram 1024
       --host 0.0.0.0 --port $PORT )

if [ "${1:-}" = "-f" ]; then
  exec "$BIN" "${ARGS[@]}"                        # 前台：Ctrl+C 停
fi

nohup "$BIN" "${ARGS[@]}" > "$LOG" 2>&1 &
pid=$!
echo "[vlm] 启动中（pid=$pid，日志 $LOG）——加载模型约十几秒 ..."
for i in $(seq 1 60); do                          # 最多等 120s
  sleep 2
  if ! kill -0 "$pid" 2> /dev/null; then
    echo "[vlm] ❌ 进程退了，最后 15 行日志："; tail -15 "$LOG"; exit 1
  fi
  if [ "$(health)" = "200" ]; then
    echo "[vlm] ✅ 就绪（health 200）——PC 侧可直接跑 e5_grasp_v2_node"
    exit 0
  fi
done
echo "[vlm] ⚠️ 120s 还没就绪，看日志：tail -30 $LOG"; exit 1
