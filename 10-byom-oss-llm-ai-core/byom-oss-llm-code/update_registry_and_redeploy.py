"""
update_registry_and_redeploy.py
重建 docker-secret（新 registry）→ resync → 新 deployment。
从 byom-oss-llm-code 目录运行。
"""
import json, time, base64
from ai_core_sdk.ai_core_v2_client import AICoreV2Client
from ai_core_sdk.models import ParameterBinding

cfg = json.load(open("config.json"))
sk = cfg["ai_core_service_key"]
rg = cfg["resource_group"]
name = cfg["name"]

client = AICoreV2Client(
    base_url=sk["serviceurls"]["AI_API_URL"] + "/v2",
    auth_url=sk["url"] + "/oauth/token",
    client_id=sk["clientid"], client_secret=sk["clientsecret"],
    resource_group=rg,
)

# ── 1. 重建 docker-secret ──────────────────────────────────────────────────
print("======== 1. 重建 docker-secret ========", flush=True)
docker_cfg = cfg["docker_secret"]
secret_name = docker_cfg["name"]
docker_config_json = docker_cfg["data"][".dockerconfigjson"]

try:
    client.docker_registry_secrets.delete(secret_name)
    print(f"  旧 secret '{secret_name}' 已删除", flush=True)
    time.sleep(2)
except Exception as e:
    print(f"  删除旧 secret 失败（可能不存在）: {e}", flush=True)

resp = client.docker_registry_secrets.create(
    name=secret_name,
    data={".dockerconfigjson": docker_config_json},
)
print(f"  ✅ 新 docker-secret 创建: name={secret_name}", flush=True)

# ── 2. Resync（拉取新模板）────────────────────────────────────────────────
print("======== 2. Resync ========", flush=True)
before = client.applications.get_status(name).sync_finished_at
client.applications.refresh(name)
for i in range(1, 16):
    st = client.applications.get_status(name)
    print(f"  [{i}] sync={st.sync_status} finished_at={st.sync_finished_at}", flush=True)
    if st.sync_status == "Synced" and st.sync_finished_at != before:
        break
    client.applications.refresh(name)
    time.sleep(15)
print("  ✅ resync 完成", flush=True)

# ── 3. 重建 ollama configuration ──────────────────────────────────────────
print("======== 3. 重建 ollama configuration ========", flush=True)
oconf = next(c for c in cfg["configurations"] if c["scenario_id"] == "ollama")
pbs = [ParameterBinding(key=p["key"], value=p["value"]) for p in oconf["parameters"]]
conf = client.configuration.create(
    name=oconf["name"], scenario_id="ollama", executable_id="ollama",
    parameter_bindings=pbs, input_artifact_bindings=[],
)
cid = conf.id
print(f"  ✅ configuration id={cid}", flush=True)

# ── 4. 创建 deployment ────────────────────────────────────────────────────
print("======== 4. 创建 deployment ========", flush=True)
resp = client.deployment.create(configuration_id=cid, resource_group=rg)
did = resp.id
print(f"  ✅ deployment id={did} status={resp.status}", flush=True)

env = json.load(open("ollama/env.json"))
env["configuration_id"] = cid
env["deployment_id"] = did
with open("ollama/env.json", "w") as f:
    json.dump(env, f, indent=4)
print(f"  ollama/env.json updated: configuration_id={cid} deployment_id={did}", flush=True)
print("\n完成。去 AI Launchpad → oss-llm 组查看新 deployment 状态。", flush=True)
