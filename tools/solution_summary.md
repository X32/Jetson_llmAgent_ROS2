# Function Calling 解决方案总结

## 问题现状
- **当前**: MLC LLM 服务器（不支持 Function Calling）
- **硬件**: Jetson Orin (7.4GB RAM, ARM64)
- **需求**: 机器人控制需要 Function Calling

## 解决方案对比

### 方案1: 文本解析替代 FC（最快）
**原理**: 从模型文本输出中解析指令
```python
# 优点：无需换服务器
# 缺点：可靠性较低，需要复杂的正则表达式
```

### 方案2: 标准 llama.cpp（推荐）
**优点**:
- ✅ 支持 Function Calling
- ✅ ARM64 兼容
- ✅ 轻量级部署

**步骤**:
```bash
# 1. 下载 llama.cpp
git clone https://github.com/ggerganov/llama.cpp
cd llama.cpp

# 2. 编译（Jetson Orin 需要 CUDA 支持）
cmake -B build -DCMAKE_CUDA_COMPILER=/usr/local/cuda/bin/nvcc \
  -DGGML_CUDA=ON -DCMAKE_BUILD_TYPE=Release
cmake --build build --parallel

# 3. 下载 Qwen2.5 模型
wget https://huggingface.co/Qwen/Qwen2.5-3B-Instruct-GGUF/resolve/main/qwen2.5-3b-instruct-q4_0.gguf

# 4. 启动服务器
./llama-server --model qwen2.5-3b-instruct-q4_0.gguf \
  --host 0.0.0.0 --port 8080 --ctx-size 2048
```

### 方案3: Docker 方案
**使用支持 ARM64 的容器镜像**

## 推荐行动
1. **短期**: 使用方案1让系统先运行起来
2. **长期**: 编译 llama.cpp 获得完整 FC 支持
