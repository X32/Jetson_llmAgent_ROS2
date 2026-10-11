// E3 Step4 · TrtPlugin 练习：CustomLayerNorm（IPluginV2DynamicExt，TRT 8.6）
//
// 为什么选 LayerNorm 练手：transformer 必备、数值行为清晰（好验证）、TRT 有原生实现可对照性能。
// 实现：对最后一维 D 做 LayerNorm（y = (x-mean)/sqrt(var+eps)*gamma + beta），
//       前导维任意（动态 shape），一行一个 thread block，共享内存两段归约（sum/sumsq）。
// 对外契约（ONNX 侧）：op_type = "CustomLayerNorm"，3 输入 (x, gamma[D], beta[D])，属性 eps；
//                      输出与 x 同 shape，float32/linear。
// 编译（容器内）：见同目录 build.sh（宿主机无 CUDA toolkit，用 NGC 容器的 nvcc + TRT 头）
// 注册：REGISTER_TENSORRT_PLUGIN 宏 → .so 被 dlopen 时自注册（Python 侧 ctypes.CDLL 即挂载）

#include <NvInfer.h>
#include <NvInferPlugin.h>
#include <cuda_runtime.h>
#include <cstdio>
#include <cstring>
#include <string>
#include <vector>

using namespace nvinfer1;

#define CHK(x) do { cudaError_t s = (x); if (s != cudaSuccess) {                 \
    fprintf(stderr, "CUDA error %s at %d\n", cudaGetErrorString(s), __LINE__); } } while (0)

// ---------------- kernel：一行一个 block，两段归约 ----------------
constexpr int TPB = 256;   // threads per block

__global__ void layernorm_kernel(const float* __restrict__ x,      // (rows, D)
                                 const float* __restrict__ gamma,  // (D,)
                                 const float* __restrict__ beta,   // (D,)
                                 float* __restrict__ y, int D, float eps) {
    const int row = blockIdx.x;
    const float* xr = x + (long long)row * D;
    float* yr = y + (long long)row * D;
    __shared__ float s_sum[TPB], s_sq[TPB];
    float t_sum = 0.f, t_sq = 0.f;
    for (int i = threadIdx.x; i < D; i += TPB) {          // strided 累加
        float v = xr[i];
        t_sum += v;
        t_sq += v * v;
    }
    s_sum[threadIdx.x] = t_sum;
    s_sq[threadIdx.x] = t_sq;
    __syncthreads();
    for (int s = TPB / 2; s > 0; s >>= 1) {               // 树形归约
        if (threadIdx.x < s) {
            s_sum[threadIdx.x] += s_sum[threadIdx.x + s];
            s_sq[threadIdx.x] += s_sq[threadIdx.x + s];
        }
        __syncthreads();
    }
    const float mean = s_sum[0] / D;
    const float var = s_sq[0] / D - mean * mean;
    const float rstd = rsqrtf(var + eps);
    for (int i = threadIdx.x; i < D; i += TPB)
        yr[i] = (xr[i] - mean) * rstd * gamma[i] + beta[i];
}

// ---------------- 动态 shape 插件 ----------------
class E2LayerNormPlugin : public IPluginV2DynamicExt {
public:
    E2LayerNormPlugin(float eps) : m_eps(eps) {}
    E2LayerNormPlugin(const void* data, size_t len) {
        std::memcpy(&m_eps, data, sizeof(float));
    }

    int getNbOutputs() const noexcept override { return 1; }
    DimsExprs getOutputDimensions(int32_t idx, const DimsExprs* inputs, int32_t nb,
                                  IExprBuilder&) noexcept override {
        // 输出与输入 0 同 shape
        return inputs[0];
    }
    bool supportsFormatCombination(int32_t pos, const PluginTensorDesc* in, int32_t nbIn,
                                   int32_t nbOut) noexcept override {
        // 8.6 签名：in 数组覆盖输入+输出（pos < nbIn 为输入，否则输出）
        return in[pos].format == PluginFormat::kLINEAR && in[pos].type == DataType::kFLOAT;
    }
    void configurePlugin(const DynamicPluginTensorDesc* in, int32_t nbIn,
                         const DynamicPluginTensorDesc* out, int32_t nbOut) noexcept override {}
    size_t getWorkspaceSize(const PluginTensorDesc*, int32_t, const PluginTensorDesc*,
                            int32_t) const noexcept override { return 0; }
    int32_t enqueue(const PluginTensorDesc* in, const PluginTensorDesc*,
                    const void* const* inputs, void* const* outputs, void*,
                    cudaStream_t stream) noexcept override {
        const int D = in[0].dims.d[in[0].dims.nbDims - 1];
        long long total = 1;
        for (int i = 0; i < in[0].dims.nbDims; i++) total *= in[0].dims.d[i];
        const int rows = (int)(total / D);
        layernorm_kernel<<<rows, TPB, 0, stream>>>(
            (const float*)inputs[0], (const float*)inputs[1], (const float*)inputs[2],
            (float*)outputs[0], D, m_eps);
        return cudaGetLastError() == cudaSuccess ? 0 : 1;
    }
    DataType getOutputDataType(int, const DataType* in, int) const noexcept override {
        return DataType::kFLOAT;
    }

    // 序列化（eps 一个 float）
    size_t getSerializationSize() const noexcept override { return sizeof(float); }
    void serialize(void* buf) const noexcept override { std::memcpy(buf, &m_eps, sizeof(float)); }

    // IPluginV2 生命周期钩子（无状态插件：空实现即可）
    int32_t initialize() noexcept override { return 0; }
    void terminate() noexcept override {}

    const char* getPluginType() const noexcept override { return "CustomLayerNorm"; }
    const char* getPluginVersion() const noexcept override { return "1"; }
    const char* getPluginNamespace() const noexcept override { return ""; }
    void setPluginNamespace(const char*) noexcept override {}
    void destroy() noexcept override { delete this; }
    IPluginV2DynamicExt* clone() const noexcept override {
        return new E2LayerNormPlugin(m_eps);
    }

private:
    float m_eps;
};

// ---------------- creator ----------------
class E2LayerNormCreator : public IPluginCreator {
public:
    E2LayerNormCreator() {
        m_attrs.emplace_back(PluginField{"eps", nullptr, PluginFieldType::kFLOAT32, 1});
        m_fc.nbFields = (int)m_attrs.size();
        m_fc.fields = m_attrs.data();
    }
    const char* getPluginName() const noexcept override { return "CustomLayerNorm"; }
    const char* getPluginVersion() const noexcept override { return "1"; }
    const PluginFieldCollection* getFieldNames() noexcept override { return &m_fc; }
    IPluginV2* createPlugin(const char*, const PluginFieldCollection* fc) noexcept override {
        float eps = 1e-5f;
        for (int i = 0; i < fc->nbFields; i++)
            if (!std::strcmp(fc->fields[i].name, "eps")) eps = *(const float*)fc->fields[i].data;
        return new E2LayerNormPlugin(eps);
    }
    IPluginV2* deserializePlugin(const char*, const void* data, size_t len) noexcept override {
        return new E2LayerNormPlugin(data, len);
    }
    void setPluginNamespace(const char*) noexcept override {}
    const char* getPluginNamespace() const noexcept override { return ""; }

private:
    PluginFieldCollection m_fc{};
    std::vector<PluginField> m_attrs;
};

REGISTER_TENSORRT_PLUGIN(E2LayerNormCreator);
