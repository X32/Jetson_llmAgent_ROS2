#!/bin/bash
# 测试 USB 摄像头麦克风 (hw:1,0)
# 用法: ./test_mic_cam.sh

echo "🎤 准备录制 USB 摄像头麦克风 (hw:1,0)"
echo "请靠近摄像头，大声说话..."
echo "按回车开始录制 3 秒"
read

arecord -d 3 -f S16_LE -r 16000 -c 1 -D plughw:1,0 /tmp/cam_test.wav

echo "✅ 录制完成，正在回放..."
aplay /tmp/cam_test.wav

echo ""
echo "📊 文件信息:"
ls -lh /tmp/cam_test.wav
file /tmp/cam_test.wav
