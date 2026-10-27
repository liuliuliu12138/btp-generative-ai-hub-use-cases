# Deploy EXAONE-4.5-33B to SAP AI Core — 部署教程

> 目标：把 **LGAI-EXAONE/EXAONE-4.5-33B**（视觉语言模型 VLM）部署到 SAP AI Core（PoC）。
> 方案：**vLLM + AWQ 量化**（HF 官方现成的多模态 4-bit 权重）。
> 配套代码：仓库 `10-byom-oss-llm-ai-core/`（即 SAP 社区两篇博客 *Bring Open-Source LLMs into SAP AI Core with Ollama / with Custom Transformer Server* 的真身）。
> 基于上次 `exaone-deep:2.4b`（Ollama）部署经验复用，见 [Deploy_EXAONE_LLM_to_SAP.md](Deploy_EXAONE_LLM_to_SAP.md)。
> 制定日期：2026-10-27

---

## 0. 方案选型：为什么是 vLLM + AWQ

### 先认清这个模型和上次完全不是一个量级

| 维度 | 上次 `exaone-deep:2.4b`（Ollama） | 本次 `LGAI-EXAONE/EXAONE-4.5-33B` |
|---|---|---|
| 模态 | 纯文本 | **视觉语言模型 VLM（Image-Text-to-Text）** |
| 架构 | 已在 Ollama 库 | 新架构 `exaone4_5`（31.7B 语言 + 1.29B 视觉编码器）|
| 体积 | 1.6GB（Q4）| **33B，bf16 原始权重 ≈ 66–80GB** |
| HF 官方推荐后端 | Ollama | **vLLM / SGLang / TensorRT-LLM** |

### 为什么选 vLLM（仓库 Option 4，`byom-oss-llm-code/vllm/`）

1. **HF 模型卡官方就是用 vLLM 跑**，`vllm serve` 命令是一等支持。
2. **原生多模态 + OpenAI 兼容 API**，直接处理 `image_url`，匹配 VLM 本质。
3. **33B 必须靠 vLLM 的张量并行（TP）+ PagedKV + 量化**才跑得动。

**为什么不用另外两条线：**

- **Ollama（上次的方式）不适合**：需要 Ollama 库里有对应 GGUF，EXAONE-4.5 是全新多模态架构，GGUF/llama.cpp 的视觉支持不稳；且 2.4B 能塞的 `infer.s` 单卡（~16GB），33B 根本放不下。
- **Custom Transformer Server 不适合**：仓库 `transformer/app/server.py` 是**专为 Phi-3-vision 硬编码**的（`<|image_1|>` 提示格式、`device='cuda:0'` 单卡、bitsandbytes 8-bit），换 EXAONE 要大改，且单卡放不下 33B。

### 为什么选 AWQ（而不是 bf16 / FP8）

| 版本 | 每权重 | 33B 约占显存 | 精度 | PoC 适配 |
|---|---|---|---|---|
| bf16 原版 | 16 bit | ~66–80GB | 最高 | GPU 门槛太高（A100-80/H100）|
| FP8 | 8 bit | ~33GB | 接近无损 | 适合有 Hopper(H100/H200/L40S) 的场景 |
| **AWQ（选它）** | 4 bit | **~18–20GB** | 轻微下降 | **GPU 门槛最低，2×A100-40G 很宽裕** |
| GGUF | 2–8 bit | 取决于级别 | 取决于级别 | 只给 llama.cpp/Ollama，不走 vLLM |

- **AWQ 是官方现成的多模态量化权重**（`LGAI-EXAONE/EXAONE-4.5-33B-AWQ`，规格 W4A16g128），**无需自己量化**。
- vLLM 会从模型 `config.json` **自动识别 AWQ**，连 `--quantization` 都不用写。
- PoC 阶段先跑通、GPU 便宜最重要 → AWQ 最优。

---

## ⚠️ 1. 两个前置拦路虎（直接决定成败，先确认）

### 1.1 GPU resource plan（**待确认，不要用 infer.s**）

- 仓库模板默认 `infer.s` = 单张 ~16GB GPU（T4/V100 级，见 `transformer/app/server.py` 注释）—— **33B 放不下，必定失败**。
- AWQ 权重 ~18–20GB，官方示例用 **`--tensor-parallel-size 2`**，即 **2 张 GPU 做张量并行**：
  - **2×A100-40G（TP=2）** → 很宽裕，推荐；
  - 或 **单张 H200（TP=1）**。
