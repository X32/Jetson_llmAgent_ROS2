"""E6 Step3: 板上 TRT 10.3 数值对齐 + 延迟实测（手册 §六）

运行环境（Jetson 系统 python3，零 torch 依赖）:
  python3 e6_jetson_bench.py            # 在 ~/Desktop/workplace/e6_act/ 下
依赖: tensorrt 10.3（JetPack 自带）+ cuda-python 12.6 + numpy

口径（与 PC e3_trt_bench 同）:
  数值 = 夹具 50 组逐组 execute vs PC TRT-FP32 参考答案（max|Δ| + 逐chunk余弦）
  延迟 = 纯前向（输入已在 device），cuda.Event 等价计时（cudaEventRecord 包夹
         execute_async_v3），warmup 50 + N=500，报 mean/p50/p95
与 PC 版差异（TRT 8→10 API）:
  execute_v2(bindings) → set_tensor_address(name) + execute_async_v3(stream)
  torch.cuda.Event     → cudart.cudaEventCreate/Record/ElapsedTime
产物: e6_bench.json（数值+延迟全量落盘，带回 PC 写报告）
"""
import json
import os
import sys

import numpy as np
import tensorrt as trt
from cuda import cudart

FIX = 'e6_fixture.npz'
ENGINES = [('fp16', 'act_fp16_orin.engine'), ('fp32', 'act_fp32_orin.engine')]
N_WARMUP, N_BENCH = 50, 500


def check(err, what=''):
    # cuda-python 返回形态不一：有的裸 cudaError_t，有的 (cudaError_t,) 单元素 tuple
    if isinstance(err, tuple):
        err = err[0]
    if err != cudart.cudaError_t.cudaSuccess:
        raise RuntimeError(f'cuda error {err} @ {what}')


class Engine:
    """TRT 10 引擎封装：cudart 管 buffer/流/event（板上无 torch CUDA 可用——
    venv torch 2.13+cu130 与 JP6 驱动不兼容，cuda.is_available()=False）"""

    def __init__(self, path):
        logger = trt.Logger(trt.Logger.ERROR)
        with open(path, 'rb') as fh, trt.Runtime(logger) as rt:
            self.eng = rt.deserialize_cuda_engine(fh.read())
        self.ctx = self.eng.create_execution_context()
        self.names = [self.eng.get_tensor_name(i) for i in range(self.eng.num_io_tensors)]
        self.in_names = [n for n in self.names
                         if self.eng.get_tensor_mode(n) == trt.TensorIOMode.INPUT]
        self.out_name = [n for n in self.names
                         if self.eng.get_tensor_mode(n) == trt.TensorIOMode.OUTPUT][0]
        err, self.stream = cudart.cudaStreamCreate()
        check(err, 'streamCreate')
        self.ptrs, self.shapes = {}, {}
        for n in self.names:
            shape = tuple(self.eng.get_tensor_shape(n))
            self.shapes[n] = shape
            err, p = cudart.cudaMalloc(int(np.prod(shape)) * 4)
            check(err, f'malloc {n}')
            self.ptrs[n] = p
            self.ctx.set_tensor_address(n, p)
        self.out_host = np.empty(self.shapes[self.out_name], np.float32)

    def set_input(self, name, arr):
        """arr: 已连续的 float32 np 数组（形状=张量形状）→ H2D"""
        assert arr.dtype == np.float32 and arr.shape == self.shapes[name], \
            f'{name}: got {arr.dtype} {arr.shape} want {self.shapes[name]}'
        check(cudart.cudaMemcpy(self.ptrs[name], arr.ctypes.data, arr.nbytes,
                                cudart.cudaMemcpyKind.cudaMemcpyHostToDevice)[0], f'H2D {name}')

    def run(self):
        if not self.ctx.execute_async_v3(self.stream):
            raise RuntimeError('execute_async_v3 returned False')
        check(cudart.cudaStreamSynchronize(self.stream), 'sync')

    def fetch(self):
        check(cudart.cudaMemcpy(self.out_host.ctypes.data, self.ptrs[self.out_name],
                                self.out_host.nbytes,
                                cudart.cudaMemcpyKind.cudaMemcpyDeviceToHost)[0], 'D2H')
        return self.out_host.copy()

    def free(self):
        for p in self.ptrs.values():
            cudart.cudaFree(p)
        cudart.cudaStreamDestroy(self.stream)


