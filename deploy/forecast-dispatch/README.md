# 单容器双预测与单时段优化部署（2026-09-29）

当前 Compose 只包含一个 `dispatch` 服务。最终只运行一个容器，内部由进程管理程序启动单点预测、24小时预测、优化API。构建阶段使用两份原预测镜像取出程序、模型和依赖；这些构建阶段不是运行时容器。

## 接口与端口

| 功能 | 对外默认端口 | 容器内地址 | 原路径 |
|---|---:|---|---|
| 平台优化 | 18768 | 0.0.0.0:8000 | POST /api/v1/fluxcast/compute |
| 24小时预测 | 不公开 | 127.0.0.1:8002 | 在原compute响应中按自然日每日追加一批96点 |
| 单点预测 | 不公开 | 127.0.0.1:8001 | 优化服务在容器内调用 |

优化请求仍为point_table、96帧历史frames、renewable_data；末帧当前，优化下一15分钟。一个compute请求返回优化结果及r7界面直接显示值、累计值和已计算曲线，字段见[直接返回契约](../../docs/界面变量直接返回-20261001.md)。每天首次可发布时追加当天00:00—23:45的96点totalPowerForecastDayAhead，其他响应不附带，平台保留当天曲线；不限制08:30，不做全天优化。新能源只读请求。原预测初始化代理路径及14项价格GET/PUT保持不变。

## 构建和启动

在仓库根目录执行。先通过原交付的image.tar.gz导入两份原预测镜像，或确保构建环境能拉取.env.example指定的原镜像：

```sh
docker load -i <单点原包目录>/image.tar.gz
docker load -i <全天原包目录>/image.tar.gz
docker compose --env-file deploy/forecast-dispatch/.env.example -f deploy/forecast-dispatch/compose.yaml build
docker compose --env-file deploy/forecast-dispatch/.env.example -f deploy/forecast-dispatch/compose.yaml up -d --no-build --wait --wait-timeout 360
```

优化Python环境单独按照uv.lock安装；原预测使用各自依赖版本。构建需要安装优化依赖的网络，已生成的离线包启动只需要导入一个合并镜像，不需要联网、Python或另外两个预测容器。Windows离线包运行 `powershell -NoProfile -File .\start.ps1`，Linux运行 `sh start.sh`。

从20260929-r3离线包开始，两个启动脚本会读取包内.env.example的DISPATCH_IMAGE并显式设置到Compose进程环境，覆盖宿主机残留的同名变量，保证使用刚导入的包内镜像。直接运行Docker Compose时不经过此保护，需要自行核对 `docker compose ... config --images`。此次修复不代替下面的数据卷迁移步骤。

默认绑定127.0.0.1，按平台需要配置DISPATCH_BIND和DISPATCH_PORT。容器内部端口固定，不通过HOST/PORT覆盖；宿主机端口可调整。不要将FORECAST_BASE_URL改为容器外地址。直接 `docker run` 时使用 `--init`、只发布8000并挂载下面三个目录。

## 缓存和升级

保留旧Compose项目名和三个命名卷，容器内路径调整如下：

| 命名卷 | 新挂载点 | 内容 |
|---|---|---|
| single_step_forecast_runtime | /opt/forecast-single/runtime | 单点预测历史及latest |
| day_ahead_forecast_runtime | /opt/forecast-day/runtime | 全天预测历史及latest |
| single_step_dispatch_runtime | /app/runtime | 优化SQLite和日志 |

原预测缓存文件名保持不变；两套缓存不能混用。新空卷的单点历史至少288点，全天至少672点；天气缺失可能需要更多真实历史。健康不代表历史已满足预测条件。每日自然日曲线优先保存前一日23:45末帧对应的预测；若该批次缺失，r5会从已有零点前历史在临时缓存中自动补算。需至少672点连续历史及有效天气上下文，数据不足时继续等待，不拼接滚动批次。初始化代理按时间升序同时预热两个模型，持续运行覆盖日界线。候选及每日发布记录也在优化SQLite卷内持久保存。

从旧三容器升级时，先备份并停止旧项目，保留数据卷。用同一个项目名执行 `docker compose ... down --remove-orphans`，**不要添加-v**。原预测卷可能由root创建，新镜像以UID10001运行；需在服务停止时，对这三个卷执行一次目录权限迁移：

```sh
docker compose --env-file deploy/forecast-dispatch/.env.example -f deploy/forecast-dispatch/compose.yaml run --rm --no-deps --user 0 --entrypoint /bin/sh dispatch -c 'chown -R 10001:10001 /opt/forecast-single/runtime /opt/forecast-day/runtime /app/runtime'
docker compose --env-file deploy/forecast-dispatch/.env.example -f deploy/forecast-dispatch/compose.yaml up -d --no-build --remove-orphans --wait --wait-timeout 360
```

迁移命令只用于已有卷的权限调整，正常运行只启动一个容器。旧镜像的/app/output对应新/app/runtime，同一卷中的数据库文件无需转换。更换Compose项目名会创建新卷，除非显式配置原卷名称。

## 生命周期与核验

入口为 `python -m src.container_runtime`。两套预测模型加载并能响应后才启动优化API；冷启动无预测时的404/no_forecast是允许状态。任一进程退出，或连续三次健康检查失败，入口停止其余进程并非零退出，交给容器restart策略整体重启。正常停止会向全部进程组发送终止信号，包括正在运行的求解子进程。

使用未占用端口、独立项目和新数据卷验收，例如项目fluxcast-single-verify。设置DISPATCH_PORT=18868后启动；Windows用PowerShell的$env:赋值，Linux用export。不要复用旧联调缓存。

```sh
uv run python scripts/check_forecast_bridge_live.py --combined --forecast-url http://127.0.0.1:18868 --dispatch-container fluxcast-single-verify-dispatch-1 --output output/forecast-integration/single-container-new
uv run python scripts/check_combined_image.py --image jingneng-fluxcast-all-in-one:20261001-r7 --output output/forecast-integration/single-container-new/combined-image.json
```

第一项回放真实历史并执行实际预测及HiGHS求解，同时检查仅一个容器、原接口和extra_info；新能源为明确的测试情景，不能作为现场闭环验收。第二项逐文件校验两套原程序/模型以及依赖版本。另需验证重建后历史/SQLite保留、子进程故障导致整个容器退出。历史回放时钟只存在隔离测试进程，生产API没有时钟覆盖。

离线打包器只接受同一个合并镜像对应的新验收证据，最终只打包一个可运行镜像，保留原模型身份记录和源代码。旧20260926-r3下载包不会自动变成单容器。当前原镜像为Linux/amd64，ARM目标需要对应的原模型镜像和重新验证。
