# 运行说明

本文档是从零开始把 imaotai_watcher 跑起来的完整步骤，覆盖两条路径：
**Docker Compose 部署**（推荐，接近生产环境）和 **本地开发运行**（不装 Docker，
逐个进程手动起，方便调试）。README.md 里的"快速开始"是精简版，本文档是详细版。

> 在开始之前请先读 README.md 里的「验证状态」一节：本项目对接的是 i茅台 App 的
> 私有接口（逆向来自 [oddfar/campus-imaotai](https://github.com/oddfar/campus-imaotai)），
> 数据库/调度/并发这些"系统骨架"部分已经过实测，但发验证码/登录/申购这几个真正打
> i茅台后端的调用**没有用真实账号验证过**——本说明里专门有一步用来验证这件事。

---

## 路径一：Docker Compose（推荐）

### 1. 准备 MySQL 和 Redis

`docker-compose.yml` 里 `api`/`scheduler` 两个容器要连接**外部**的 MySQL 和 Redis
（没有内置在 compose 里）。如果手头没有现成实例，最快的方式是本机再起两个独立容器：

```bash
docker run -d --name imaotai-mysql \
  -e MYSQL_ROOT_PASSWORD=root_pw \
  -e MYSQL_DATABASE=imaotai \
  -e MYSQL_USER=imaotai \
  -e MYSQL_PASSWORD=imaotai_pw \
  -p 3306:3306 \
  mysql:8 --character-set-server=utf8mb4

docker run -d --name imaotai-redis -p 6379:6379 redis:7
```

`MYSQL_HOST`/`REDIS_HOST` 后面会填 `host.docker.internal`（Mac/Windows Docker Desktop）
或宿主机的局域网 IP（Linux 上 `host.docker.internal` 需要 Docker 20.10+ 并在
compose 里加 `extra_hosts: ["host.docker.internal:host-gateway"]`，或者直接用
宿主机 IP／把 mysql/redis 容器加进同一个 Docker network 用容器名访问）。

### 2. 克隆仓库并配置环境变量

```bash
git clone https://github.com/Paul30028/imaotai_watcher
cd imaotai_watcher
cp .env.example .env
```

编辑 `.env`（对应上一步起的容器为例）：

```env
JWT_SECRET=换成一个随机字符串，比如 openssl rand -hex 32 的输出
ADMIN_USERNAME=admin
ADMIN_PASSWORD=换成你自己的管理员密码

MYSQL_HOST=host.docker.internal
MYSQL_PORT=3306
MYSQL_DATABASE=imaotai
MYSQL_USER=imaotai
MYSQL_PASSWORD=imaotai_pw

REDIS_HOST=host.docker.internal
REDIS_PORT=6379
REDIS_PASSWORD=

LOG_LEVEL=INFO
```

### 3. 启动

```bash
docker-compose up -d --build
docker-compose ps        # 确认 api / scheduler / frontend 三个都是 Up
docker-compose logs -f api        # 看到 "Database ready." 说明建表成功
```

### 4. 打开浏览器

访问 `http://localhost`（或服务器 IP），用 `.env` 里的 `ADMIN_USERNAME`/`ADMIN_PASSWORD`
登录。

---

## 路径二：本地开发运行（不用 Docker）

适合改代码时快速验证，也是我在提交这份代码前实际跑通的方式。

### 后端

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate   # 可选，建议用虚拟环境
pip install -r requirements.txt

export jwt_secret=devsecret
export admin_username=admin
export admin_password=你的密码
export mysql_host=localhost
export mysql_database=imaotai
export mysql_user=imaotai
export mysql_password=你的密码
export redis_host=localhost

# 首次启动 uvicorn 会自动建表+建管理员账号，也可以单独手动跑一次：
python init_db.py

# 终端 1：启动 API
uvicorn main:app --reload --port 8000

# 终端 2：启动调度器（申购/刷新/结果查询的定时任务都在这里跑）
python scheduler/main.py
```

后端本地跑要求本机已有可连接的 MySQL/Redis（同路径一第 1 步，端口映射到
`localhost` 而不是 `host.docker.internal` 即可）。

### 前端

```bash
cd frontend
npm install
npm run dev     # 默认 http://localhost:5173，自动把 /api/ 代理到 localhost:8000
```

浏览器打开 `http://localhost:5173` 即可看到管理界面，走的是本地启动的 API。

---

## 启动后验证清单

按顺序做，每一步都能独立确认系统这一层没问题：

1. **健康检查**
   ```bash
   curl http://localhost:8000/api/health   # 本地开发直连 api，或 Docker 路径下换成 http://localhost:80/api/health（走 nginx）
   # {"status":"ok"}
   ```
2. **管理员登录**：浏览器打开前端地址，用 `.env`/环境变量里配置的账号密码登录，
   能进入仪表盘即说明 JWT 鉴权 + 数据库都正常。
3. **添加一个 i茅台账号**（账号管理页）：填手机号 + 省市 + 经纬度，点"添加账号"
   后会自动发送短信验证码——**这一步是本项目里唯一没被我实测过的环节**，如果
   这里报错，看 `docker-compose logs api`（或本地 uvicorn 的终端输出），把报错
   贴出来，多半是 i茅台接口细节变了，需要针对性排查（不是配置问题）。
4. **收到验证码后完成登录**：输入验证码提交，成功后账号状态应变成"正常"。
5. **等一次早晨的刷新任务**（07:10/07:55/08:10/08:55 任一点），或手动触发一次：
   ```bash
   docker-compose exec scheduler python -c "from core.imaotai_api import refresh_catalogue_cache; refresh_catalogue_cache()"
   # 本地开发环境等价命令：cd backend && python -c "..."（需要先 export 好环境变量）
   ```
   然后去商品配置页确认"今日在售商品"下拉框里有数据。
6. **配置商品 + 手动触发一次申购**（系统设置页"立即申购"按钮），去申购日志页
   确认有 success/fail 记录写入，并检查是否收到 Server酱 通知（需要先在系统设置
   页填好 SendKey）。
7. **调度器状态**：仪表盘/系统设置页应显示调度器"运行中"（基于 Redis 心跳，
   若显示"已停止"，说明 `scheduler` 容器/进程没起来或连不上 Redis）。

全部走通后，系统就是完整可用的；剩下唯一需要"等明天 9 点"才能最终确认的是
真实预约窗口内的自动触发是否按预期命中——可以先看账号管理页"今日申购分钟"列
确认已经分配了分钟数，第二天到点后回来看申购日志即可。

---

## 常见问题速查

| 现象 | 原因 / 处理 |
|------|------|
| `docker-compose up` 后 api 容器一直重启 | 看 `docker-compose logs api`；十有八九是连不上 MySQL/Redis，检查 `.env` 里的 HOST 是否能从容器内访问到 |
| 浏览器登录一直 401 | 确认 `.env` 的 `ADMIN_USERNAME`/`ADMIN_PASSWORD` 和输入的完全一致；已建过管理员账号后再改 `.env` 密码不会生效，需要去数据库改或重建库 |
| 调度器状态显示"已停止" | `docker-compose logs scheduler`；Redis 心跳 60 秒过期，多半是 scheduler 进程崩了或连不上 Redis |
| 发验证码/登录报错 | 见上方验证清单第 3 步；把具体报错内容发出来定位 |
| 商品下拉框是空的 | 需要先跑过一次早晨刷新（见上方验证清单第 5 步），或手动触发 `refresh_catalogue_cache()` |
| 时区/申购时间不对 | 已在 `backend/scheduler/main.py` 里把所有定时任务显式锁定为北京时间（UTC+8），
与容器系统时区无关，如果观察到时间不对，先确认没有改动过这部分代码 |

---

## 生产部署建议

- **备份**：`accounts` 表里的 `token`/`cookie` 是登录凭证，`purchase_logs` 是历史记录，
  按你的 MySQL 实例正常备份策略处理即可，这两张表没有特殊要求。
- **日志**：`docker-compose logs -f api scheduler` 或对应容器的日志驱动，`LOG_LEVEL`
  可以调到 `DEBUG` 排查问题、平时建议 `INFO`。
- **多账号规模**：并发申购用线程池（`max_workers=min(账号数, 5)`），账号数很多时
  申购窗口内的整体耗时会更长，必要时可以调大 `backend/core/purchase.py` 里的
  `max_workers` 上限。
- **接口维护**：i茅台官方 App 更新可能导致接口路径/请求头/AES 密钥变化，出现大面积
  申购失败时先去查 `purchase_logs` 里的 `message` 字段，看错误信息是不是"接口返回
  非预期结构"这类特征，再对照最新抓包结果更新 `backend/core/imaotai_api.py`。
