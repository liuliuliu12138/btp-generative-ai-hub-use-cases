"""
pull_model.py — 向运行中的 deployment 拉取 exaone-deep:2.4b 模型。
从 byom-oss-llm-code 目录运行。
"""
import json, requests

cfg = json.load(open("config.json"))
sk = cfg["ai_core_service_key"]
rg = cfg["resource_group"]

# 获取 OAuth token（client credentials flow）
token_resp = requests.post(
    sk["url"] + "/oauth/token",
    params={"grant_type": "client_credentials"},
    auth=(sk["clientid"], sk["clientsecret"]),
    timeout=30,
)
token_resp.raise_for_status()
token = token_resp.json()["access_token"]
print(f"token 获取成功（长度 {len(token)}）", flush=True)

deployment_url = json.load(open("ollama/env.json")).get(
    "deployment_url",
    "https://api.ai.prod.eu-central-1.aws.ml.hana.ondemand.com/v2/inference/deployments/d241483ed1f30659"
)
model_name = "exaone-deep:2.4b"

pull_url = f"{deployment_url}/v1/api/pull"
headers = {
    "Authorization": f"Bearer {token}",
    "AI-Resource-Group": rg,
    "Content-Type": "application/json",
}

print(f"拉取模型: {model_name}", flush=True)
print(f"URL: {pull_url}", flush=True)
print("（下载约 1.6 GB，耐心等待…）\n", flush=True)

resp = requests.post(pull_url, headers=headers, json={"name": model_name}, stream=True, timeout=1800)
resp.raise_for_status()

for line in resp.iter_lines():
    if line:
        try:
            obj = json.loads(line)
            status = obj.get("status", "")
            completed = obj.get("completed", "")
            total = obj.get("total", "")
            if total:
                pct = int(completed) * 100 // int(total) if int(total) > 0 else 0
                print(f"  {status}: {pct}% ({completed}/{total})", flush=True)
            else:
                print(f"  {status}", flush=True)
            if status == "success":
                print("\n✅ 模型拉取完成！", flush=True)
                break
        except Exception:
            print(f"  {line}", flush=True)