- **行动项**：到 SAP AI Launchpad / 你的 entitlement 里确认租户开通了哪个大显存 GPU plan，把下文 `<待确认>` 的 `resourcePlan` 和 `tensorParallelSize` 填上（GPU 数 = TP 数）。

### 1.2 vLLM 版本（**待确认**）

- base 镜像 `vllm/vllm-openai` 必须新到**同时支持** `exaone4_5` 架构 **和** 该架构的 AWQ 内核（awq_marlin）。
- **行动项**：核对 vLLM release notes / supported models 里有 `exaone4_5`，**钉一个明确 tag**（不要用 `latest`），否则起容器加载模型时直接报错。

---

## 2. 关键参数表（可复用）

| 项 | 值 |
|---|---|
| 目标模型 | `LGAI-EXAONE/EXAONE-4.5-33B-AWQ`（AWQ 4-bit，多模态，~18–20GB）|
| 推理后端 | vLLM（OpenAI 兼容 API，端口 8000）|
| Docker 镜像 | `entlms.common.repositories.cloud.sap/ems/vllm-openai:ai-core` |
| base 镜像 | `vllm/vllm-openai:<钉死的版本tag>`（**待确认**支持 exaone4_5+awq）|
| registry | `entlms.common.repositories.cloud.sap`，namespace `ems`（AI Core runtime 可达）|
| ~~registry（弃用）~~ | ~~`sbda.int.repositories.cloud.sap`~~（AI Core 不可达）、~~Docker Hub~~（公司代理 push 不通）|
| GitHub fork | `https://github.com/liuliuliu12138/btp-generative-ai-hub-use-cases.git` |
| 教程工作目录 | `10-byom-oss-llm-ai-core/` |
| Dockerfile | `byom-oss-llm-code/vllm/Dockerfile` |
| serving 模板 | `byom-oss-llm-templates/vllm-template.yaml` |
| config 模板 | `byom-oss-llm-code/config.template.json` |
| scenario / executable | `vllm` / `vllm` |
| configuration name | `vllm-exaone45-33b-awq`（唯一，防 409 撞名）|
| resource_group | `oss-llm` |
| **resourcePlan** | `<待确认: A100 类大显存 plan>` |
| **tensorParallelSize** | `<待确认: = plan 的 GPU 数，官方示例 2>` |

---

## 3. 代码改造

### 3.1 `byom-oss-llm-templates/vllm-template.yaml`

相对仓库现有模板（默认 Mistral-7B、单卡、fp16、无 TP），改动：换 AWQ 模型、`dtype=auto`、新增 `--tensor-parallel-size` 和 `--trust-remote-code`、换 entlms registry 和 `docker-secret`、调大 `max-model-len`、调小 `max-num-seqs`、**删掉 `--quantization` 行**（vLLM 自动识别 AWQ）。

