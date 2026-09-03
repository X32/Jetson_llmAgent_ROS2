#!/bin/bash
# 检查 llama.cpp Function Calling 支持和测试脚本

echo "🔍 检查当前运行的服务器..."
echo "当前运行: MLC LLM (不支持 Function Calling)"
echo ""

echo "📋 Function Calling 支持对比:"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "服务器类型          | FC 支持 | 推荐度"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "MLC LLM             | ❌      | ⭐ (边缘优化)"
echo "llama.cpp           | ✅      | ⭐⭐⭐⭐⭐"
echo "Ollama              | ✅      | ⭐⭐⭐⭐"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

echo "🔧 解决方案:"
echo ""
echo "方案1: 使用标准 llama.cpp（推荐）"
echo "  - 下载: git clone https://github.com/ggerganov/llama.cpp"
echo "  - 编译: cd llama.cpp && make"
echo "  - 运行: ./llama-server --model /path/to/Qwen2.5-3B-Instruct-q4_0.gguf --port 8000"
echo ""

echo "方案2: 使用 Ollama（最简单）"
echo "  - 安装: curl https://ollama.com/install.sh | sh"
echo "  - 拉取: ollama pull qwen2.5:3b"
echo "  - 运行: ollama serve"
echo "  - 修改配置: base_url=http://localhost:11434"
echo ""

echo "方案3: 升级 MLC LLM 到支持 FC 的版本"
echo "  - 检查最新版本: pip install --upgrade mlc-llm"
echo "  - 或者使用 MLC LLM 的 REST API（非 OpenAI 兼容）"
echo ""

echo "⚡ 快速测试当前服务器:"
echo "curl -X POST http://localhost:8000/v1/chat/completions \\"
echo "  -H 'Content-Type: application/json' \\"
echo "  -d '{\"model\": \"/workspace/dist/Qwen2.5-3B-Instruct-q4f16_1-MLC\", \"messages\": [{\"role\": \"user\", \"content\": \"你好\"}]}'"
