#!/bin/bash

# OpenCV版本冲突修复脚本

echo "=== OpenCV版本冲突修复 ==="
echo

# 颜色定义
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${BLUE}检测OpenCV版本冲突...${NC}"
echo

# 检查冲突的OpenCV库
echo "检查本地OpenCV 3.4库:"
if [ -d "/usr/local/lib" ]; then
    echo "本地OpenCV库:"
    ls -la /usr/local/lib/ | grep "libopencv.*\.so\.3\.4" | head -5
fi

echo
echo "系统OpenCV库:"
pkg-config --modversion opencv4 2>/dev/null || echo "OpenCV 4 未找到"

echo

echo -e "${BLUE}解决方案选项:${NC}"
echo "1. 临时重命名OpenCV 3.4库（推荐）"
echo "2. 设置编译时库路径优先级"
echo "3. 使用docker容器"
echo "4. 跳过摄像头节点（当前状态）"
echo

read -p "选择解决方案 (1-4): " choice

case $choice in
    1)
        echo -e "${YELLOW}临时重命名OpenCV 3.4库...${NC}"

        # 创建备份目录
        sudo mkdir -p /usr/local/lib/opencv_backup

        # 移动OpenCV 3.4库到备份目录
        echo "备份OpenCV 3.4库..."
        sudo mv /usr/local/lib/libopencv_*3.4* /usr/local/lib/opencv_backup/ 2>/dev/null

        echo -e "${GREEN}✓ OpenCV 3.4库已备份${NC}"
        echo "现在可以重新编译摄像头节点了"
        echo "如需恢复: sudo mv /usr/local/lib/opencv_backup/* /usr/local/lib/"
        ;;

    2)
        echo -e "${YELLOW}设置库路径优先级...${NC}"

        # 创建环境变量设置文件
        cat > /tmp/opencv_build_env.sh << 'EOF'
# 优先使用系统OpenCV库
export LD_LIBRARY_PATH=/usr/lib/x86_64-linux-gnu:$LD_LIBRARY_PATH
export PKG_CONFIG_PATH=/usr/lib/x86_64-linux-gnu/pkgconfig:$PKG_CONFIG_PATH
EOF

        echo "环境变量文件已创建: /tmp/opencv_build_env.sh"
        echo "在编译前运行: source /tmp/opencv_build_env.sh"
        ;;

    3)
        echo "Docker容器方案需要额外配置，跳过..."
        ;;

    4)
        echo "保持当前状态，跳过摄像头节点编译"
        ;;

    *)
        echo -e "${RED}无效选择${NC}"
        exit 1
        ;;
esac

echo
echo -e "${GREEN}=== 修复完成 ===${NC}"
echo "现在可以尝试编译摄像头节点"