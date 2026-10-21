"""
recreate_docker_secret.py — 删除旧 docker-secret，用 config.json 里的新 registry 凭证重建。
从 byom-oss-llm-code 目录运行。
"""
import json, time
from ai_core_sdk.ai_core_v2_client import AICoreV2Client

cfg = json.load(open("config.json"))
sk = cfg["ai_core_service_key"]
rg = cfg["resource_group"]

client = AICoreV2Client(
    base_url=sk["serviceurls"]["AI_API_URL"] + "/v2",
    auth_url=sk["url"] + "/oauth/token",
    client_id=sk["clientid"], client_secret=sk["clientsecret"],
    resource_group=rg,
)

docker_cfg = cfg["docker_secret"]
secret_name = docker_cfg["name"]
docker_config_json = docker_cfg["data"][".dockerconfigjson"]

print(f"======== 删除旧 docker-secret: {secret_name} ========", flush=True)
try:
    client.docker_registry_secrets.delete(secret_name)
    print(f"  ✅ 已删除", flush=True)
    time.sleep(2)
except Exception as e:
    print(f"  跳过删除（可能不存在）: {e}", flush=True)

print(f"======== 重建 docker-secret: {secret_name} ========", flush=True)
client.docker_registry_secrets.create(
    name=secret_name,
    data={".dockerconfigjson": docker_config_json},
)
print(f"  ✅ 新 docker-secret 创建成功: name={secret_name}", flush=True)

print("\n验收：去 AI Launchpad → Docker Registry Secrets 确认 docker-secret 存在。", flush=True)
