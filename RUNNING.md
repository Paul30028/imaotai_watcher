# 运行说明

本文档是从零开始把 imaotai_watcher 跑起来的完整步骤，覆盖三条路径：
**Docker 部署**（推荐，一条命令，接近生产环境）、**本地开发运行**（不装 Docker，
前后端分开跑，方便改代码时快速看效果）和 **GitHub Actions**（申购请求从 GitHub
的云端服务器发出，不受你本地网络 IP 限流影响，见下方路径三）。README.md 里
的"快速开始"是精简版，本文档是详细版。

> 在开始之前请先读 README.md 里的「验证状态」一节：本项目对接的是 i茅台 App 的
> 私有接口（逆向来自 [oddfar/campus-imaotai](https://github.com/oddfar/campus-imaotai)），
> 数据库/调度/前端托管这些"系统骨架"部分已经过实测，但发验证码/登录/申购这几个真正打
> i茅台后端的调用**没有用真实账号验证过**——本说明里专门有一步用来验证这件事。

这个版本不需要 MySQL、Redis 或任何其他外部服务：数据库是一个 SQLite 文件，
调度器是 API 进程里的一个后台线程，前端编译产物由同一个进程直接提供。

---

## 路径一：Docker（推荐）

### 1. 克隆仓库并配置环境变量

```bash
git clone https://github.com/Paul30028/imaotai_watcher
cd imaotai_watcher
cp .env.example .env
```

编辑 `.env`，至少改这两项：

```env
JWT_SECRET=换成一个随机字符串，比如 openssl rand -hex 32 的输出
ADMIN_PASSWORD=换成你自己的管理员密码
```

### 2. 启动

用 docker-compose（会自动处理数据持久化的 volume）：

```bash
docker-compose up -d --build
docker-compose logs -f    # 看到 "Database ready." 和 "Uvicorn running" 说明起来了
```

或者不用 compose，直接 docker 命令也行：

```bash
docker build -t imaotai-watcher .
docker run -d --name imaotai-watcher \
  -p 8000:8000 \
  --env-file .env \
  -v imaotai-data:/app/data \
  --restart unless-stopped \
  imaotai-watcher
```

### 3. 打开浏览器

访问 `http://localhost:8000`（或服务器 IP:8000），用 `.env` 里的
`ADMIN_USERNAME`/`ADMIN_PASSWORD` 登录。

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
# database_url 不用设，默认会在 backend/data/imaotai.db 自动创建

# 启动 API（首次启动会自动建表 + 建管理员账号 + 启动调度器）
uvicorn main:app --reload --port 8000
```

不需要预先起任何数据库或 Redis——SQLite 文件在第一次启动时自动创建。

### 前端

```bash
cd frontend
npm install
npm run dev     # 默认 http://localhost:5173，自动把 /api/ 代理到 localhost:8000
```

浏览器打开 `http://localhost:5173` 即可看到管理界面，走的是本地启动的 API。

> 本地开发模式下前后端是两个独立进程；只有构建 Docker 镜像时，`frontend/dist`
> 才会被打包进后端镜像的 `static/` 目录，由同一个 uvicorn 进程直接提供
> （`backend/main.py` 里挂载 `/assets` 静态资源 + 一个 SPA fallback 路由，让
> `/accounts` 这类 React Router 客户端路由也能直接刷新访问）。

---

## 路径三：GitHub Actions（绕开本地 IP 限流）

**这条路径解决的是一个具体问题**：Docker/本地开发这两条路径，每次请求都是从
你的电脑/服务器所在网络发出的。如果这个 IP 被 i茅台后端限流了（实测现象：
连续测试一整天后，哪怕换了从未用过的手机号，发验证码依然稳定返回
`429 Too Many Requests`），**同一网络下的所有账号都会被卡住，跟代码对不对
没关系**。GitHub Actions 每次运行用的都是 GitHub 数据中心的 IP，跟你本地网络
无关，天然绕开这个问题（做法参考了 [397179459/iMaoTai-reserve](https://github.com/397179459/iMaoTai-reserve)，
一个用同样方式定时运行、有 480+ star 的开源项目）。

**这条路径不需要也不使用 Docker 里的那个数据库**——账号信息通过 GitHub 仓库的
Secrets 传进去。登录这一步（手机号 → 收验证码 → 换 token）仍然要通过路径一/二
跑起来的 Web 界面完成一次，因为发短信这类交互式操作没法在 Actions 里做。

### 1. 照旧用 Docker/本地开发把账号跑起来

按路径一或路径二的步骤，把系统跑起来，添加账号、收验证码、完成登录，并在商品
配置页选好要申购的商品。这一步跟不用 GitHub Actions 时完全一样，界面操作，不用
碰数据库。

### 2. 点一下按钮，把配置复制出来

登录成功后，去「账号管理」页，点右上角 **「复制 GitHub Actions 配置」**——会自动
把所有已登录账号的 `device_id`/`token`/`user_id`/门店/商品配置打包成一段 JSON，
直接复制到剪贴板了（不用去数据库里找，也不用手写 JSON）。

### 3. 粘贴进 GitHub 仓库的 Secrets

进入仓库 `Settings → Secrets and variables → Actions → New repository secret`：

- **`IMAOTAI_ACCOUNTS`**（必填）：Name 填 `IMAOTAI_ACCOUNTS`，Value 直接粘贴刚才
  复制的内容，保存。
- **`SERVERCHAN_KEY`**（选填）：Server 酱的 SendKey，配了就会在每次运行结束后
  推送一条微信通知（成功/失败个数 + 每个商品的结果）。不配的话结果只能在
  Actions 的运行日志里看。

> 之后账号信息有变化（比如加了新账号、token 刷新了、改了申购商品），回账号管理页
> 重新点一次「复制 GitHub Actions 配置」，把 `IMAOTAI_ACCOUNTS` 这个 Secret 的内容
> 覆盖更新一下就行。

### 4. 确认定时任务已启用

workflow 文件在 `.github/workflows/reserve.yml`，默认在北京时间 8:58 和 9:05
各跑一次（申购窗口是 9:00-9:59，排两次是因为 GitHub 的 schedule 触发在高峰期
可能延迟几分钟）。首次把 workflow 文件推送到默认分支后，去仓库的 `Actions`
标签页确认它出现在左侧列表里、状态不是灰色的"disabled"。

### 5. 手动跑一次验证

不用等到明天 9 点——去 `Actions → i茅台申购（GitHub Actions 版）→ Run workflow`
手动触发一次，几秒后刷新页面看运行日志，确认 `IMAOTAI_ACCOUNTS` 解析没报错、
`reserve_item` 的返回结果符合预期（这一步同时也验证了 Secrets 填对了没有）。

> 这条路径和 Docker/本地开发路径是可以同时用的：Web 界面继续用来管理账号、
> 收验证码、看历史日志；真正在 9 点发出申购请求的，换成从 GitHub Actions 发出。
> 如果之后账号 token 过期了（大概一个月一次），照样要回到 Web 界面重新登录一次，
> 再把新的 token 更新进 `IMAOTAI_ACCOUNTS` 这个 Secret。

---

## 启动后验证清单

按顺序做，每一步都能独立确认系统这一层没问题：

1. **健康检查**
   ```bash
   curl http://localhost:8000/api/health
   # {"status":"ok"}
   ```
2. **管理员登录**：浏览器打开 `http://localhost:8000`（Docker 路径）或
   `http://localhost:5173`（本地开发），用配置的账号密码登录，能进入仪表盘
   即说明 JWT 鉴权 + 数据库都正常。
3. **添加一个 i茅台账号**（账号管理页）：填手机号 + 省市 + 经纬度，点"添加账号"
   后会自动发送短信验证码——**这一步是本项目里唯一没被我实测过的环节**，如果
   这里报错，看容器日志（`docker-compose logs -f`，本地开发看 uvicorn 的终端
   输出），把报错贴出来，多半是 i茅台接口细节变了，需要针对性排查（不是配置
   问题）。
4. **收到验证码后完成登录**：输入验证码提交，成功后账号状态应变成"正常"。
5. **等一次早晨的刷新任务**（07:10/07:55/08:10/08:55 任一点），或手动触发一次：
   ```bash
   docker-compose exec app python -c "from core.imaotai_api import refresh_catalogue_cache; refresh_catalogue_cache()"
   # 本地开发环境等价命令：cd backend && python -c "..."（需要先 export 好环境变量）
   ```
   然后去商品配置页确认"今日在售商品"下拉框里有数据。
6. **配置商品 + 手动触发一次申购**（系统设置页"立即申购"按钮），去申购日志页
   确认有 success/fail 记录写入，并检查是否收到 Server酱 通知（需要先在系统设置
   页填好 SendKey）。
7. **调度器状态**：仪表盘/系统设置页应显示调度器"运行中"——调度器现在是应用
   内的后台线程，只要 API 进程活着它就活着，这一步基本上只是确认进程没崩。

全部走通后，系统就是完整可用的；剩下唯一需要"等明天 9 点"才能最终确认的是
真实预约窗口内的自动触发是否按预期命中——可以先看账号管理页"今日申购分钟"列
确认已经分配了分钟数，第二天到点后回来看申购日志即可。

---

## 常见问题速查

| 现象 | 原因 / 处理 |
|------|------|
| 容器起不来 / 一直重启 | `docker-compose logs -f` 看具体报错；检查 `.env` 里 `JWT_SECRET`/`ADMIN_PASSWORD` 是否都填了（这两个是必填项，没填会在启动时直接报 pydantic 校验错误退出） |
| 浏览器登录一直 401 | 确认 `.env` 的 `ADMIN_USERNAME`/`ADMIN_PASSWORD` 和输入的完全一致；已建过管理员账号后再改 `.env` 密码不会生效（管理员账号只在数据库里没有时才会自动创建一次），需要去 SQLite 文件里改或删掉 volume 重新初始化 |
| 发验证码/登录报错 | 见上方验证清单第 3 步；把具体报错内容发出来定位 |
| 发验证码稳定返回 `429 Too Many Requests`，换手机号也一样 | 大概率是这个网络的出口 IP 被限流了，跟账号/代码无关。换个网络（比如手机热点）再试一次能确认；长期方案见上方「路径三：GitHub Actions」，用 GitHub 的云端 IP 绕开本地限流 |
| 商品下拉框是空的 | 需要先跑过一次早晨刷新（见上方验证清单第 5 步），或手动触发 `refresh_catalogue_cache()` |
| 数据重启后丢了 | 用 `docker run` 时忘了挂 `-v imaotai-data:/app/data`；不挂 volume 的话容器删掉数据就没了 |
| 时区/申购时间不对 | 所有定时任务都在 `backend/scheduler/main.py` 里显式锁定为北京时间（UTC+8），与容器系统时区无关，如果观察到时间不对，先确认没有改动过这部分代码 |

---

## 生产部署建议

- **备份**：只有一个文件需要备份——`backend/data/imaotai.db`（或者对应的
  Docker volume `imaotai-data`）。里面存了账号 token/cookie（登录凭证）和历史
  申购记录，按你平时对单文件数据库的备份习惯处理即可（定期复制这个文件，
  或者用 `docker run --rm -v imaotai-data:/data -v $(pwd):/backup alpine tar czf /backup/imaotai-data.tar.gz -C /data .` 这类命令打包）。
- **日志**：`docker-compose logs -f` 或对应容器的日志驱动。
- **多账号规模**：并发申购用线程池（`max_workers=min(账号数, 5)`），账号数很多时
  申购窗口内的整体耗时会更长，必要时可以调大 `backend/core/purchase.py` 里的
  `max_workers` 上限。SQLite 对这种"一个本地应用、几个到几十个账号"的规模完全
  够用；如果哪天账号规模大到需要真正的并发写入型数据库，再考虑把
  `DATABASE_URL` 换成 PostgreSQL 之类的（SQLAlchemy 层已经是数据库无关的写法）。
- **接口维护**：i茅台官方 App 更新可能导致接口路径/请求头/AES 密钥变化，出现大面积
  申购失败时先去查申购日志里的 `message` 字段，看错误信息是不是"接口返回
  非预期结构"这类特征，再对照最新抓包结果更新 `backend/core/imaotai_api.py`。
