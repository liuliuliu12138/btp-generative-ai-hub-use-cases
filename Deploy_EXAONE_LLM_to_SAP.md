# Deploy EXAONE LLM to SAP AI Core — 操作追溯记录

> 目标：按教程 [Bring Open-Source LLMs into SAP AI Core with Ollama](https://community.sap.com/t5/artificial-intelligence-blogs-posts/bring-open-source-llms-into-sap-ai-core-with-ollama/ba-p/13659769) 把 **EXAONE Deep 最小模型** 部署到 SAP AI Core（PoC）。
> 方案：Ollama 推理服务器（镜像与模型解耦，模型运行时动态拉取）。
> 记录开始：2026-10-14

---

## 关键参数（可复用）

| 项 | 值 |
|---|---|
| 目标模型 | `exaone-deep:2.4b`（Ollama 库，1.6GB，Q4_K_M，32K ctx）—— EXAONE Deep 最小 |
| **Docker 镜像（部署用）** | **`sbda.int.repositories.cloud.sap/ems/ollama:ai-core`**（内网 SAP registry，digest `sha256:0552c7f5a3b1…`） |
| registry | `sbda.int.repositories.cloud.sap`，namespace `ems`（Docker Hub 被公司网络代理挡，改用此内网 registry） |
| ~~Docker Hub user~~ | ~~`maggieliu714005548`~~（弃用，公司网络 push 不通） |
| GitHub fork | `https://github.com/liuliuliu12138/btp-generative-ai-hub-use-cases.git`（本地 clone 的 origin） |
| 本地仓库根 | `/Users/I326998/git/btp-generative-ai-hub-use-cases` |
| 教程工作目录 | `10-byom-oss-llm-ai-core/` |
| Dockerfile | `10-byom-oss-llm-ai-core/byom-oss-llm-code/ollama/Dockerfile` |
| serving 模板 | `10-byom-oss-llm-ai-core/byom-oss-llm-templates/ollama-template.yaml` |
| config 模板 | `10-byom-oss-llm-ai-core/byom-oss-llm-code/config.template.json` |
| resource plan | `infer.s`（带 GPU，2.4B 够用） |
| resource_group | `oss-llm`（待建，可按 config 调整） |

---

## 前置条件核对

| 项 | 状态 | 备注 |
|---|---|---|
| ① SAP AI Core（Standard/Extended）+ service key | ✅ 用户已有 | 到 Step 4 写进 config.json |
| ② Docker Hub 账号 + access token | ✅ 账号 `maggieliu714005548`，token 用户自留 | login 由用户在本地终端执行 |
| ③ GitHub 可写 fork | ✅ `liuliuliu12138/...` | 模板改完需 push 到此 fork |
| ④ 执行方式 | ✅ 由 Claude 用终端命令/脚本代跑 | notebook cell → CLI/python |
| 本地 Docker | ✅ 已安装 | daemon 待确认 |

---

## 步骤总表

| 步骤 | 内容 | EXAONE 改动 | 状态 |
|---|---|---|---|
| 0 | 前置条件核对 | — | ✅ 完成 |
| 1 | 准备 Dockerfile | 无需改（镜像与模型无关） | ✅ 完成 |
| 2 | 构建并推送 Docker 镜像 | 推到内网 SAP registry（Docker Hub 被挡） | ✅ 完成 |
| 3 | 改 ollama-template.yaml | modelName→exaone-deep:2.4b；image→内网 registry；secret 名→docker-secret | ✅ 完成（文件已改，待 push GitHub） |
| 4 | 准备 config.json | 保留全部 configurations，仅 ollama 项改 EXAONE | ✅ 完成（机密已填、JSON 合法） |
| 5 | 00-init-config：onboard repo+建 app+同步 scenario+建 configuration | — | ⬜ 未开始 |
| 6 | 01-deployment：创建 deployment 等 RUNNING | — | ⬜ 未开始 |
| 7 | 拉取 exaone-deep:2.4b 并推理 | 模型名用 EXAONE | ⬜ 未开始 |
| 8（可选） | 接 Open WebUI | PoC 跳过 | ⬜ 未开始 |

---

## 步骤日志

### Step 0 — 前置条件核对 ✅
- 结果：AI Core service key 在手；Docker Hub 账号已建（`maggieliu714005548`）；GitHub fork 已就位；执行方式=Claude 代跑。

### Step 1 — 准备 Dockerfile ✅
- 做了什么：确认 `ollama/Dockerfile` 就位。其做三件适配：装 Ollama+nginx；nginx 把 `/api/*` 反代为 `/v1/api/*`（AI Core 要求端点带 /v1 前缀），`/v1/chat/*` 原样；为 nobody 用户建 `/nonexistent/.ollama`，EXPOSE 8080，CMD 同时起 nginx + `ollama serve`。
- EXAONE 改动：**无**。镜像与模型解耦，模型运行时拉取。
- 结果：文件存在且与教程一致，无需改动。验收通过。

### Step 2 — 构建并推送 Docker 镜像 ⏳
- 计划命令（显式指定 Dockerfile 路径与 context）：
  ```sh
  docker build --platform=linux/amd64 \
    -f /Users/I326998/git/btp-generative-ai-hub-use-cases/10-byom-oss-llm-ai-core/byom-oss-llm-code/ollama/Dockerfile \
    -t docker.io/maggieliu714005548/ollama:ai-core \
    /Users/I326998/git/btp-generative-ai-hub-use-cases/10-byom-oss-llm-ai-core/byom-oss-llm-code/ollama
  docker push docker.io/maggieliu714005548/ollama:ai-core
  ```
- token 处理：`docker login -u maggieliu714005548` 由用户本地终端执行，凭证缓存，token 不进 Claude 工具调用。
- 验收标准：build 末尾 `naming to docker.io/maggieliu714005548/ollama:ai-core ... DONE`；push 给出 `ai-core: digest: sha256:...`；Docker Hub tags 页可见 `ai-core`。
- 环境：Docker Desktop 需手动 `open -a Docker` 启动；本机架构 aarch64(Apple Silicon)，故必须 `--platform=linux/amd64` 交叉构建。
- **坑①（已修复）**：首次 build 在第 3 步 `curl ollama/install.sh | sh` 失败，报 `This version requires zstd for extraction`。Ollama 新版安装脚本改用 zstd 压缩，教程 Dockerfile 未装 zstd。
  - 修复：Dockerfile apt 安装列表加 `zstd`（已改，用户确认）。此为环境版本漂移适配，与 EXAONE 无关。
- **坑②（下载慢，根因澄清）**：build 第 3 步下载的是 **Ollama 二进制 `ollama-linux-amd64.tar.zst`，来自 ollama.com CDN（curl 下载），不是 Docker 镜像**。本机已配 Docker 国内镜像(daocloud/azk8s/163)，但那只加速 `docker pull` 基础镜像，对 ollama.com 的 curl 下载无效，故慢。
  - 本地已装的 ollama 是 macOS/arm64，**无法复用**到 linux/amd64 镜像。
  - 备选**方案 B（下次从头做可直接用，更快）**：Dockerfile 改为 `FROM ollama/ollama:latest`（走国内镜像快）+ 装 nginx + `ENTRYPOINT []` + `CMD service nginx start && /bin/ollama serve`，绕开 ollama.com。本次因 build 已过 65%，选择等待，未切 B。
- 结果：_（待填——等待 build 跑完）_

### Step 2 关键转折 — push 目标从 Docker Hub 改为内网 SAP registry ✅
- **坑③（push 失败，根因=公司网络代理）**：原计划推 Docker Hub（`registry-1.docker.io`），但公司网络的 HTTP 代理（squid:3128）对 Docker Hub push 连接不稳/间歇性掐断，表现为 `use of closed network connection` 和对 blob 的 HEAD 请求 `EOF`（连空 blob 都失败，证明不是层大小问题，是代理到 Docker Hub 的链路问题）。
  - 期间副作用：手动 quit/relaunch Docker 一度把 Docker Desktop VM 后端弄挂（`dialing 192.168.65.7:2376 no route to host` → 所有 docker API 500），后台重启任务最终自愈，镜像未丢（存于 VM 持久磁盘）。
  - 无效尝试：`max-concurrent-uploads:1`、多次重试、关代理（关代理后反而连不上 Docker Hub，证明该网络下 push Docker Hub 必须经代理，而代理又不稳）。
- **解法**：用户改用公司内网镜像仓库 `sbda.int.repositories.cloud.sap`，`docker login` 后：
  ```sh
  docker tag docker.io/maggieliu714005548/ollama:ai-core sbda.int.repositories.cloud.sap/ems/ollama:ai-core
  docker push sbda.int.repositories.cloud.sap/ems/ollama:ai-core
  ```
  一次成功。命名规则：`<registry>/<namespace=ems>/<repository=ollama>:<tag=ai-core>`。
- **结果**：✅ push 成功，镜像 `sbda.int.repositories.cloud.sap/ems/ollama:ai-core`，digest `sha256:0552c7f5a3b197d45a23824ce22a607f53b4ccb5b4457b9c0d8d4cb42cb89ee9`。
- **对后续步骤的影响**：Step 3 serving 模板的 `image:` 要改成内网 registry 地址；docker secret 要指向 `sbda.int.repositories.cloud.sap`（含对应凭证），而非 Docker Hub。

### Step 3 — 改 serving 模板 ollama-template.yaml ✅
- 文件：`10-byom-oss-llm-ai-core/byom-oss-llm-templates/ollama-template.yaml`
- 三处改动（已完成，无遗留占位符）：
  - `modelName` 默认 `"phi3:14b"` → `"exaone-deep:2.4b"`（EXAONE Deep 最小模型）
  - `imagePullSecrets.name` `<YOUR_DOCKER_SECRET>` → `docker-secret`
  - `image` `docker.io/<YOUR_DOCKER_USER>/ollama:ai-core` → `sbda.int.repositories.cloud.sap/ems/ollama:ai-core`
  - `resourcePlan` 保持 `infer.s`（带 GPU，2.4B 够用）
- 概念澄清（docker secret）：name 只是引用；值 = `.dockerconfigjson`（registry 主机 + username + token），Step 5 跑 00-init-config 时从 config.json 读入并**存进 AI Core**，部署时按名在 AI Core 内部查值，不再读本地 config.json。
- 待办：改好的模板需 push 到 GitHub fork（放在 Step 5 之前），且需确认公司网络能 push github.com。
- **结果**：✅ 文件已改并校验，YAML 合法、无 `<YOUR_*>`/`phi3` 残留。

### Step 4 — 准备 config.json ⏳（待用户填机密）
- 文件：`10-byom-oss-llm-ai-core/byom-oss-llm-code/config.json`（由 config.template.json 复制生成）
- 安全：已确认被 `.gitignore` 忽略（`10-byom-oss-llm-ai-core/.gitignore` 第 3 行 `byom-oss-llm-code/config.json`）。**含机密，勿提交。**
- 已填非机密：`name=byom-open-source-llms`、`resource_group=oss-llm`、docker_secret auths host=`sbda.int.repositories.cloud.sap`、`git_repo.repo_url`=fork、`git_repo.user=liuliuliu12138`、`path_in_repo` 不变；ollama 配置 `name=ollama-exaone-deep-2-4b`、`modelName=exaone-deep:2.4b`。保留全部 6 个 configurations（用户要求，备以后用）。
- JSON 校验：✅ 合法。
- **待用户填 3 组机密**：① `ai_core_service_key`（clientid/clientsecret/url/identityzone/identityzoneid/appname/AI_API_URL）；② docker_secret 的 `username`+`password`（sbda 内网 registry 拉取凭证）；③ `git_repo.access_token`（GitHub PAT）。
- 结果：_（待用户填完机密后，Step 5 运行 00-init-config 验证）_

---

## 下一步 / 续作提示
- 下次续作：从「步骤总表」里第一个非 ✅ 的步骤继续。
- 需要用户提供/操作的：Step 2 的 `docker login`；Step 4 的 AI Core service key、Docker token、GitHub PAT 填入 `config.json`（该文件含机密，勿提交）。
