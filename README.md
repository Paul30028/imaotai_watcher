# imaotai_watcher

i茅台自动申购系统 — 支持多账号并发申购、Web 管理界面、Docker 一键部署。

## 功能特性

- **多账号管理**：支持添加多个 i茅台账号，短信验证码登录，自动维护 token
- **精准定时申购**：默认 09:00 触发，支持自定义时间，失败自动重试（最多 3 次）
- **并发申购**：多账号同时申购，提升成功率
- **商品配置**：支持全局默认商品和账号级独立配置，账号级优先
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
| 账号管理 | `/accounts` | 添加/编辑/删除 i茅台账号，短信验证码登录，刷新 token |
| 商品配置 | `/products` | 配置全局或账号级申购商品，启用/禁用 |
| 申购日志 | `/logs` | 查看历史申购记录，支持日期/账号/状态筛选 |
| 系统设置 | `/settings` | 申购时间配置、Server酱 SendKey 配置、手动触发申购 |

## 申购流程

```
Scheduler 09:00 触发
  ├── 查询所有 status=active 的账号
  └── 并发执行每个账号：
        ├── 获取商品列表（账号级优先，回退全局默认）
        ├── 对每个 enabled 商品调用申购 API
        │     ├── 成功 → 写日志(success)
        │     └── 失败 → 重试最多 3 次（间隔 1 秒）
        │           └── 全部失败 → 写日志(fail)
        └── token 过期 → 标记账号 expired，推送告警
  └── 汇总结果 → Server酱 推送今日摘要
```

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

## 免责声明

本项目仅供学习交流使用，请遵守 i茅台平台相关规定，合理使用。
