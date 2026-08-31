# imaotai_watcher

i茅台自动申购系统 — 支持多账号并发申购、Web 管理界面、Docker 一键部署。

> **接口来源说明**：`backend/core/imaotai_api.py` 对接的是 i茅台 App 的私有接口，
> 逆向自开源项目 [oddfar/campus-imaotai](https://github.com/oddfar/campus-imaotai)
> 的 `IMTServiceImpl.java` / `IShopServiceImpl.java`（并做过 AES/MD5 签名的独立单测
> 验证），**并非官方公开 API**。接口路径、请求头、AES 密钥等可能随官方 App 更新而失效，
> 需要自行跟进维护；本项目仅供学习交流使用，请遵守 i茅台平台相关规定，合理使用，不用于
> 批量注册小号、代抢倒卖等违反平台规则或法律法规的用途。

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
- **Docker 部署**：三容器架构，对接外部 MySQL + Redis

## 系统架构

```
Browser
  └─→ Nginx :80
        ├─→ /         → React 静态文件
        └─→ /api/     → FastAPI :8000
                            │         │
                          MySQL     Redis
                            │         │
                      Scheduler（独立容器）
```

| 容器 | 说明 |
|------|------|
| `api` | FastAPI + uvicorn，处理所有 HTTP 请求 |
| `scheduler` | APScheduler 独立进程，执行定时申购任务 |
| `frontend` | Nginx 服务 React 静态文件，反代 `/api/` 到 api 容器 |

MySQL 和 Redis 使用外部已有实例，不纳入 docker-compose 管理。

## 目录结构

```
imaotai_watcher/
├── backend/
│   ├── api/              # FastAPI 路由（auth/accounts/products/logs/scheduler/settings）
│   ├── core/             # i茅台 API 客户端、申购逻辑、Server酱通知
│   ├── models/           # SQLAlchemy ORM 模型
│   ├── schemas/          # Pydantic 请求/响应模型
│   ├── scheduler/        # APScheduler 独立进程入口
│   ├── utils/            # 签名算法、日志配置
│   ├── main.py           # FastAPI 应用入口
│   ├── database.py       # 数据库连接
│   ├── redis_client.py   # Redis 连接
│   ├── init_db.py        # 初始化表结构和管理员账号
│   ├── config.py         # 环境变量配置
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/
│   ├── src/
│   │   ├── pages/        # Login / Dashboard / Accounts / Products / Logs / Settings
│   │   ├── components/   # AppLayout、PrivateRoute
│   │   ├── api/          # axios 封装 + 各模块请求函数
│   │   └── store/        # Zustand 状态管理（JWT）
│   ├── package.json
│   └── Dockerfile
├── docker-compose.yml
└── .env.example
```

## 快速开始

> 下面是精简版部署步骤；完整的分步说明（含没有现成 MySQL/Redis 时怎么办、
> 启动后如何逐项验证、常见故障排查）见 [RUNNING.md](./RUNNING.md)。

### 前置条件

- Docker + Docker Compose
- 可用的 MySQL 实例（提前创建数据库 `imaotai`）
- 可用的 Redis 实例

### 部署步骤

**1. 克隆仓库**

```bash
git clone <repo-url>
cd imaotai_watcher
```

**2. 配置环境变量**

```bash
cp .env.example .env
```

编辑 `.env`，填入实际配置：

```env
# JWT 密钥（随机字符串，建议 32 位以上）
JWT_SECRET=your-random-secret-key

# 初始管理员账号
ADMIN_USERNAME=admin
ADMIN_PASSWORD=your-admin-password

# MySQL 连接（外部实例）
MYSQL_HOST=192.168.1.100
MYSQL_PORT=3306
MYSQL_DATABASE=imaotai
MYSQL_USER=imaotai
MYSQL_PASSWORD=your-mysql-password

# Redis 连接（外部实例）
REDIS_HOST=192.168.1.100
REDIS_PORT=6379
REDIS_PASSWORD=

# 日志级别（DEBUG/INFO/WARNING/ERROR）
LOG_LEVEL=INFO
```

**3. 启动服务**

```bash
docker-compose up -d
```

**5. 访问系统**

打开浏览器访问 `http://your-server-ip`，使用 `.env` 中配置的管理员账号登录。

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

也支持在「系统设置」页点击"立即申购"，对全部 active 账号立即触发（不看分钟分配）。

## 技术栈

**后端**

| 组件 | 版本 | 用途 |
|------|------|------|
| FastAPI | 0.111 | Web 框架 |
| SQLAlchemy | 2.0 | ORM |
| APScheduler | 3.10 | 定时任务 |
| redis-py | 5.0 | 心跳/跨进程触发/限流/缓存 |
| python-jose | 3.3 | JWT |
| passlib[bcrypt] | 1.7 | 密码哈希 |
| httpx | 0.27 | i茅台 API HTTP 客户端 |

**前端**

| 组件 | 版本 | 用途 |
|------|------|------|
| React | 18 | UI 框架 |
| TypeScript | 5 | 类型安全 |
| Ant Design | 5.x | 组件库 |
| @ant-design/charts | - | 趋势折线图 |
| Zustand | - | 状态管理（JWT 持久化） |
| React Router | v6 | 路由 |
| Vite | - | 构建工具 |
| axios | - | HTTP 客户端 |

## 环境变量说明

| 变量 | 必填 | 默认值 | 说明 |
|------|------|--------|------|
| `JWT_SECRET` | 是 | — | JWT 签名密钥 |
| `ADMIN_USERNAME` | 是 | — | 初始管理员用户名 |
| `ADMIN_PASSWORD` | 是 | — | 初始管理员密码 |
| `MYSQL_HOST` | 是 | — | MySQL 主机地址 |
| `MYSQL_PORT` | 否 | `3306` | MySQL 端口 |
| `MYSQL_DATABASE` | 是 | — | 数据库名 |
| `MYSQL_USER` | 是 | — | 数据库用户名 |
| `MYSQL_PASSWORD` | 是 | — | 数据库密码 |
| `REDIS_HOST` | 是 | — | Redis 主机地址 |
| `REDIS_PORT` | 否 | `6379` | Redis 端口 |
| `REDIS_PASSWORD` | 否 | 空 | Redis 密码 |
| `LOG_LEVEL` | 否 | `INFO` | 日志级别 |

## 开发环境

### 后端

```bash
cd backend
pip install -r requirements.txt

# 配置环境变量
export MYSQL_HOST=localhost
# ... 其他变量

# 启动 API
uvicorn main:app --reload

# 启动 Scheduler（另开终端）
python scheduler/main.py

# 运行测试
pytest
```

### 前端

```bash
cd frontend
npm install

# 启动开发服务器（自动代理 /api/ 到 localhost:8000）
npm run dev

# 构建
npm run build
```

## 验证状态

以下内容已在本地起真实 MySQL + Redis 实测通过：数据库迁移（含旧表结构升级）、
管理员登录、账号增删改查、调度器任务编排（每日随机分钟分配 + cron 注册）、
并发申购的多线程 Session 隔离、前端 TypeScript 构建。

**尚未用真实 i茅台账号验证过**：发送验证码 / 登录 / 查询今日商品 / 提交申购 /
查询申购结果这几个真正对接 i茅台后端的调用。这几个接口的路径、请求头、AES 密钥
都是照抄自 [oddfar/campus-imaotai](https://github.com/oddfar/campus-imaotai) 的
可运行开源实现，逻辑上可信，但没有用真账号跑通过，也无法保证不随官方 App 更新失效。
**首次部署后请先用一个真实手机号走一遍"发送验证码 → 登录"流程确认可用**，如果失败，
把 api 容器日志（`docker-compose logs api`）里的报错发出来，可以针对性排查是接口
变了还是配置问题。

## 常见问题

**调度器状态显示"已停止"**

Scheduler 容器通过 Redis key `scheduler:heartbeat`（TTL 60s）上报心跳，若超过 60 秒未更新则 API 判断为停止。检查 scheduler 容器日志：

```bash
docker-compose logs scheduler
```

**token 过期导致账号被标记为 expired**

在「账号管理」页面点击"刷新Token"，重新走一遍短信验证码登录流程即可恢复。

**首次启动后无法登录**

api 容器启动时会自动建表并创建管理员账号，确认 `.env` 中 `ADMIN_USERNAME` 和 `ADMIN_PASSWORD` 与登录时输入一致，并检查 api 容器日志确认 "Database ready." 已输出。

**商品配置页"今日在售商品"下拉为空**

该列表来自 i茅台当日场次接口，需要 scheduler 容器完成过一次早晨的缓存刷新
（07:10/07:55/08:10/08:55 任一时间点）才会有数据；也可以在服务器上手动触发一次：

```bash
docker-compose exec scheduler python -c "from core.imaotai_api import refresh_catalogue_cache; refresh_catalogue_cache()"
```

**升级到本版本后旧账号的门店信息为空**

旧版本的 `city_code` 字段已废弃，`init_db.py` 会自动给已有的 `accounts` 表加上
`province_name`/`city_name`/`lat`/`lng`/`shop_type` 等新列（默认空值），升级后需要
在「账号管理」页编辑已有账号，补全省市和经纬度信息，否则申购时会报"门店为空"。

## 免责声明

本项目仅供学习交流使用，请遵守 i茅台平台相关规定，合理使用。
