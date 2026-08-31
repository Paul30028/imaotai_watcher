# 单容器构建：把 React 前端编译成静态文件，塞进 FastAPI 后端镜像里由同一个
# uvicorn 进程直接托管（backend/main.py 挂载 static/ 目录）。最终产物只有
# 一个容器、一个端口，不再需要 nginx 反代，也不需要外部 MySQL/Redis
# （数据库用容器内的 SQLite 文件，见 docker-compose.yml 的 volume）。

# ---- Stage 1: 编译前端 ----
FROM node:20-alpine AS frontend-builder
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# ---- Stage 2: 后端 + 打包好的前端静态文件 ----
FROM python:3.11-slim
WORKDIR /app

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ .
COPY --from=frontend-builder /app/frontend/dist ./static

# SQLite 数据文件默认写在这里（config.py: database_url=sqlite:///./data/imaotai.db），
# docker-compose.yml 把它挂成具名 volume，容器重建/更新镜像不会丢数据。
RUN mkdir -p /app/data

EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
