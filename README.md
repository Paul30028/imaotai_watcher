# imaotai_watcher

i茅台自动申购系统 — 支持多账号并发申购、Web 管理界面，**单容器一键部署，
没有外部依赖**（数据库用内嵌 SQLite，调度器和 API 是同一个进程）。

> **接口来源说明**：`backend/core/imaotai_api.py` 对接的是 i茅台 App 的私有接口，
> 逆向自开源项目 [oddfar/campus-imaotai](https://github.com/oddfar/campus-imaotai)
> 的 `IMTServiceImpl.java` / `IShopServiceImpl.java`（并做过 AES/MD5 签名的独立单测
> 验证），请求头字段又对照 [AkenClub/ken-iMoutai-Script](https://github.com/AkenClub/ken-iMoutai-Script)
> 和 [397179459/iMaoTai-reserve](https://github.com/397179459/iMaoTai-reserve) 这两个
> 有真实用户确认申购成功的活跃项目做过交叉验证，**并非官方公开 API**。接口路径、请求头、
> AES 密钥等可能随官方 App 更新而失效，需要自行跟进维护；本项目仅供学习交流使用，请遵守
> i茅台平台相关规定，合理使用，不用于批量注册小号、代抢倒卖等违反平台规则或法律法规的用途。

## 功能特性

- **多账号管理**：支持添加多个 i茅台账号，短信验证码登录，自动维护 token/cookie
- **错峰定时申购**：i茅台申购入口固定在 9:00-9:59 这一小时开放，每个账号在窗口内按
  随机（或固定）分钟触发，避免所有账号同一秒并发导致限流；失败自动重试（最多 3 次）
- **并发申购**：多账号同时申购，提升成功率
- **门店选择**：按省份/城市 + 经纬度，支持"本市出货量最大门店"或"距离最近门店"两种策略
- **商品配置**：商品编码从当日在售商品列表中动态选择（每日变化），支持全局默认商品和
  账号级独立配置，账号级优先
- **结果确认**：每日结果公布时间（默认 18:05）自动查询官方申购结果并回填日志
- **结果通知**：通过 Server酱 推送申购结果到微信，token 过期时告警
- **Web 管理界面**：React + Ant Design，含数据统计图表
- **JWT 鉴权**：admin / viewer 双角色，viewer 只读
- **单容器部署**：`docker run` 一条命令启动，没有 MySQL/Redis 之类的外部依赖
- **GitHub Actions 备用申购路径**：申购请求可选择从 GitHub 云端 IP 发出，避开本地
  网络被限流的情况（见 [RUNNING.md「路径三」](./RUNNING.md#路径三github-actions绕开本地-ip-限流)）

## 系统架构

```
Browser ──→ uvicorn（单进程，:8000）
              ├── /api/*  → FastAPI 路由
              ├── 其它路径 → 打包好的 React 静态文件（SPA）
              ├── 后台线程 → APScheduler（定时申购/刷新/结果查询）
              └── SQLite 文件（backend/data/imaotai.db，容器里挂 volume 持久化）
```

早期版本是 api / scheduler / frontend 三容器 + 外部 MySQL + 外部 Redis 的架构；
现在合并成了一个进程：调度器作为应用启动时的后台线程运行（不再需要 Redis
心跳/消息队列在进程间通信），前端编译产物由同一个 FastAPI 应用直接托管（不再
需要 nginx 反代），数据库换成单文件 SQLite（不再需要单独的数据库服务）。目的
是让"部署"这件事对个人自托管场景足够简单：一条 `docker run` 或者
`pip install && python main.py` 就能跑起来。

## 目录结构

```
imaotai_watcher/
├── backend/
│   ├── api/              # FastAPI 路由（auth/accounts/products/logs/scheduler/settings）
│   ├── core/             # i茅台 API 客户端、申购逻辑、Server酱通知
│   ├── models/           # SQLAlchemy ORM 模型
│   ├── schemas/          # Pydantic 请求/响应模型
│   ├── scheduler/        # 调度任务定义 + 启停（main.py 生命周期里作为后台线程启动）
│   ├── utils/            # 签名算法、进程内 TTL 缓存、日志配置
│   ├── main.py           # FastAPI 应用入口：API 路由 + 前端静态文件 + 调度器
│   ├── database.py       # SQLite 连接
│   ├── init_db.py        # 初始化表结构、管理员账号、旧库列迁移
│   ├── config.py         # 环境变量配置
│   ├── requirements.txt
│   └── data/              # SQLite 数据文件默认写在这里（.gitignore 已排除）
├── frontend/
│   ├── src/
│   │   ├── pages/        # Login / Dashboard / Accounts / Products / Logs / Settings
│   │   ├── components/   # AppLayout、PrivateRoute
│   │   ├── api/          # axios 封装 + 各模块请求函数
│   │   └── store/        # Zustand 状态管理（JWT）
│   └── package.json
├── Dockerfile             # 多阶段构建：编译前端 → 塞进后端镜像，单容器产物
├── docker-compose.yml     # 单服务 + 一个持久化 volume
└── .env.example
```

## 快速开始

> 下面是精简版部署步骤；完整的分步说明（含本地开发怎么跑、启动后如何逐项验证、
> 常见故障排查）见 [RUNNING.md](./RUNNING.md)。

### 前置条件

- Docker（不需要 Docker Compose 也行，直接 `docker build`+`docker run` 也可以）

不需要预先准备 MySQL、Redis 或任何其他外部服务。

### 部署步骤

```bash
git clone https://github.com/Paul30028/imaotai_watcher
cd imaotai_watcher
cp .env.example .env
# 编辑 .env：至少改 JWT_SECRET 和 ADMIN_PASSWORD

docker-compose up -d --build
```

打开浏览器访问 `http://your-server-ip:8000`，用 `.env` 里配置的管理员账号登录。

数据（账号、商品、日志）存在 Docker 具名 volume `imaotai-data` 里，重建/更新容器
不会丢失；备份就是备份这一个 volume（或直接备份 `backend/data/imaotai.db` 这一
个文件，如果你不用 volume 而是本机运行）。

> 如果发验证码/申购持续报 `429 Too Many Requests`，通常是你本地网络的出口 IP
> 被限流了，跟部署对不对没关系。除了 Docker/本地运行，仓库里还带了一份
> GitHub Actions workflow（`.github/workflows/reserve.yml` + `backend/gh_action_reserve.py`），
> 申购请求从 GitHub 的云端 IP 发出，天然绕开本地限流，见 [RUNNING.md「路径三」](./RUNNING.md#路径三github-actions绕开本地-ip-限流)。

## 页面说明

| 页面 | 路径 | 功能 |
|------|------|------|
| 登录 | `/login` | 用户名 + 密码登录 |
| 仪表盘 | `/dashboard` | 统计卡片、7日趋势图、最近申购记录（30秒自动刷新） |
| 账号管理 | `/accounts` | 添加/编辑/删除 i茅台账号，短信验证码登录，刷新 token；填写省市+经纬度+门店选择方式+错峰分钟策略；列表显示今日实际分配到的申购分钟 |
| 商品配置 | `/products` | 从当日在售商品接口 (`GET /api/accounts/today-items`) 下拉选择商品并配置全局或账号级申购项，启用/禁用 |
| 申购日志 | `/logs` | 查看历史申购记录，支持日期/账号/状态筛选（status: success/fail/confirmed） |
| 系统设置 | `/settings` | 申购窗口小时配置、Server酱 SendKey 配置、手动触发申购 |

### 账号信息填写说明

添加账号时除了手机号，还需要：

| 字段 | 说明 |
|------|------|
| `province_name` / `city_name` | 完整省市名称，如"广东省"/"深圳市"，用于查询该省当日门店库存 |
| `lat` / `lng` | 账号常用地址的纬度/经度，用于"距离最近门店"策略，也作为申购请求的 `MT-Lat`/`MT-Lng` 头。可在地图 App（高德/百度/Apple 地图）中长按目标位置获取坐标 |
| `shop_type` | `1`=预约本市出货量最大的门店（本市查不到会自动退化为本省最近门店）；`2`=直接预约本省距离最近的门店 |
| `random_minute` / `fixed_minute` | 是否在 9 点这一小时内随机分配申购分钟错峰；关闭后需指定 `fixed_minute`（1-59） |

登录成功后，`token`/`cookie`/`userId` 会自动保存；账号列表的"今日申购分钟"列显示当天凌晨（01:10）自动分配的实际触发分钟。

## 申购流程

```
01:10  为所有 status=active 账号分配今日申购分钟（随机/固定，1-59）
07:10 / 07:55 / 08:10 / 08:55  预热 App 版本号 / 场次 / 门店数据缓存
09:00-09:59  逐分钟检查，命中当前分钟的账号并发申购：
  ├── 按 shop_type 选门店（本市库存最高 or 经纬度最近）
  ├── 对每个 enabled 商品调用申购 API（AES 加密 actParam）
  │     ├── 成功 → 写日志(success)
  │     └── 失败 → 重试最多 3 次（间隔 1 秒）
  │           └── 全部失败 → 写日志(fail)
  │           └── 判断为 token 失效 → 标记账号 expired，推送告警
  └── 汇总结果 → Server酱 推送本次申购摘要
18:05  查询官方申购结果，回填 confirmed 日志 → Server酱 推送确认摘要
```

以上所有定时任务都锁定为北京时间（UTC+8），与容器/宿主机的系统时区无关。

也支持在「系统设置」页点击"立即申购"，对全部 active 账号立即触发（不看分钟分配）。

## 技术栈

**后端**

| 组件 | 版本 | 用途 |
|------|------|------|
| FastAPI | 0.111 | Web 框架，同时托管 API 和前端静态文件 |
| SQLAlchemy | 2.0 | ORM（SQLite） |
| APScheduler | 3.10 | 应用内后台线程，定时任务 |
| python-jose | 3.3 | JWT |
| passlib[bcrypt] | 1.7 | 密码哈希 |
| httpx | 0.27 | i茅台 API HTTP 客户端 |
| pycryptodome | 3.20 | 申购请求体的 AES-256-CBC 加密 |

**前端**

| 组件 | 版本 | 用途 |
|------|------|------|
| React | 18 | UI 框架 |
| TypeScript | 5 | 类型安全 |
| Ant Design | 5.x | 组件库 |
| @ant-design/charts | - | 趋势折线图 |
| Zustand | - | 状态管理（JWT 持久化） |
| React Router | v6 | 路由（客户端路由，由后端的 SPA fallback 支持） |
| Vite | - | 构建工具 |
| axios | - | HTTP 客户端 |

## 环境变量说明

| 变量 | 必填 | 默认值 | 说明 |
|------|------|--------|------|
| `JWT_SECRET` | 是 | — | JWT 签名密钥 |
| `ADMIN_USERNAME` | 否 | `admin` | 初始管理员用户名 |
| `ADMIN_PASSWORD` | 是 | — | 初始管理员密码 |
| `DATABASE_URL` | 否 | `sqlite:///./data/imaotai.db` | SQLAlchemy 数据库连接串，一般不用改 |

不再需要配置 MySQL/Redis 相关变量。

## 开发环境

```bash
cd backend
pip install -r requirements.txt

export jwt_secret=devsecret
export admin_password=你的密码

# API + 调度器（同一个进程）
uvicorn main:app --reload

# 运行测试（纯 SQLite，不需要起任何外部服务）
pytest
```

```bash
cd frontend
npm install
npm run dev     # 默认 http://localhost:5173，自动代理 /api/ 到 localhost:8000
```

本地开发时前端和后端是两个进程（`npm run dev` 的热重载体验更好）；只有打
Docker 镜像时才会把前端编译产物塞进后端一起提供，见 [RUNNING.md](./RUNNING.md)。

## 验证状态

以下内容已在本地实测通过（纯 SQLite，无需任何外部服务）：数据库初始化 +
旧库列迁移、管理员登录、账号增删改查、调度器在应用内启动/立即触发/配置变更后
重新排班、前端 TypeScript 构建、后端同时提供 API 与 SPA 静态文件（含 SPA 客户端
路由 fallback、静态资源、path traversal 防护的针对性验证）。

**尚未用真实 i茅台账号验证过**：发送验证码 / 登录 / 查询今日商品 / 提交申购 /
查询申购结果这几个真正对接 i茅台后端的调用。这几个接口的路径、请求头、AES 密钥
都是照抄自 [oddfar/campus-imaotai](https://github.com/oddfar/campus-imaotai) 的
可运行开源实现，逻辑上可信，但没有用真账号跑通过，也无法保证不随官方 App 更新失效。
**首次部署后请先用一个真实手机号走一遍"发送验证码 → 登录"流程确认可用**，如果失败，
把容器日志（`docker-compose logs -f`）里的报错发出来，可以针对性排查是接口
变了还是配置问题。

## 常见问题

**调度器状态显示"已停止"**

调度器现在是应用内的一个后台线程，跟着 API 进程一起活/一起挂，所以"已停止"
基本等价于"整个容器没起来或者刚重启还没完成初始化"。看容器日志：

```bash
docker-compose logs -f
```

**token 过期导致账号被标记为 expired**

在「账号管理」页面点击"刷新Token"，重新走一遍短信验证码登录流程即可恢复。

**首次启动后无法登录**

应用启动时会自动建表并创建管理员账号，确认 `.env` 中 `ADMIN_USERNAME` 和 `ADMIN_PASSWORD` 与登录时输入一致，并检查日志确认 "Database ready." 已输出。

**商品配置页"今日在售商品"下拉为空**

该列表来自 i茅台当日场次接口，需要完成过一次早晨的缓存刷新
（07:10/07:55/08:10/08:55 任一时间点）才会有数据；也可以手动触发一次：

```bash
docker-compose exec app python -c "from core.imaotai_api import refresh_catalogue_cache; refresh_catalogue_cache()"
```

**升级到"真实接口版"后旧账号的门店信息为空**

更早版本的 `city_code` 字段已废弃，`init_db.py` 会自动给已有的 `accounts` 表加上
`province_name`/`city_name`/`lat`/`lng`/`shop_type` 等新列（默认空值），升级后需要
在「账号管理」页编辑已有账号，补全省市和经纬度信息，否则申购时会报"门店为空"。

**从旧的三容器 + MySQL/Redis 版本升级**

数据库从 MySQL 换成了 SQLite，不会自动迁移旧数据；如果你手头有旧版本 MySQL
里的账号/日志数据需要保留，需要手动导出后写入新的 SQLite 文件（或者干脆用
新版重新登录账号，反正 token 本来就会过期需要重新登录）。

## 免责声明

本项目仅供学习交流使用，请遵守 i茅台平台相关规定，合理使用。
