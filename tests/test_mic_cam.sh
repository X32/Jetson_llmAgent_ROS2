#!/bin/bash
# 测试 USB 摄像头麦克风（自动检测 USB 声卡设备号）
# 用法: ./test_mic_cam.sh [输出文件]
#   不带参数 → 录到 /tmp/cam_test.wav
#   带相对路径 → ./test_mic_cam.sh ./test.wav 录到当前目录

OUT="${1:-/tmp/cam_test.wav}"

echo "🎤 检测 USB 麦克风设备号..."

# 自动查找 USB 声卡的 card 号（匹配 arecord -l 输出中的 "USB" 字样）
USB_CARD=$(arecord -l 2>/dev/null | grep -i "usb" | grep -oP 'card \K[0-9]+' | head -1)

if [ -z "$USB_CARD" ]; then
    echo "❌ 未找到 USB 麦克风设备！当前录音设备列表："
    arecord -l 2>/dev/null || echo "（无录音设备）"
    exit 1
fi

MIC_DEV="plughw:${USB_CARD},0"
echo "✅ 找到 USB 麦克风: card $USB_CARD → 使用 $MIC_DEV"
echo ""
echo "🎤 准备录制，请靠近麦克风大声说话..."
echo "按回车开始录制 3 秒"
read

arecord -d 3 -f S16_LE -r 16000 -c 1 -D "$MIC_DEV" "$OUT"

if [ $? -ne 0 ]; then
    echo "❌ 录制失败"
    exit 1
fi

# 音量分析：峰值太小说明没录到声音
python3 - <<EOF
import wave, struct
w = wave.open('$OUT')
samples = struct.unpack(f'<{w.getnframes()}h', w.readframes(w.getnframes()))
peak = max(abs(s) for s in samples)
print(f"📊 峰值幅度: {peak} ({'✅ 有效声音' if peak > 500 else '⚠️ 几乎静音，检查增益或对着麦克风说话'})")
EOF

echo "🔊 正在回放..."
aplay "$OUT"

echo ""
echo "📁 文件信息:"
ls -lh "$OUT"
