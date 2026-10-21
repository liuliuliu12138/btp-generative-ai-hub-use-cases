# Deploy EXAONE LLM to SAP AI Core — 操作追溯记录

> 目标：按教程 [Bring Open-Source LLMs into SAP AI Core with Ollama](https://community.sap.com/t5/artificial-intelligence-blogs-posts/bring-open-source-llms-into-sap-ai-core-with-ollama/ba-p/13659769) 把 **EXAONE Deep 最小模型** 部署到 SAP AI Core（PoC）。
> 方案：Ollama 推理服务器（镜像与模型解耦，模型运行时动态拉取）。
> 记录开始：2026-10-14

---

## 关键参数（可复用）

| 项 | 值 |
|---|---|
| 目标模型 | `exaone-deep:2.4b`（Ollama 库，1.6GB，Q4_K_M，32K ctx）—— EXAONE Deep 最小 |
| **Docker 镜像（部署用）** | **`entlms.common.repositories.cloud.sap/ems/ollama:ai-core`**（digest `sha256:0552c7f5a3b1…`） |
| registry（当前） | `entlms.common.repositories.cloud.sap`，namespace `ems` |
| ~~registry（弃用）~~ | ~~`sbda.int.repositories.cloud.sap`~~（AI Core runtime 无法访问，已废弃） |
| ~~Docker Hub user~~ | ~~`maggieliu714005548`~~（弃用，公司网络 push 不通） |
| GitHub fork | `https://github.com/liuliuliu12138/btp-generative-ai-hub-use-cases.git` |
| 本地仓库根 | `/Users/I326998/git/btp-generative-ai-hub-use-cases` |
| 教程工作目录 | `10-byom-oss-llm-ai-core/` |
| Dockerfile | `10-byom-oss-llm-ai-core/byom-oss-llm-code/ollama/Dockerfile` |
| serving 模板 | `10-byom-oss-llm-ai-core/byom-oss-llm-templates/ollama-template.yaml` |
| config 模板 | `10-byom-oss-llm-ai-core/byom-oss-llm-code/config.template.json` |
| resource plan | `infer.s`（带 GPU，2.4B 够用） |
| resource_group | `oss-llm` |
| **deployment_url** | `https://api.ai.prod.eu-central-1.aws.ml.hana.ondemand.com/v2/inference/deployments/d241483ed1f30659` |
| deployment_id（当前） | `d241483ed1f30659`（RUNNING ✅） |
| configuration_id（当前） | `a406553d-a87a-473e-a100-b3dea96a6621` |

---

## 前置条件核对

| 项 | 状态 | 备注 |
|---|---|---|
| ① SAP AI Core（Standard/Extended）+ service key | ✅ | 已写入 config.json |
| ② 内网 registry 账号 | ✅ | `entlms.common.repositories.cloud.sap`，凭证用户自留 |
| ③ GitHub 可写 fork | ✅ `liuliuliu12138/...` | 模板已 push |
| ④ 执行方式 | ✅ 由 Claude 用终端命令/脚本代跑 | notebook cell → CLI/python |
| 本地 Docker | ✅ 已安装 | daemon 需手动 `open -a Docker` 启动 |

---

## 步骤总表

| 步骤 | 内容 | EXAONE 改动 | 状态 |
|---|---|---|---|
| 0 | 前置条件核对 | — | ✅ 完成 |
| 1 | 准备 Dockerfile | 无需改（镜像与模型无关） | ✅ 完成 |
| 2 | 构建并推送 Docker 镜像 | 推到内网 registry（Docker Hub 被挡） | ✅ 完成 |
| 3 | 改 ollama-template.yaml | modelName→exaone-deep:2.4b；image→entlms registry；secret→docker-secret | ✅ 完成 |
| 4 | 准备 config.json | 保留全部 configurations，ollama 项改 EXAONE | ✅ 完成 |
| 5 | 00-init-config：onboard repo+建 app+同步 scenario+建 configuration | — | ✅ 完成 |
| 6 | 创建 deployment，等 RUNNING | 换 entlms registry 后成功 RUNNING | ✅ 完成 |
| 7a | 获取 deployment URL | — | ✅ 完成 |
| 7b | 拉取 exaone-deep:2.4b 到容器 | 模型名 exaone-deep:2.4b | ✅ 完成 |
| 7c | 直接 API 推理测试 | — | ⬜ 待用户手动执行 |
| 7d | GenAI Hub SDK 推理测试 | — | ⬜ 未开始 |
| 8（可选） | 接 Open WebUI | PoC 跳过 | ⬜ 跳过 |

---

## 步骤日志

### Step 0 — 前置条件核对 ✅
- 结果：AI Core service key 在手；Docker Hub 账号已建（`maggieliu714005548`）；GitHub fork 已就位；执行方式=Claude 代跑。

### Step 1 — 准备 Dockerfile ✅
- 做了什么：确认 `ollama/Dockerfile` 就位。其做三件适配：装 Ollama+nginx；nginx 把 `/v1/api/*` 反代到 Ollama 的 `/api/*`（AI Core 要求端点带 /v1 前缀），`/v1/chat/completions` 原样转发；为 nobody 用户建 `/nonexistent/.ollama`，EXPOSE 8080，CMD 同时起 nginx + `ollama serve`。
- EXAONE 改动：**无**。镜像与模型解耦，模型运行时拉取。
- **坑①（已修复）**：首次 build 失败，报 `This version requires zstd for extraction`。Ollama 新版安装脚本改用 zstd，教程 Dockerfile 未装。修复：apt 安装列表加 `zstd`。
- 结果：✅ 文件就位，验收通过。

### Step 2 — 构建并推送 Docker 镜像 ✅
- build 命令：
  ```sh
  docker build --platform=linux/amd64 \
    -f .../ollama/Dockerfile \
    -t docker.io/maggieliu714005548/ollama:ai-core \
    .../ollama
  ```
- **坑②（下载慢）**：build 时下载 Ollama 二进制来自 ollama.com CDN，国内镜像加速对其无效。
- **坑③（push 失败）**：公司网络代理（squid:3128）对 Docker Hub push 不稳，`use of closed network connection`，无法修复。
- **解法**：改推内网 registry `sbda.int.repositories.cloud.sap/ems/ollama:ai-core`，一次成功。digest `sha256:0552c7f5a3b1…`。

### Step 2 追加 — 镜像迁移到 entlms registry ✅
- **根因**：`sbda.int.repositories.cloud.sap` 是内部开发用 registry，AI Core runtime 网络无法访问，导致 deployment 长时间 PENDING。
- 同事建议换用 `entlms.common.repositories.cloud.sap`（AI Core 可访问的 registry）。
- 操作：
  ```sh
  docker login entlms.common.repositories.cloud.sap   # 用户操作
  docker tag sbda.int.repositories.cloud.sap/ems/ollama:ai-core \
             entlms.common.repositories.cloud.sap/ems/ollama:ai-core
  docker push entlms.common.repositories.cloud.sap/ems/ollama:ai-core
  ```
- 结果：✅ push 成功，digest `sha256:0552c7f5a3b197d45a23824ce22a607f53b4ccb5b4457b9c0d8d4cb42cb89ee9`（镜像内容不变，只换地址）。

### Step 2 — 本地验证镜像可用性 ✅
- 历史容器记录：无（首次跑）。
- 本地运行验证（`--platform linux/amd64`，模拟 AI Core 环境）：
  ```sh
  docker run --rm -d --platform linux/amd64 -p 8080:8080 --name ollama-test \
    entlms.common.repositories.cloud.sap/ems/ollama:ai-core
  docker exec ollama-test ps aux | grep -E "nginx|ollama"   # 两个进程都在 ✅
  curl -s http://localhost:8080/v1/api/tags                  # {"models":[]} ✅
  docker stop ollama-test
  ```
- 结论：镜像本身无问题，nginx+ollama 启动正常，端点响应正常。

### Step 3 — 改 serving 模板 ollama-template.yaml ✅
- 改动记录（两轮）：
  - 第一轮：`modelName` → `exaone-deep:2.4b`；`imagePullSecrets.name` → `docker-secret`；`image` → `sbda.int.repositories.cloud.sap/ems/ollama:ai-core`
  - 第二轮（registry 迁移后）：`image` → `entlms.common.repositories.cloud.sap/ems/ollama:ai-core`
- 两轮均已 commit + push 到 GitHub fork。
- **坑⑤（digest 引用不兼容）**：曾尝试用 `image: ..@sha256:<digest>` 钉死镜像 → AI Core 报 `Runtime Adapter Exception: Configuration invalid`。结论：AI Core runtime adapter 不接受 digest 格式镜像引用，必须用 tag 格式。

### Step 4 — 准备 config.json ✅
- 文件被 `.gitignore` 忽略，含机密，勿提交。
- 经过两轮更新：初始填 sbda registry 凭证，迁移后更新为 entlms registry 凭证。
- 关键非机密字段：`name=byom-llm-exaone`、`resource_group=oss-llm`、`modelName=exaone-deep:2.4b`。

### Step 5 — 00-init-config ✅
- 脚本：`byom-oss-llm-code/run_init_config.py`
- **坑④（撞名）**：`name=byom-open-source-llms` 在共享租户已被占用 → 改 `name=byom-llm-exaone` 解决。
- 结果：token ✅；resource group `oss-llm` ✅；docker-secret ✅；仓库 onboard ✅；application `byom-llm-exaone` ✅；sync=Synced/health=Healthy ✅；6 个 configuration 全部创建 ✅。

### Step 6 — 创建 deployment → RUNNING ✅
- **坑⑥（registry 不可达）**：前两个 deployment（`d973f4cbbda147d0`、`d6436cceff7a75bf`）均长时间 PENDING，无日志无事件。根因：`sbda.int.repositories.cloud.sap` AI Core runtime 无法访问。
- **解法**：迁移到 `entlms.common.repositories.cloud.sap` 后，同步重建 docker-secret + resync + 新 deployment。
  - 脚本：`byom-oss-llm-code/recreate_docker_secret.py`（重建 secret）、`byom-oss-llm-code/resync_and_new_deployment.py`（resync + 新 deployment）
- **当前 deployment**：`d241483ed1f30659`，configuration `a406553d-a87a-473e-a100-b3dea96a6621`，status=**RUNNING** ✅
- deployment_url：`https://api.ai.prod.eu-central-1.aws.ml.hana.ondemand.com/v2/inference/deployments/d241483ed1f30659`

### Step 7a — 获取 deployment URL ✅
- 用户提供：`https://api.ai.prod.eu-central-1.aws.ml.hana.ondemand.com/v2/inference/deployments/d241483ed1f30659`
- 已写入 `ollama/env.json`。

### Step 7b — 拉取模型到容器 ✅
- 脚本：`byom-oss-llm-code/pull_model.py`
- 调用：`POST {deployment_url}/v1/api/pull`，body `{"name": "exaone-deep:2.4b"}`，需 Bearer token + `AI-Resource-Group: oss-llm` header。
- token 获取：OAuth client credentials flow（`POST {sk.url}/oauth/token`）。
- 结果：
  ```
  pulling manifest
  pulling 1eefef7fedff: 100%  (1644918944 bytes，主模型权重)
  pulling 37cddd3bd818: 100%  (tokenizer)
  pulling 294fd63925d8: 100%  (config)
  pulling db5a752e264f: 100%  (license)
  pulling d43429850c63: 100%  (template)
  verifying sha256 digest ✅
  writing manifest ✅
  success ✅
  ```
- `exaone-deep:2.4b` 已下载并写入容器，可推理。

---

## 坑汇总

| # | 坑 | 根因 | 解法 |
|---|---|---|---|
| ① | Dockerfile build 失败：`requires zstd` | Ollama 新版安装脚本改用 zstd，教程未更新 | apt 加装 `zstd` |
| ② | Build 慢 | Ollama 二进制从 ollama.com 下载，国内镜像加速无效 | 等待；或改用 `FROM ollama/ollama` 基础镜像 |
| ③ | Docker Hub push 失败 | 公司代理 squid:3128 对 Docker Hub push 连接不稳 | 改推内网 registry |
| ④ | AI Core onboard 409 撞名 | `byom-open-source-llms` 在共享租户已被占用 | 改 `name=byom-llm-exaone` |
| ⑤ | digest 镜像引用报错 | AI Core runtime adapter 不接受 `image@sha256:` 格式 | 回退为 tag 引用 |
| ⑥ | PENDING 无法 RUNNING | `sbda.int.repositories.cloud.sap` AI Core runtime 无法访问 | 迁移到 `entlms.common.repositories.cloud.sap` |

---

## 下一步 / 续作提示
- **当前状态**：deployment RUNNING，模型 `exaone-deep:2.4b` 已拉取到容器。
- **下一步**：Step 7c（直接 API 推理）→ Step 7d（GenAI Hub SDK 推理）。
- Step 8（Open WebUI）PoC 阶段跳过。