```yaml
apiVersion: ai.sap.com/v1alpha1
kind: ServingTemplate
metadata:
  name: vllm
  annotations:
    scenarios.ai.sap.com/description: "Run a vLLM server on SAP AI Core"
    scenarios.ai.sap.com/name: "vllm"
    executables.ai.sap.com/description: "Run a vLLM server on SAP AI Core"
    executables.ai.sap.com/name: "vllm"
  labels:
    scenarios.ai.sap.com/id: "vllm"
    ai.sap.com/version: "0.0.1"
spec:
  inputs:
    parameters:
      - name: modelName
        default: "LGAI-EXAONE/EXAONE-4.5-33B-AWQ"     # AWQ 现成多模态权重
        type: string
        description: "HF 模型路径，SDK 调用时的 model 名也用它"
      - name: dataType
        default: "auto"                                # AWQ 让 vLLM 按 config 自动取（float16），不强制
        type: string
      - name: gpuMemoryUtilization
        default: "0.90"
        type: string
      - name: maxTokenLen
        default: "8192"                                # 先小，别用官方 262144 否则 KV cache 爆显存
        type: string
      - name: maxNumBatchedTokens
        default: "8192"
        type: string
      - name: maxNumSeqs
        default: "16"                                  # 33B 显存下别用 2048
        type: string
      - name: tensorParallelSize
        default: "<待确认: = plan 的 GPU 数，官方示例 2>"
        type: string
      - name: resourcePlan
        default: "<待确认: A100 类大显存 plan；绝不能是 infer.s>"
        type: string
        description: "Resource Plan of SAP AI Core"
  template:
    apiVersion: "serving.kserve.io/v1beta1"
    metadata:
      annotations: |
        autoscaling.knative.dev/metric: concurrency
        autoscaling.knative.dev/target: 1
        autoscaling.knative.dev/targetBurstCapacity: 0
      labels: |
        ai.sap.com/resourcePlan: "{{inputs.parameters.resourcePlan}}"
    spec: |
      predictor:
        imagePullSecrets:
        - name: docker-secret
        minReplicas: 1
        maxReplicas: 1
        containers:
        - name: kserve-container
          image: entlms.common.repositories.cloud.sap/ems/vllm-openai:ai-core
          ports:
            - containerPort: 8000
              protocol: TCP
          command: ["/bin/sh", "-c"]
          args:
            - >
              set -e && echo "-------------Starting vLLM OpenAI API Server--------------"
              && python3 -m vllm.entrypoints.openai.api_server
              --model {{inputs.parameters.modelName}}
              --dtype {{inputs.parameters.dataType}}
              --gpu-memory-utilization {{inputs.parameters.gpuMemoryUtilization}}
              --tensor-parallel-size {{inputs.parameters.tensorParallelSize}}
              --trust-remote-code
              --enforce-eager
              --max-model-len {{inputs.parameters.maxTokenLen}}
              --max-num-batched-tokens {{inputs.parameters.maxNumBatchedTokens}}
              --max-num-seqs {{inputs.parameters.maxNumSeqs}}
          env:
            - name: MODEL
              value: "{{inputs.parameters.modelName}}"
```

> 说明：
> - **不写 `--served-model-name`** → 对外模型名 = HF 路径，和 SDK 调用保持同一标识，省掉对齐烦恼。
> - **不写 `HF_TOKEN`** → AWQ 卡注明无 gating、公开可下；若真遇到 401，再在 `env` 加 `HF_TOKEN`。
> - **`--enforce-eager`** 关闭 CUDA graph，省显存、首次 bring-up 更稳（代价是略慢）。

### 3.2 `byom-oss-llm-code/config.json` 的 vllm configuration 条目

（`config.json` 含机密、被 `.gitignore` 忽略，勿提交。只改 vllm 这一条，其余 configuration 保留。）

```json
{
  "name": "vllm-exaone45-33b-awq",
  "scenario_id": "vllm",
  "executable_id": "vllm",
  "input_artifacts": [],
  "parameters": [
    { "key": "modelName",            "value": "LGAI-EXAONE/EXAONE-4.5-33B-AWQ" },
    { "key": "dataType",             "value": "auto" },
    { "key": "gpuMemoryUtilization", "value": "0.90" },
    { "key": "maxTokenLen",          "value": "8192" },
    { "key": "maxNumBatchedTokens",  "value": "8192" },
    { "key": "maxNumSeqs",           "value": "16" },
    { "key": "tensorParallelSize",   "value": "<待确认: 官方示例 2>" },
    { "key": "resourcePlan",         "value": "<待确认: A100 类>" }
  ]
}
```

非机密关键字段：`resource_group=oss-llm`、registry 用 entlms。

### 3.3 `byom-oss-llm-code/vllm/Dockerfile`

基本不改，只盯 base 镜像：

```dockerfile
ARG BASE_IMAGE=vllm/vllm-openai:<钉死的版本tag>   # ⚠️ 必须支持 exaone4_5 + awq
FROM ${BASE_IMAGE}
ENV LANG C.UTF-8

# Adaptation for SAP AI Core（nobody 用户 + HF 缓存目录）
RUN mkdir -p /nonexistent/ && \
    mkdir -p /hf-home/ && \
    chown -R nobody:nogroup /nonexistent /hf-home/ && \
    chmod -R 770 /nonexistent/ /hf-home/

ENV HF_HOME=/hf-home
EXPOSE 8000
# 注意：serving template 用 command/args 覆盖了 ENTRYPOINT，原 Mistral 的 ENTRYPOINT 不影响。
```

