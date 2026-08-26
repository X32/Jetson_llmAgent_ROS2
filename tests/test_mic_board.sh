#!/bin/bash
# 测试主板声卡麦克风 (plughw:0,0)
# 用法: ./test_mic_board.sh
# 前提: 需要在机箱后面板粉色孔插入 3.5mm 麦克风/耳机麦

echo "🎤 准备录制主板声卡麦克风 (plughw:0,0)"
echo "请确保机箱后面板粉色孔已插入麦克风"
echo "按回车开始录制 3 秒"
read

arecord -d 3 -f S16_LE -r 16000 -c 1 -D plughw:0,0 /tmp/board_test.wav

echo "✅ 录制完成，正在回放..."
aplay /tmp/board_test.wav

echo ""
echo "📊 文件信息:"
ls -lh /tmp/board_test.wav
file /tmp/board_test.wav

echo ""
echo "❓ 如果回放是静音，请检查:"
echo "   1. 麦克风是否正确插入后面板粉色孔"
echo "   2. 运行 pavucontrol 检查输入设备和增益"
echo "   3. 尝试前面板: plughw:0,2"
