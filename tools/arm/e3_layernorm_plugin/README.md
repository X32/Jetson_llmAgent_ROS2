# E3 Step4 交付：自写 TrtPlugin —— CustomLayerNorm

> 为什么有这个：ACT 模型全部是标准算子（TRT 8.6 原生支持，build 零 `UNSUPPORTED_NODE`），
> 阶段4 的回退预案生效——用 **LayerNorm** 练手写 plugin：transformer 必备、数值行为清晰好验、
> 有 TRT 原生实现可对照性能。本文是"一页说明"（接口/序列化/数值验证/踩坑），代码在旁边。

## 1. 交付物清单

| 文件 | 说明 |
| ---- | ---- |
| `e3_layernorm_plugin.cu` | 源码（kernel + IPluginV2DynamicExt 插件类 + IPluginCreator + 注册宏），~160 行 |
| `build.sh` | 编译脚本（**在 NGC 容器内跑**——宿主机无 CUDA toolkit；nvcc + TRT 头文件容器自带） |
| `libe2_layernorm_plugin.so` | 编译产物（1.1MB，宿主机 ctypes.CDLL 直接挂载） |
| `../e3_plugin_test.py` | 验证脚本：双引擎构建 + 数值对照 + 延迟对照 |

## 2. 接口契约（ONNX 侧怎么用它）

- **op_type**：`CustomLayerNorm`（dlopen 时 `REGISTER_TENSORRT_PLUGIN` 宏自动注册进 registry，名字=creator 名）
- **输入**（3 个，全 float32/linear）：`x(…, D)` 任意前导维（动态 shape）、`gamma(D,)`、`beta(D,)`
- **输出**：与 x 同 shape；`y = (x - mean_D) / sqrt(var_D + eps) * gamma + beta`（最后一维归一化，与 `nn.LayerNorm(normalized_shape=D)` 语义一致）
- **属性**：`eps`（float，默认 1e-5，ONNX 节点属性 → creator 的 PluginField → 序列化）

## 3. 实现要点（讲面试时的三个层次）

1. **kernel**（一行一个 block）：strided 累加 sum/sumsq → 共享内存树形归约 → `rsqrtf(var+eps)` 归一化；256 threads/block，D≤256×k 自动跨步。
2. **插件类**（IPluginV2DynamicExt 的生命周期）：
   - `getOutputDimensions`（用 `IExprBuilder` 表达"输出=输入同 shape"，支持动态 batch）
   - `supportsFormatCombination`（声明只吃 float32/linear）
   - `enqueue`（真正的 kernel launch，stream 由 TRT 传入——不能自己开 stream）
   - `serialize/getSerializationSize`（只存 eps——**plugin 的状态要能存取**，engine 反序列化时靠它复活）
   - `clone`（TRT 复制插件实例用）
3. **注册链**：`REGISTER_TENSORRT_PLUGIN(Creator)` → `.so` 被 `ctypes.CDLL` dlopen 时静态构造器注册 → ONNX parser 遇到 `CustomLayerNorm` 节点按名字查 registry → 引用 creator 造插件。

## 4. 数值与性能验证（2026-09-17 实测，`e3_plugin_test.py`）

| 项 | 结果 | 判据 |
| -- | ---- | ---- |
| plugin vs numpy 参照 | max\|Δ\| = 7.15e-07 | — |
| plugin vs **TRT 原生 LayerNormalization** | **max\|Δ\| = 7.15e-07** | <1e-5 ✅（富余 7 倍） |
| 延迟（N=64, D=512，单节点引擎，N=2000） | 自写 22.7μs vs 原生 23.8μs | 同量级（单节点被 launch 开销主导；不追求赢原生——练习目标是"能写对"） |

## 5. 踩坑实录（TRT 8.6 plugin 编译的 5 连坑，都写进了手册坑位#14）

1. `getOutputDimensions` 的 builder 参数在 8.6 叫 **`IExprBuilder`**（`IPluginBuilder` 是 TRT 10 的名字）；
2. **所有 override 都要 `noexcept`**（8.6 全接口 noexcept，漏了=exception specification 不兼容）；
3. `supportsFormatCombination` 是**四参**（`in` 数组同时覆盖输入+输出，用 `pos < nbInputs` 区分）；
4. `initialize()/terminate()` 是纯虚函数，**无状态插件也要空实现**，否则抽象类不能实例化；
5. nvcc 默认不链 `libnvinfer` → `.so` 报 `undefined symbol: getPluginRegistry`，编译要加 `-lnvinfer -lnvinfer_plugin`。

## 6. 复现命令

```bash
bash build.sh     # 容器内编译 → 本目录 .so
unset PYTHONPATH && export LD_LIBRARY_PATH=/mnt/apfs/workplace/trt-862/lib:/mnt/apfs/workplace/venvs/act/lib/python3.10/site-packages/torch/lib
python ../e3_plugin_test.py   # 数值 + 延迟验证
```