> ⚠️ 33B AWQ 权重下载 ~18–20GB，容器 ephemeral 存储要够；`HF_HOME=/hf-home`。首次拉模型耗时较长。

---

## 4. 分步操作表

| 步骤 | 内容 | 关键点 / 上次踩坑规避 | 状态 |
|---|---|---|---|
| 0 | 前置确认：GPU plan、TP 数、vLLM 版本 | **拦路虎 §1**，必须先敲定 | ⬜ |
| 1 | 复用 `config.json` | 上次已配好 AI Core service key / entlms registry / GitHub fork | ⬜ |
| 2 | 改 `vllm-template.yaml`（§3.1）| **镜像用 tag 不用 digest**（坑⑤）；registry 用 entlms（坑⑥）| ⬜ |
| 3 | 改 `config.json` vllm 条目（§3.2）| `name=vllm-exaone45-33b-awq` 唯一防 409（坑④）| ⬜ |
| 4 | commit + push 模板到 GitHub fork | 只提交模板，勿提交 config.json | ⬜ |
| 5 | build & push 镜像到 entlms registry | 见下方命令；**不用 Docker Hub**（坑③）| ⬜ |
| 6 | 跑 `00-init-config`：onboard repo + 建 app + 同步 scenario + 建 configuration | sync=Synced / health=Healthy，configuration 创建成功 | ⬜ |
| 7 | 建 deployment，轮询至 RUNNING | registry 必须 AI Core runtime 可达（坑⑥）；首拉模型慢，耐心等 | ⬜ |
| 8 | 获取 deployment URL，写入 `vllm/env.json` | — | ⬜ |
| 9 | 直接 API 推理测试（图文 + 纯文本）| 见 §5 | ⬜ |
| 10 | GenAI Hub SDK 推理测试 | `model` 字段 = `LGAI-EXAONE/EXAONE-4.5-33B-AWQ` | ⬜ |

### 构建并推送镜像（Step 5）

```sh
cd 10-byom-oss-llm-ai-core/byom-oss-llm-code/vllm

# 登录内网 registry（AI Core runtime 可达）
docker login entlms.common.repositories.cloud.sap

# 构建（务必 --platform=linux/amd64 模拟 AI Core 环境）
docker build --platform=linux/amd64 \
  -t entlms.common.repositories.cloud.sap/ems/vllm-openai:ai-core .

# 推送
docker push entlms.common.repositories.cloud.sap/ems/vllm-openai:ai-core
```

### 创建并监控 deployment（Step 7）

沿用仓库 `vllm/01-deployment.ipynb` 的逻辑（AI Core SDK）：

```python
from ai_core_sdk.ai_core_v2_client import AICoreV2Client
import json, requests, time
from datetime import datetime

with open("../config.json") as f:
    config = json.load(f)
resource_group = config.get("resource_group", "oss-llm")
sk = config["ai_core_service_key"]
client = AICoreV2Client(
    base_url=sk["serviceurls"]["AI_API_URL"] + "/v2",
    auth_url=sk["url"] + "/oauth/token",
    client_id=sk["clientid"], client_secret=sk["clientsecret"],
    resource_group=resource_group)

with open("./env.json") as f:
    configuration_id = json.load(f)["configuration_id"]

resp = client.deployment.create(configuration_id=configuration_id,
                                resource_group=resource_group)
deployment_id = resp.id
print("deployment:", deployment_id, resp.status)
# 然后轮询 GET {AI_API_URL}/v2/lm/deployments/{deployment_id} 直到 status == RUNNING
```

> **监控要点**：deployment 日志里应看到 vLLM 加载 AWQ 权重、识别 `exaone4_5`、`awq_marlin` 内核、最后 `Uvicorn running on 0.0.0.0:8000`。
> 若长时间 PENDING 无日志 → 多半是 registry 不可达（坑⑥）或 resource plan 显存不足；若 CrashLoop → 看日志是否 vLLM 版本不认 `exaone4_5`（拦路虎 §1.2）或显存 OOM（调小 `maxTokenLen`/`maxNumSeqs` 或加大 TP/plan）。