def bench_latency(eng, n=N_BENCH):
    """cuda.Event 等价：500 对 event 预建，全异步 record 后统一 sync（PC e3 同款流水线）"""
    events = []
    for _ in range(n):
        err, e0 = cudart.cudaEventCreate(); check(err, 'evCreate')
        err, e1 = cudart.cudaEventCreate(); check(err, 'evCreate')
        events.append((e0, e1))
    for _ in range(N_WARMUP):
        eng.ctx.execute_async_v3(eng.stream)
    check(cudart.cudaStreamSynchronize(eng.stream), 'warmup sync')
    for e0, e1 in events:
        check(cudart.cudaEventRecord(e0, eng.stream), 'rec0')
        eng.ctx.execute_async_v3(eng.stream)
        check(cudart.cudaEventRecord(e1, eng.stream), 'rec1')
    check(cudart.cudaStreamSynchronize(eng.stream), 'bench sync')
    ts = []
    for e0, e1 in events:
        err, ms = cudart.cudaEventElapsedTime(e0, e1); check(err, 'elapsed')
        ts.append(ms)
        cudart.cudaEventDestroy(e0); cudart.cudaEventDestroy(e1)
    return np.asarray(ts)


def main():
    f = np.load(FIX)
    qpos, img, ref = f['obs_qpos'], f['obs_img'], f['ref_chunk']
    n_fix = len(qpos)
    results = {'fixture_n': n_fix, 'trt_version': trt.__version__,
               'n_warmup': N_WARMUP, 'n_bench': N_BENCH, 'engines': {}}

    for tag, path in ENGINES:
        if not os.path.exists(path):
            print(f'[skip] {path} 不存在'); continue
        eng = Engine(path)
        # 输入张量名对位：qpos(1,9) / image(1,2,3,84,84)
        name_q = [n for n in eng.in_names if eng.shapes[n] == (1, 9)][0]
        name_i = [n for n in eng.in_names if n != name_q][0]
        # ---- 数值：50 组夹具逐组 ----
        outs = []
        for i in range(n_fix):
            eng.set_input(name_q, qpos[i:i + 1])
            eng.set_input(name_i, img[i:i + 1])
            eng.run()
            outs.append(eng.fetch()[0])
        outs = np.asarray(outs)
        d = np.abs(outs - ref)
        cos = np.sum(outs * ref, axis=2) / (
            np.linalg.norm(outs, axis=2) * np.linalg.norm(ref, axis=2) + 1e-12)
        # ---- 延迟：夹具[0] 常驻 device，纯前向 ----
        ts = bench_latency(eng)
        eng.free()
        results['engines'][tag] = dict(
            engine=path, size_mb=round(os.path.getsize(path) / 1e6, 1),
            max_abs_diff=float(d.max()), cos_min=float(cos.min()),
            rel_err_max=float((d / (np.abs(ref) + 1e-6)).max()),
            latency_ms=dict(mean=float(ts.mean()), p50=float(np.percentile(ts, 50)),
                            p95=float(np.percentile(ts, 95)), min=float(ts.min()),
                            max=float(ts.max()), cov=float(ts.std() / ts.mean() * 100)))
        e = results['engines'][tag]
        print(f"== {tag} ({e['size_mb']}MB) ==\n"
              f"  数值: max|Δ|={e['max_abs_diff']:.2e}  余弦min={e['cos_min']:.8f}  "
              f"相对误差max={e['rel_err_max']:.2e}\n"
              f"  延迟: mean={e['latency_ms']['mean']:.2f}ms  p50={e['latency_ms']['p50']:.2f}  "
              f"p95={e['latency_ms']['p95']:.2f}  CoV={e['latency_ms']['cov']:.1f}%")

    with open('e6_bench.json', 'w') as fp:
        json.dump(results, fp, indent=1, ensure_ascii=False)
    print('\nsaved e6_bench.json')


if __name__ == '__main__':
    main()
