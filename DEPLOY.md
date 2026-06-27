# 部署到 uchat.sohoclouds.com

Docker Compose 单域名部署。所有流量走 `https://uchat.sohoclouds.com`,Nginx 按路径反代到后端。

```
https://uchat.sohoclouds.com (443/TLS, Nginx 容器唯一对外)
  /                → 前端 dist 静态 (SPA)
  /api  /media     → 反代 backend:1081
  /ws              → 反代 backend:1081 (WebSocket 升级)
backend (FastAPI, uvicorn 单 worker, 内网 1081)
mysql:8 (内网 3306)
qdrant (独立向量服务, 内网 6333/6334)
持久卷: data/mysql  data/qdrant  uploads  data/letsencrypt
```

产物清单(已随仓库提供):
- `Dockerfile` / `.dockerignore` — 后端镜像
- `docker-compose.yml` — mysql + qdrant + backend + nginx
- `nginx/uchat.conf` — 单域名反代
- `.env.production.example` — 后端环境变量模板
- `frontend/.env.production` — 前端构建指向同域

---

## 向量服务

RAG 知识库和 Mem0 记忆都连接独立 `qdrant` 容器(`QDRANT_URL=http://qdrant:6333`),不再使用后端进程内嵌 RocksDB 文件库。
因此不会再因为 `qdrant_data` / `memory_db` 文件锁限制后端多进程或多副本。后端 worker 数由 `.env.production` 的 `WEB_CONCURRENCY` 控制,默认 2。
两个业务通过不同 collection 隔离:
- RAG 知识库:`col_{org_id}_{kb_id}`
- Mem0 记忆:`saas_visitor_memories`

---

## 首次上线

### 0. 前置
- `uchat.sohoclouds.com` 的 **A 记录已指向服务器公网 IP**(certbot 签证书前必须生效)。
- 服务器装好 Docker + compose 插件:`docker --version && docker compose version`。

### 1. 拉代码 + 配置
```bash
git clone <repo> && cd zcs
cp .env.production.example .env.production
# 编辑 .env.production:
#   - MYSQL_ROOT_PASSWORD 与 DATABASE_URL 里的密码填成【同一个】强密码
#   - 生产 LLM key、随机 JWT_SECRET (openssl rand -hex 32)
```
配置只有 `.env.production` 一份(单一真相源):
- backend 容器把它挂成 `/app/.env`,由 pydantic 读取(正确剥引号);
- compose 用 `--env-file .env.production` 读 `MYSQL_ROOT_PASSWORD` 给 mysql 容器。

无需再单独 `export` 任何变量。

### 2. 构建前端
```bash
npm --prefix frontend install
npm --prefix frontend run build   # 产出 frontend/dist, 用 .env.production 注入 API base
```

### 3. 签 TLS 证书 (Let's Encrypt, 一次性)
先临时用 standalone 模式签(此时 80 端口需空闲):
```bash
mkdir -p data/letsencrypt data/certbot-www
docker run --rm -p 80:80 \
  -v "$PWD/data/letsencrypt:/etc/letsencrypt" \
  certbot/certbot certonly --standalone -d uchat.sohoclouds.com \
  --agree-tos -m you@example.com --no-eff-email
```
(续期:`docker run --rm -v .../letsencrypt:/etc/letsencrypt -v .../certbot-www:/var/www/certbot certbot/certbot renew` + `docker compose exec nginx nginx -s reload`,可挂 cron。)

### 4. 起服务
```bash
docker compose --env-file .env.production up -d --build
```
- mysql 首次启动自动执行 `database.sql` 建表。
- `docker compose ps` 四个容器应 healthy/up。

### 5. 初始化平台超管
```bash
curl -X POST https://uchat.sohoclouds.com/api/auth/bootstrap \
  -H 'Content-Type: application/json' \
  -d '{"secret":"<.env.production 里的 JWT_SECRET>","email":"admin@local","password":"<强密码>"}'
```
之后用该账号登录 `https://uchat.sohoclouds.com`。

---

## 日常运维

```bash
# 提示: 凡涉及 (重)创建容器的命令都带 --env-file .env.production, 让 compose 拿到 MYSQL_ROOT_PASSWORD
docker compose logs -f backend                                   # 看后端日志
docker compose --env-file .env.production up -d --build backend  # 重新部署后端 (改代码后)
npm --prefix frontend run build && docker compose restart nginx  # 重新部署前端
docker compose down                                              # 停 (数据在 ./data 与 ./uploads, 不丢)
```
备份:定期备份 `./data/mysql`、`./data/qdrant`、`./uploads`。

---

## 验证清单

1. `docker compose ps` 四容器健康;`docker compose logs backend` 无 Qdrant / DB 连接错误。
2. 浏览器开 `https://uchat.sohoclouds.com` → 登录 → 四角色 dashboard 正常;刷新子路由(如 `/org/sessions`)不 404(SPA 回退生效)。
3. 上传:后台发图片 → DB `content_type=image`;`https://uchat.sohoclouds.com/media/xxx` 能打开。
4. WS:访客 widget 发消息收到 AI 回复;接管后坐席发文字/图片能下发。
5. `docker compose restart backend` 后:Mem0 记忆/向量/上传文件仍在(卷持久化)。
6. TLS:浏览器锁标正常,无 mixed-content。

---

## 访客 Widget 接入

`test.html/*.html` 是**本地测试页**(硬编码测试 ID + `127.0.0.1:1081`),**不要直接当生产 widget**。
生产嵌入页需用:
- WebSocket:`wss://uchat.sohoclouds.com/ws/{activity_id}/{visitor_uid}`
- 媒体地址:后端已通过 `PUBLIC_BASE_URL` 下发 `https://uchat.sohoclouds.com/media/...` 的绝对地址,widget 直接渲染即可。
把这两个地址告知前端接入方 / 第三方页面。

---

## 安全提醒
- `.env`、`.env.production` **不要进 git**(`.dockerignore` 已排除入镜像)。
- 仓库历史里的 `.env` 含明文 DB 密码与 LLM key,**生产务必换新值**。
- MySQL 仅容器内网可达(compose 未对外映射 3306)。