---

## 5. 推理测试样例

部署 RUNNING 后，端点为 `{AI_API_URL}/v2/inference/deployments/{deployment_id}`，需 header：
`Authorization: Bearer <token>`、`AI-Resource-Group: oss-llm`。vLLM 暴露 OpenAI 兼容的 `/v1/chat/completions`。

### 5.1 图文（多模态）测试

```sh
curl -X POST "{DEPLOYMENT_URL}/v1/chat/completions" \
  -H "Authorization: Bearer {TOKEN}" \
  -H "AI-Resource-Group: oss-llm" \
  -H "Content-Type: application/json" \
  --data '{
    "model": "LGAI-EXAONE/EXAONE-4.5-33B-AWQ",
    "messages": [
      { "role": "user", "content": [
        { "type": "text", "text": "Describe this image in one sentence." },
        { "type": "image_url", "image_url": { "url": "https://cdn.britannica.com/61/93061-050-99147DCE/Statue-of-Liberty-Island-New-York-Bay.jpg" } }
      ]}
    ],
    "temperature": 1.0,
    "top_p": 0.95,
    "presence_penalty": 1.5
  }'
```

### 5.2 纯文本测试

```sh
curl -X POST "{DEPLOYMENT_URL}/v1/chat/completions" \
  -H "Authorization: Bearer {TOKEN}" \
  -H "AI-Resource-Group: oss-llm" \
  -H "Content-Type: application/json" \
  --data '{
    "model": "LGAI-EXAONE/EXAONE-4.5-33B-AWQ",
    "messages": [{ "role": "user", "content": "用一句话介绍 SAP AI Core。" }],
    "temperature": 1.0, "top_p": 0.95, "presence_penalty": 1.5
  }'
```

### 5.3 GenAI Hub SDK（可选）

模型名用 `LGAI-EXAONE/EXAONE-4.5-33B-AWQ`，参考仓库 `vllm/02-vllm.ipynb` 的调用方式。

> **采样参数**：AWQ 模型卡推荐 `temperature=1.0, top_p=0.95, presence_penalty=1.5`。
> **推理/thinking 模式**：EXAONE-4.5 默认开启 reasoning；延迟敏感场景可在请求里传 `"enable_thinking": false`（或 chat template 对应开关）关闭以降延迟。

---

## 6. 上次部署的坑汇总（本次规避）

| # | 坑 | 根因 | 本次怎么避 |
|---|---|---|---|
| ① | Dockerfile build 失败 `requires zstd` | Ollama 安装脚本改用 zstd | 本次用 vLLM 官方镜像，不涉及 |
| ② | build 慢 | 二进制从海外 CDN 下 | vLLM 官方镜像；AWQ 权重运行时从 HF 拉 |
| ③ | Docker Hub push 失败 | 公司代理对 Docker Hub 不稳 | **推 entlms 内网 registry** |
| ④ | onboard 409 撞名 | name 在共享租户被占 | `name=vllm-exaone45-33b-awq` 唯一 |
| ⑤ | digest 镜像引用报错 | AI Core runtime adapter 不接受 `image@sha256:` | **镜像用 tag 格式** |
| ⑥ | 一直 PENDING 不 RUNNING | `sbda` registry AI Core 不可达 | **用 entlms registry**（runtime 可达）|

---

## 7. ⚠️ 许可证红字（上生产前必读）

- **`EXAONE AI Model License Agreement 1.2 - NC`（Non-Commercial，非商用）**。
- AWQ 版和 bf16 原版同属该许可证族。
- **PoC / 内部评估一般可行；但 EMS 是 SAP 商用产品，任何生产/商用用途前，务必走 OSC（开源合规）/ 法务确认**，不要直接上商用链路。

---

## 8. 下一步 / 续作提示

- **先办**：敲定 GPU resource plan（A100 类，TP=2）与 vLLM 版本 tag（支持 `exaone4_5`+awq），把 §3 里的 `<待确认>` 填实。
- **再跑**：按 §4 分步操作表执行 Step 1 → 10。
- **跑通后**：若要省 GPU 可评估单卡大显存方案；若要更高精度可改 FP8（需 Hopper 卡）。
- Open WebUI 等前端 PoC 阶段跳过。
