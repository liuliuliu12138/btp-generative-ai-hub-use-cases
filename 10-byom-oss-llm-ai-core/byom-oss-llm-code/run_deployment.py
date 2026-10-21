"""
run_deployment.py — 复刻 ollama/01-deployment.ipynb 的「创建 deployment + 轮询状态」部分。
由 Claude 代跑 Step 6。从 byom-oss-llm-code 目录运行。
创建后立即把 deployment_id 写回 ollama/env.json（即使后续轮询被中断也不丢）。
"""
import json, os, time, datetime
import requests
from ai_core_sdk.ai_core_v2_client import AICoreV2Client

CFG = "config.json"
ENV = "ollama/env.json"


def now_utc():
    return datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def update_env(key, value):
    with open(ENV) as f:
        d = json.load(f)
    d[key] = value
    with open(ENV, "w") as f:
        json.dump(d, f, indent=4)
    print(f"  {ENV} updated: {key}={value}", flush=True)


cfg = json.load(open(CFG))
sk = cfg["ai_core_service_key"]
rg = cfg.get("resource_group", "default")
base_url = sk["serviceurls"]["AI_API_URL"] + "/v2/lm"
client = AICoreV2Client(
    base_url=sk["serviceurls"]["AI_API_URL"] + "/v2",
    auth_url=sk["url"] + "/oauth/token",
    client_id=sk["clientid"], client_secret=sk["clientsecret"], resource_group=rg,
)
token = client.rest_client.get_token()
headers = {"Authorization": token, "ai-resource-group": rg, "Content-Type": "application/json"}

configuration_id = json.load(open(ENV))["configuration_id"]
print(f"======== 创建 deployment (configuration_id={configuration_id}) ========", flush=True)
resp = client.deployment.create(configuration_id=configuration_id, resource_group=rg)
deployment_id = resp.id
print(f"  ✅ deployment 创建: id={deployment_id} status={resp.status} msg={getattr(resp,'message','')}", flush=True)
update_env("deployment_id", deployment_id)

print("======== 轮询状态 + 日志，直到 RUNNING / DEAD ========", flush=True)
deployment_url = f"{base_url}/deployments/{deployment_id}"
last_check = now_utc()
status = "UNKNOWN"
max_iter, interval = 48, 25  # ~20 分钟
t0 = time.time()
for i in range(1, max_iter + 1):
    cur = now_utc()
    try:
        r = requests.get(url=deployment_url, headers=headers)
        resp_j = r.json()
        status = resp_j.get("status", "UNKNOWN")
        durl = resp_j.get("deployment_url", "")
    except Exception as e:
        status = f"ERR({e})"
        durl = ""
    mins = round((time.time() - t0) / 60, 1)
    print(f"  [{i}/{max_iter}] {cur} status={status} url={durl} ({mins}min)", flush=True)
    # 拉日志（可能为空）
    try:
        rl = requests.get(url=f"{deployment_url}/logs?start={last_check}", headers=headers)
        txt = rl.text
        if txt and len(txt) > 2 and '"data":[]' not in txt:
            print(f"    logs: {txt[:1200]}", flush=True)
    except Exception as e:
        print(f"    (日志获取异常: {e})", flush=True)
    last_check = cur
    if status in ("RUNNING", "DEAD"):
        break
    time.sleep(interval)

print("======== 结果 ========", flush=True)
if status == "RUNNING":
    print(f"  ✅ Deployment RUNNING! deployment_id={deployment_id}", flush=True)
    print(f"  deployment_url={durl}", flush=True)
else:
    print(f"  ⚠️ 结束时状态={status}（未到 RUNNING）。deployment_id={deployment_id}，可继续轮询或查日志。", flush=True)
