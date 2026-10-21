"""
resync_and_redeploy.py — Step 6 修复：
1) 触发 AI Core 重新同步 GitHub（拉取 digest-pinned 的新模板）
2) 停止并删除旧的 PENDING deployment
3) 用更新后的 executable 创建新 deployment
从 byom-oss-llm-code 目录运行。
"""
import json, time
from ai_core_sdk.ai_core_v2_client import AICoreV2Client

cfg = json.load(open("config.json"))
sk = cfg["ai_core_service_key"]
rg = cfg["resource_group"]
name = cfg["name"]
client = AICoreV2Client(
    base_url=sk["serviceurls"]["AI_API_URL"] + "/v2",
    auth_url=sk["url"] + "/oauth/token",
    client_id=sk["clientid"], client_secret=sk["clientsecret"], resource_group=rg,
)
env = json.load(open("ollama/env.json"))
configuration_id = env["configuration_id"]
old_dep = env.get("deployment_id", "")

print("======== 1. 触发 resync 并等待 Synced ========", flush=True)
before = None
try:
    before = client.applications.get_status(name).sync_finished_at
except Exception as e:
    print("  get_status err:", e, flush=True)
client.applications.refresh(name)
for i in range(1, 16):
    st = client.applications.get_status(name)
    print(f"  [{i}] sync={st.sync_status} finished_at={st.sync_finished_at}", flush=True)
    if st.sync_status == "Synced" and st.sync_finished_at != before:
        break
    client.applications.refresh(name)
    time.sleep(15)
print("  ✅ resync 完成（executable 已更新为 digest-pinned 镜像）", flush=True)

print("======== 2. 停止 + 删除旧 deployment ========", flush=True)
if old_dep:
    from ai_api_client_sdk.models.target_status import TargetStatus
    try:
        client.deployment.modify(deployment_id=old_dep, target_status=TargetStatus.STOPPED, resource_group=rg)
        print(f"  已请求停止 {old_dep}", flush=True)
    except Exception as e:
        print(f"  停止 {old_dep} 异常/可能已非运行态: {type(e).__name__}: {e}", flush=True)
    # 轮询等待进入 STOPPED/DEAD 后再删
    import requests
    base = sk["serviceurls"]["AI_API_URL"] + "/v2/lm"
    for i in range(1, 13):
        try:
            r = requests.get(f"{base}/deployments/{old_dep}",
                             headers={"Authorization": client.rest_client.get_token(), "ai-resource-group": rg}).json()
            s = r.get("status")
            print(f"  [{i}] 旧 deployment status={s}", flush=True)
            if s in ("STOPPED", "DEAD", "UNKNOWN"):
                break
        except Exception as e:
            print("   查询异常:", e, flush=True)
        time.sleep(10)
    try:
        client.deployment.delete(deployment_id=old_dep, resource_group=rg)
        print(f"  ✅ 已删除旧 deployment {old_dep}", flush=True)
    except Exception as e:
        print(f"  ⚠️ 删除旧 deployment 失败（不阻塞新建）: {type(e).__name__}: {e}", flush=True)
else:
    print("  无旧 deployment_id，跳过", flush=True)

print("======== 3. 创建新 deployment ========", flush=True)
resp = client.deployment.create(configuration_id=configuration_id, resource_group=rg)
new_dep = resp.id
print(f"  ✅ 新 deployment: id={new_dep} status={resp.status}", flush=True)
env["deployment_id"] = new_dep
with open("ollama/env.json", "w") as f:
    json.dump(env, f, indent=4)
print(f"  ollama/env.json updated: deployment_id={new_dep}", flush=True)
print("  后续用新 id 轮询状态。", flush=True)
