"""
recreate_config_and_deploy.py — resync 后旧 configuration 失效，重建 ollama configuration 并部署。
从 byom-oss-llm-code 目录运行。
"""
import json
from ai_core_sdk.ai_core_v2_client import AICoreV2Client
from ai_core_sdk.models import ParameterBinding

cfg = json.load(open("config.json"))
sk = cfg["ai_core_service_key"]
rg = cfg["resource_group"]
client = AICoreV2Client(
    base_url=sk["serviceurls"]["AI_API_URL"] + "/v2",
    auth_url=sk["url"] + "/oauth/token",
    client_id=sk["clientid"], client_secret=sk["clientsecret"], resource_group=rg,
)

# 取 config.json 里 ollama 的 configuration 定义
oconf = next(c for c in cfg["configurations"] if c["scenario_id"] == "ollama")
print("======== 1. 重建 ollama configuration ========", flush=True)
pbs = [ParameterBinding(key=p["key"], value=p["value"]) for p in oconf["parameters"]]
conf = client.configuration.create(
    name=oconf["name"], scenario_id="ollama", executable_id="ollama",
    parameter_bindings=pbs, input_artifact_bindings=[],
)
cid = conf.id
print(f"  ✅ 新 configuration: id={cid} (params={[(p['key'],p['value']) for p in oconf['parameters']]})", flush=True)

env = json.load(open("ollama/env.json"))
env["configuration_id"] = cid
with open("ollama/env.json", "w") as f:
    json.dump(env, f, indent=4)
print(f"  ollama/env.json updated: configuration_id={cid}", flush=True)

print("======== 2. 创建 deployment ========", flush=True)
resp = client.deployment.create(configuration_id=cid, resource_group=rg)
did = resp.id
print(f"  ✅ 新 deployment: id={did} status={resp.status}", flush=True)
env["deployment_id"] = did
with open("ollama/env.json", "w") as f:
    json.dump(env, f, indent=4)
print(f"  ollama/env.json updated: deployment_id={did}", flush=True)
