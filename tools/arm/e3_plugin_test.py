"""E3 Step4 验证：自写 CustomLayerNorm plugin vs TRT 原生 LayerNormalization

流程：
  1. onnx.helper 手搓两个同构小图：原生 LayerNormalization 节点 / CustomLayerNorm 自定义节点
  2. ctypes.CDLL 挂载 plugin .so（REGISTER_TENSORRT_PLUGIN 宏在 dlopen 时自注册）
  3. 双引擎构建 → 数值对照（vs numpy 参照）→ 延迟对照（cuda.Event, N=2000）
判据：plugin vs 原生 max|Δ| < 1e-5；延迟如实记录（练习用 kernel 不求赢原生——差距能讲清即可）
环境：unset PYTHONPATH; export LD_LIBRARY_PATH=/mnt/apfs/workplace/trt-862/lib:.../torch/lib
"""
import ctypes
import numpy as np
import onnx
import onnx.helper as oh
import tensorrt as trt
import torch

D, N = 512, 64          # ACT transformer 的 hidden 维度 / 一个 batch 的行数
EPS = 1e-5
rng = np.random.RandomState(0)

GAMMA = (rng.randn(D).astype(np.float32) * 0.1 + 1.0)   # 权重只生成一次（rng 有状态，
BETA = (rng.randn(D).astype(np.float32) * 0.05)         # 每次 make_model 重抽会让三方对不上）

def make_model(op_type):
    x = oh.make_tensor_value_info('X', onnx.TensorProto.FLOAT, [N, D])
    y = oh.make_tensor_value_info('Y', onnx.TensorProto.FLOAT, [N, D])
    gamma = onnx.numpy_helper.from_array(GAMMA, 'gamma')
    beta = onnx.numpy_helper.from_array(BETA, 'beta')
    if op_type == 'LayerNormalization':
        node = oh.make_node('LayerNormalization', ['X', 'gamma', 'beta'], ['Y'], epsilon=EPS)
    else:
        node = oh.make_node('CustomLayerNorm', ['X', 'gamma', 'beta'], ['Y'], eps=EPS)
    g = oh.make_graph([node], 'g', [x], [y], [gamma, beta])
    m = oh.make_model(g, opset_imports=[oh.make_opsetid('', 17)])
    m.ir_version = 8
    return m

for op in ('LayerNormalization', 'CustomLayerNorm'):
    onnx.save(make_model(op), f'/tmp/ln_{op}.onnx')

# plugin 挂载（必须在 builder 之前——注册发生在 dlopen 时）
ctypes.CDLL('/mnt/apfs/workplace/ROS2/tools/arm/e3_layernorm_plugin/libe2_layernorm_plugin.so')

logger = trt.Logger(trt.Logger.ERROR)

def build(path):
    builder = trt.Builder(logger)
    net = builder.create_network(1 << int(trt.NetworkDefinitionCreationFlag.EXPLICIT_BATCH))
    parser = trt.OnnxParser(net, logger)
    ok = parser.parse_from_file(path)
    if not ok:
        for i in range(parser.num_errors):
            print('  [parser]', parser.get_error(i))
        raise SystemExit(1)
    blob = builder.build_serialized_network(net, builder.create_builder_config())
    with open(path.replace('.onnx', '.engine'), 'wb') as f:
        f.write(blob)
    return path.replace('.onnx', '.engine')

eng_native = build('/tmp/ln_LayerNormalization.onnx')
eng_plugin = build('/tmp/ln_CustomLayerNorm.onnx')

def load_run(engine_path, x):
    with open(engine_path, 'rb') as f, trt.Runtime(logger) as rt:
        eng = rt.deserialize_cuda_engine(f.read())
    ctx = eng.create_execution_context()
    dx = torch.from_numpy(x).cuda(); dy = torch.empty(N, D, device='cuda')
    ctx.execute_v2([dx.data_ptr(), dy.data_ptr()])
    return dy.cpu().numpy(), ctx, eng

x = rng.randn(N, D).astype(np.float32)
# numpy 参照（用同一套 GAMMA/BETA 常量）
ref = (x - x.mean(-1, keepdims=True)) / np.sqrt(x.var(-1, keepdims=True) + EPS) * GAMMA + BETA

y_nat, ctx_n, eng_n = load_run(eng_native, x)
y_plg, ctx_p, eng_p = load_run(eng_plugin, x)
print('== 数值对照（N=64, D=512, 随机输入）==')
print(f'原生 vs numpy 参照 : max|Δ| = {np.abs(y_nat - ref).max():.2e}')
print(f'plugin vs numpy 参照: max|Δ| = {np.abs(y_plg - ref).max():.2e}')
print(f'plugin vs 原生      : max|Δ| = {np.abs(y_plg - y_nat).max():.2e}  （判据 <1e-5）')

# 延迟对照
def bench(ctx, eng, n=2000):
    dx = torch.from_numpy(x).cuda(); dy = torch.empty(N, D, device='cuda')
    for _ in range(200):
        ctx.execute_v2([dx.data_ptr(), dy.data_ptr()])
    ev = [(torch.cuda.Event(True), torch.cuda.Event(True)) for _ in range(n)]
    torch.cuda.synchronize()
    for s, e in ev:
        s.record(); ctx.execute_v2([dx.data_ptr(), dy.data_ptr()]); e.record()
    torch.cuda.synchronize()
    return np.array([s.elapsed_time(e) for s, e in ev])

print('\n== 延迟对照（单节点引擎，cuda.Event，warmup200+N=2000）==')
for tag, ctx, eng in [('TRT 原生 LayerNorm', ctx_n, eng_n), ('自写 plugin', ctx_p, eng_p)]:
    ts = bench(ctx, eng)
    print(f'{tag:22s}: mean={ts.mean()*1000:7.2f}us p50={np.percentile(ts,50)*1000:7.2f}us')
