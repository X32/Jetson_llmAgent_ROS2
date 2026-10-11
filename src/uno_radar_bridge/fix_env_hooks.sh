#!/bin/bash
# 修复：本机 pip 版 colcon(0.21.0) 缺少 ROS 集成组件，构建 ament_python 包时
# 不会生成 ament_prefix_path 环境钩子，导致 source 后 ros2 找不到包。
# 现象：ros2 run 报 "Package 'uno_radar_bridge' not found"
# 用法：每次 colcon build --packages-select uno_radar_bridge 之后执行一次本脚本
set -e
WS="${WS:-/mnt/apfs/workplace/ROS2}"
PKG=uno_radar_bridge
HOOK_DIR="$WS/install/$PKG/share/$PKG/hook"
DSV="$WS/install/$PKG/share/$PKG/package.dsv"

mkdir -p "$HOOK_DIR"

echo 'prepend-non-duplicate;AMENT_PREFIX_PATH;' > "$HOOK_DIR/ament_prefix_path.dsv"
cat > "$HOOK_DIR/ament_prefix_path.sh" <<'EOF'
# generated from colcon_core/shell/template/hook_prepend_value.sh.em

_colcon_prepend_unique_value AMENT_PREFIX_PATH "$COLCON_CURRENT_PREFIX"
EOF
cat > "$HOOK_DIR/ament_prefix_path.ps1" <<'EOF'
# generated from colcon_core/shell/template/hook_prepend_value.ps1.em

$env:AMENT_PREFIX_PATH = "$COLCON_CURRENT_PREFIX;" + $env:AMENT_PREFIX_PATH
EOF

if ! grep -q ament_prefix_path "$DSV"; then
  printf 'source;share/%s/hook/ament_prefix_path.ps1\nsource;share/%s/hook/ament_prefix_path.dsv\nsource;share/%s/hook/ament_prefix_path.sh\n' \
    "$PKG" "$PKG" "$PKG" >> "$DSV"
fi

echo "OK: $PKG 的 ament_prefix_path 钩子已就位"
echo "验证: source $WS/install/setup.bash && ros2 pkg prefix $PKG"
