# imaotai_watcher 设计文档

**日期：** 2026-04-14  
**项目：** imaotai_watcher — i茅台自动抢购软件  
**参考：** https://github.com/wudizhanshen012/imaotai_autobuy

> **2026-08-30 更新说明**：本文档记录的是最初的骨架设计。实际实现中
> `backend/core/imaotai_api.py` / `backend/utils/signature.py` 最初对接的接口契约是
> 虚构的、未跑通过真实后端，已改为对接逆向自
> [oddfar/campus-imaotai](https://github.com/oddfar/campus-imaotai) 并做过单测验证的
> 真实接口契约；数据模型、调度策略（错峰申购、结果确认）也相应调整。以 README.md 和
> 代码为准，本文档仅保留作为架构演进的历史记录。

---

## 1. 需求概述

构建一个 i茅台自动申购系统，支持：
- 多账号并发申购，每账号可独立配置商品
- 精确定时（默认 09:00）触发申购，失败自动重试（最多3次）
- Server酱推送申购结果通知
- Docker 容器化部署
- React + Ant Design 前端 Web 管理界面
- JWT 登录鉴权，支持多系统用户（admin/viewer 角色）
- 数据统计图表（近7日趋势）

---

## 2. 整体架构

### 方案：双容器拆分（方案 B）

API 服务与调度器独立运行，互不影响。09:00 申购窗口期间，前端操作不会中断任务。

```
Browser
  └─→ Nginx :80
        ├─→ /         → React 静态文件
        └─→ /api/     → FastAPI :8000
                            │         │
                          MySQL     Redis
                            │         │
                      Scheduler（独立容器，连接同一 MySQL + Redis）
```

**Redis 使用场景（4处）：**

| 场景 | Key 设计 | 说明 |
|------|---------|------|
| 调度器心跳 | `scheduler:heartbeat`（TTL 60s） | 替代 scheduler_state 表轮询，API 读 key 是否存在判断存活 |
| 手动触发申购 | `scheduler:trigger`（List，LPUSH/BRPOP） | API LPUSH 消息，Scheduler BRPOP 阻塞等待，实现跨进程通知 |
| 验证码防刷 | `sms:limit:{phone}`（TTL 60s） | 发送验证码接口限流，60秒内只允许发一次 |
| 接口缓存 | `cache:stats`（TTL 300s） | `/api/logs/stats` 统计数据缓存，避免每次重算近7日数据 |

### 目录结构

```
imaotai_watcher/
├── backend/
│   ├── api/
│   │   ├── auth.py            # 登录、JWT 刷新
│   │   ├── accounts.py        # 账号 CRUD、验证码登录
│   │   ├── products.py        # 商品配置 CRUD
│   │   ├── logs.py            # 申购日志查询、统计
│   │   ├── scheduler.py       # 调度器状态、手动触发
│   │   └── settings.py        # 通知配置
│   ├── core/
│   │   ├── imaotai_api.py     # i茅台 API 封装（签名、重试）
│   │   ├── purchase.py        # 申购核心逻辑
│   │   └── notifier.py        # Server酱推送
│   ├── scheduler/
│   │   └── main.py            # APScheduler 独立进程入口
│   ├── models/
│   │   └── models.py          # SQLAlchemy ORM 模型
│   ├── schemas/
│   │   └── schemas.py         # Pydantic 请求/响应模型
│   ├── utils/
│   │   ├── signature.py       # 请求签名算法
│   │   ├── time_sync.py       # 时间同步
│   │   └── logger.py          # 日志配置
│   ├── main.py                # FastAPI 应用入口
│   ├── database.py            # SQLAlchemy 连接配置
│   ├── requirements.txt
│   └── Dockerfile             # api 和 scheduler 共用同一镜像
├── frontend/
│   ├── src/
│   │   ├── pages/
│   │   │   ├── Login.tsx
│   │   │   ├── Dashboard.tsx
│   │   │   ├── Accounts.tsx
│   │   │   ├── Products.tsx
│   │   │   ├── Logs.tsx
│   │   │   └── Settings.tsx
│   │   ├── components/        # 通用组件（Layout、PrivateRoute 等）
│   │   ├── api/               # axios 实例 + 各模块请求函数
│   │   ├── store/             # 全局状态（JWT、用户信息）
│   │   └── App.tsx
│   ├── package.json
│   └── Dockerfile             # 两阶段构建：node:18 build → nginx:alpine serve
├── nginx/
│   └── nginx.conf
├── docker-compose.yml
└── .env.example
```

---

## 3. 数据模型

### MySQL 表（5张）

#### users — 系统登录用户
| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | |
| username | VARCHAR UNIQUE | |
| password_hash | VARCHAR | bcrypt |
| role | VARCHAR | admin / viewer |
| created_at | DATETIME | |

#### accounts — i茅台账号
| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | |
| phone | VARCHAR UNIQUE | 手机号 |
| token | VARCHAR | i茅台 token |
| device_id | VARCHAR | 设备 ID |
| city_code | VARCHAR | 城市编码 |
| status | VARCHAR | active / expired |
| last_login | DATETIME | |
| created_at | DATETIME | |

#### products — 商品配置
| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | |
| account_id | INTEGER FK nullable | NULL = 全局默认 |
| item_code | VARCHAR | 商品编码 |
| item_name | VARCHAR | 商品名称 |
| enabled | BOOLEAN | |

账号级配置优先于全局默认。

#### purchase_logs — 申购记录
| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | |
| account_id | INTEGER FK | |
| item_code | VARCHAR | |
| item_name | VARCHAR | |
| status | VARCHAR | success / fail / retry |
| message | TEXT | API 返回信息 |
| purchased_at | DATETIME | |

只写不改，保留完整历史。

#### scheduler_state — 调度器心跳
| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 固定为 1 |
| next_run_at | DATETIME | 下次执行时间 |
| last_run_at | DATETIME | 上次执行时间 |
| last_heartbeat | DATETIME | 调度器进程心跳 |
| schedule_time | VARCHAR | 申购时间，默认 "09:00" |

调度器心跳改由 Redis key `scheduler:heartbeat`（TTL 60s）维护，此表仅保留 `next_run_at`、`last_run_at`、`schedule_time` 三个字段用于持久化。API 读 Redis key 是否存在判断调度器存活，不再轮询数据库。

---

## 4. 后端 API 接口

### 认证
```
POST /api/auth/login          # 用户名密码登录，返回 JWT
POST /api/auth/refresh        # 刷新 token
```

### 账号管理
```
GET    /api/accounts                    # 账号列表（含状态）
POST   /api/accounts                    # 添加账号
PUT    /api/accounts/{id}               # 更新账号（城市、状态）
DELETE /api/accounts/{id}               # 删除账号
POST   /api/accounts/{id}/verify        # 发送验证码
POST   /api/accounts/{id}/login         # 验证码登录，刷新 token
```

### 商品配置
```
GET    /api/products                    # 商品列表（?account_id= 过滤）
POST   /api/products                    # 添加商品
PUT    /api/products/{id}               # 更新（启用/禁用）
DELETE /api/products/{id}               # 删除
```

### 申购日志
```
GET /api/logs                           # 日志列表（分页、日期、账号过滤）
GET /api/logs/stats                     # 统计（成功率、近7日趋势）
```

### 任务控制
```
GET  /api/scheduler/status              # 调度器状态（心跳、下次执行时间）
POST /api/scheduler/trigger             # 手动立即触发申购
PUT  /api/scheduler/config              # 修改申购时间
```

### 通知设置
```
GET  /api/settings/notify               # 获取 Server酱 配置
PUT  /api/settings/notify               # 更新 SendKey
POST /api/settings/notify/test          # 发送测试通知
```

所有接口（除 `/api/auth/login`）均需 `Authorization: Bearer <token>` header。  
viewer 角色只有读权限，写操作返回 403。

---

## 5. 前端页面

### 路由结构
```
/login          登录页
/               重定向到 /dashboard
/dashboard      仪表盘
/accounts       账号管理
/products       商品配置
/logs           申购日志
/settings       系统设置
```

未登录访问任何页面自动跳转 `/login`。

### 各页面功能

**登录页（/login）**
- 用户名 + 密码表单，提交后存储 JWT 到 localStorage

**仪表盘（/dashboard）**
- 数字卡片：账号总数 / 今日成功次数 / 今日失败次数 / 调度器状态
- 近7日申购趋势折线图（成功 vs 失败，@ant-design/charts）
- 最近20条申购记录表格，每30秒自动刷新

**账号管理（/accounts）**
- 账号列表表格：手机号、城市、状态（正常/token过期）、最近登录时间
- 添加账号弹窗：输入手机号 → 点击发验证码 → 输入验证码 → 登录
- 行操作：编辑城市、刷新 token、删除（需确认）

**商品配置（/products）**
- 顶部 Tab 切换：全局默认 / 各账号独立配置
- 商品列表：商品名称、编码、启用状态开关
- 新增商品表单

**申购日志（/logs）**
- 筛选栏：日期范围 / 账号 / 状态（成功/失败）
- 分页表格：时间、账号、商品、状态、API 返回信息

**系统设置（/settings）**
- 申购时间配置（TimePicker，默认 09:00）
- Server酱 SendKey 输入框 + 发送测试通知按钮
- 手动触发申购按钮（点击弹确认框，确认后调用 trigger 接口）

### 技术细节
- React 18 + TypeScript + React Router v6
- Ant Design 5.x 组件库
- @ant-design/charts 折线图
- axios 拦截器：自动注入 JWT，401 自动跳回登录
- Vite 构建

---

## 6. 部署

### docker-compose.yml 服务

| 服务 | 镜像 | 端口 | 说明 |
|------|------|------|------|
| api | backend:latest | 8000（内部） | FastAPI + uvicorn |
| scheduler | backend:latest | 无 | APScheduler 独立进程 |
| nginx | nginx:alpine | 80 | 静态文件 + 反代 |

MySQL 和 Redis 均使用外部已有实例，不纳入 docker-compose 管理。  
api 和 scheduler 共用同一个 backend 镜像，通过不同 CMD 启动：
- api：`uvicorn main:app --host 0.0.0.0 --port 8000`
- scheduler：`python scheduler/main.py`

### 环境变量（.env）
```
# JWT
JWT_SECRET=<随机字符串>

# 初始管理员
ADMIN_USERNAME=admin
ADMIN_PASSWORD=<初始密码>

# MySQL 连接（外部实例）
MYSQL_HOST=<host>
MYSQL_PORT=3306
MYSQL_DATABASE=imaotai
MYSQL_USER=imaotai
MYSQL_PASSWORD=<数据库密码>

# Redis 连接
REDIS_HOST=redis
REDIS_PORT=6379
REDIS_PASSWORD=
```

`database.py` 从环境变量组装 MySQL 连接串：  
`mysql+pymysql://{MYSQL_USER}:{MYSQL_PASSWORD}@{MYSQL_HOST}:{MYSQL_PORT}/{MYSQL_DATABASE}`  
SQLAlchemy 使用连接池（pool_pre_ping=True），自动处理断连重连。

`redis_client.py` 从环境变量初始化 redis-py 连接，api 和 scheduler 容器均复用同一 Redis 服务。

### 启动
```bash
cp .env.example .env
# 编辑 .env 填入配置
docker-compose up -d
# 访问 http://localhost
```

---

## 7. 核心申购流程

```
Scheduler 09:00 触发
  ├── 更新 scheduler_state.last_run_at
  ├── 查询所有 status=active 的账号
  └── 对每个账号并发执行：
        ├── 获取该账号的商品列表（账号级优先，回退全局默认）
        ├── 对每个 enabled 商品调用 i茅台 申购 API
        │     ├── 成功 → 写 purchase_logs(status=success)
        │     └── 失败 → 重试最多3次（间隔1秒）
        │           ├── 重试成功 → 写 purchase_logs(status=success)
        │           └── 全部失败 → 写 purchase_logs(status=fail)
        └── token 过期 → 更新 accounts.status=expired，推送 Server酱 告警
  └── 汇总结果 → Server酱 推送今日申购摘要
```

---

## 8. 错误处理

| 场景 | 处理方式 |
|------|---------|
| i茅台 API 超时 | 重试3次，每次间隔1秒 |
| token 过期 | 账号标记 expired，Server酱告警，跳过该账号 |
| 调度器进程崩溃 | API 通过心跳超时检测，Dashboard 显示异常状态 |
| 前端 JWT 过期 | axios 拦截器捕获 401，自动跳转登录页 |
| 数据库连接断开 | SQLAlchemy pool_pre_ping=True，自动重连 |

---

## 9. 不在本期范围内

- 多通知渠道（企业微信、钉钉）
- Redis/Celery 分布式
- 账号登录二维码方式
- 商品余量查询
