"""
run_init_config.py — 复刻 00-init-config.ipynb 的初始化逻辑（EXAONE/内网 registry 适配版）
由 Claude 代跑 Step 5c。读取 config.json，分步执行并打印清晰日志，带"已存在"兜底。
运行：从 byom-oss-llm-code 目录下用 venv 的 python 执行。
"""
import json, os, sys, time

CFG = "config.json"


def banner(msg):
    print(f"\n{'='*8} {msg} {'='*8}", flush=True)


def update_json_file(file_path, key, value):
    # 若文件/目录不存在则创建（原 notebook 不处理，这里加固）
    d = os.path.dirname(file_path)
    if d and not os.path.isdir(d):
        os.makedirs(d, exist_ok=True)
    data = {}
    if os.path.isfile(file_path):
        try:
            with open(file_path) as f:
                data = json.load(f)
        except Exception:
            data = {}
    data[key] = value
    with open(file_path, "w") as f:
        json.dump(data, f, indent=4)
    print(f"  {file_path} updated: {key}={value}", flush=True)


def main():
    banner("1. 读取 config.json + 初始化 client + 拿 token")
    with open(CFG) as f:
        config = json.load(f)
    resource_group = config.get("resource_group", "default")
    name = config.get("name", "open-source-llms")
    print(f"  name={name}  resource_group={resource_group}", flush=True)

    from ai_core_sdk.ai_core_v2_client import AICoreV2Client
    from ai_core_sdk.models import ParameterBinding

    sk = config["ai_core_service_key"]
    client = AICoreV2Client(
        base_url=sk["serviceurls"]["AI_API_URL"] + "/v2",
        auth_url=sk["url"] + "/oauth/token",
        client_id=sk["clientid"],
        client_secret=sk["clientsecret"],
        resource_group=resource_group,
    )
    token = client.rest_client.get_token()
    print(f"  ✅ token 获取成功（长度 {len(token)}），service key 有效", flush=True)

    banner("2. 创建 resource group")
    try:
        resp = client.resource_groups.create(resource_group_id=resource_group)
        print(f"  ✅ 已创建: {resp.__dict__}", flush=True)
    except Exception as e:
        print(f"  ⚠️ 创建失败/可能已存在，继续: {type(e).__name__}: {e}", flush=True)

    banner("3. 注册 docker secret")
    ds = config["docker_secret"]
    try:
        resp = client.docker_registry_secrets.create(name=ds["name"], data=ds["data"])
        print(f"  ✅ docker secret '{ds['name']}' 已创建: {resp.__dict__}", flush=True)
    except Exception as e:
        print(f"  ⚠️ 创建失败/可能已存在，继续: {type(e).__name__}: {e}", flush=True)

    banner("4. onboard GitHub 仓库 + 创建 application")
    repo = config["git_repo"]
    try:
        r = client.repositories.create(name, url=repo["repo_url"], username=repo["user"], password=repo["access_token"])
        print(f"  ✅ 仓库 onboard: {r}", flush=True)
    except Exception as e:
        print(f"  ⚠️ 仓库 onboard 失败/可能已存在，继续: {type(e).__name__}: {e}", flush=True)
    app = config["application"]
    try:
        a = client.applications.create(
            revision=app.get("revision", "HEAD"),
            path=app.get("path_in_repo"),
            application_name=name,
            repository_name=name,
        )
        print(f"  ✅ application 创建: {a}", flush=True)
    except Exception as e:
        print(f"  ⚠️ application 创建失败/可能已存在，继续: {type(e).__name__}: {e}", flush=True)

    banner("5. 触发 sync 并等待 Synced，确认 scenario")
    max_tries, interval = 12, 20
    synced = False
    for i in range(1, max_tries + 1):
        st = client.applications.get_status(name)
        print(f"  [{i}/{max_tries}] health={st.health_status} sync={st.sync_status} finished_at={st.sync_finished_at}", flush=True)
        if st.sync_status == "Synced":
            synced = True
            break
        try:
            client.applications.refresh(name)
        except Exception as e:
            print(f"    refresh 异常: {e}", flush=True)
        time.sleep(interval)
    if not synced:
        print("  ❌ 多次重试仍未 Synced，停止。请检查 AI Core 能否访问该 GitHub fork / PAT 权限 / 模板路径。", flush=True)
        sys.exit(2)
    scenarios = client.scenario.query()
    names = [s.name for s in scenarios.resources]
    print(f"  已同步 scenarios: {names}", flush=True)
    print(f"  ollama scenario 是否存在: {'✅ 是' if 'ollama' in names else '❌ 否'}", flush=True)

    banner("6. 创建 configurations（全部），写回各 env.json")
    for conf in config["configurations"]:
        sid, eid, cname = conf["scenario_id"], conf["executable_id"], conf["name"]
        try:
            pbs = [ParameterBinding(key=p["key"], value=p["value"]) for p in conf["parameters"]]
            cfg = client.configuration.create(
                name=cname, scenario_id=sid, executable_id=eid,
                parameter_bindings=pbs, input_artifact_bindings=[],
            )
            print(f"  ✅ [{sid}] configuration '{cname}' 创建: id={cfg.id}", flush=True)
            update_json_file(f"{eid}/env.json", "configuration_id", cfg.id)
        except Exception as e:
            print(f"  ⚠️ [{sid}] configuration '{cname}' 创建失败: {type(e).__name__}: {e}", flush=True)

    banner("完成")
    print("  后续：Step 6 用 ollama/env.json 里的 configuration_id 创建 deployment。", flush=True)


if __name__ == "__main__":
    main()
