# Twitter DM Bot

通过飞书管理后台，自动在 Twitter/X 上给目标用户发送私信的机器人系统。

**适用场景**：Web3 项目方、KOL、Community Manager 批量触达目标用户。

---

## 系统架构

```
Dm/
├── backend/              — FastAPI 后端
│   ├── main.py           — 服务入口
│   ├── scheduler.py      — APScheduler 定时调度
│   ├── adspower.py       — AdsPower 指纹浏览器管理
│   ├── playwright_agent.py — Playwright 浏览器自动化发DM
│   ├── feishu.py         — 飞书数据源对接
│   ├── message_gen.py    — 私信模板生成
│   ├── database.py       — SQLite 数据库操作
│   ├── models.py         — 数据模型
│   └── config.py         — 配置加载
├── frontend/             — Vue3 控制台（Dashboard / Accounts / Targets / Templates / Exceptions）
├── start.sh              — 一键启动脚本
└── requirements.txt     — Python 依赖
```

---

## 快速开始

### 环境要求

- macOS / Linux
- Python 3.10+
- Node.js 18+（前端）
- [AdsPower](https://www.adspower.net/) 指纹浏览器（已登录账号）
- 飞书自建应用（获取 App ID / App Secret）

### 第一步：安装依赖

```bash
# 后端
pip install -r requirements.txt

# 前端
cd frontend && npm install && cd ..
```

### 第二步：配置环境变量

```bash
cp .env.example .env
```

然后编辑 `.env`，填入以下信息：

```env
# ===== 飞书配置 =====
FEISHU_APP_ID=cli_xxxxxxxxxxxxxx
FEISHU_APP_SECRET=xxxxxxxxxxxxxxxxxxxxxxxx
FEISHU_APP_TOKEN=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
FEISHU_TABLE_TARGETS=xxxxxxxxxxxxxxxx   # 目标用户表 ID
FEISHU_TABLE_ACCOUNTS=xxxxxxxxxxxxxxxx  # 账号池表 ID

# ===== AdsPower 配置 =====
ADSPOWER_HOST=http://local.adspower.net
ADSPOWER_PORT=50325

# ===== 运行参数 =====
DAILY_DM_LIMIT=5          # 单账号每日发送上限
MIN_INTERVAL_SEC=900      # 两条消息最小间隔（秒）
MAX_INTERVAL_SEC=2400    # 两条消息最大间隔（秒）
SYNC_INTERVAL_MIN=30      # 飞书同步间隔（分钟）
MAX_RETRY_ACCOUNTS_PER_TARGET=3  # 失败重试切换账号次数
TIMEZONE=Asia/Shanghai
```

#### 飞书表格准备

系统依赖两张飞书多维表格：

**1. 目标用户表**（字段要求）

| 字段名 | 类型 | 说明 |
|--------|------|------|
| `username` | 文本 | Twitter 用户名（不含 @） |
| `message` | 文本 | 自定义私信内容（可选，不填则用模板） |
| `status` | 单选 | `待发送` / `发送中` / `已发送` / `失败` |

**2. 账号池表**（字段要求）

| 字段名 | 类型 | 说明 |
|--------|------|------|
| `adspower_id` | 文本 | AdsPower 浏览器 ID |
| `status` | 单选 | `正常` / `异常` / `禁用` |
| `last_used` | 日期 | 最后使用时间（自动更新） |

### 第三步：启动

```bash
./start.sh
```

启动后访问：
- **前端控制台**：`http://localhost:3000`
- **后端 API**：`http://localhost:8000`

---

## 使用流程

### 日常使用步骤

1. 在飞书**目标用户表**新增记录，状态设为 `待发送`
2. 在飞书**账号池表**确保有状态为 `正常` 的账号
3. 在前端 Dashboard 点击 **启动**
4. 实时查看发送日志
5. 失败的目标可在 **Exceptions** 页面查看原因并手动重试

### 消息模板配置

在 **Templates** 页面管理私信模板，支持变量替换：

| 变量 | 说明 |
|------|------|
| `{{username}}` | 替换为目标 Twitter 用户名 |
| `{{date}}` | 替换为当天日期 |

---

## 发送链路

```
飞书目标表（待发送）
  → 后端拉取 → 排队调度
    → 申请一个正常状态的 AdsPower 浏览器
      → Playwright 打开 Twitter
        → 搜索目标用户
          → 进入私信对话
            → 发送消息
              → 回写飞书状态（已发送 / 失败）
```

### 失败类型说明

| 失败类型 | 含义 | 是否重试 |
|---------|------|---------|
| `blocked_verification` | 对方账号需验证，无法发送 | ❌ 不重试 |
| `cannot_dm` | 对方不接受私信 | ❌ 不重试 |
| `target_not_found` | 搜索不到该用户名 | ❌ 不重试 |
| `captcha` | 触发 Twitter 验证码风控 | ✅ 换账号重试 |
| `error` | 执行异常（网络超时等） | ✅ 换账号重试 |

---

## 生产部署建议（Mac Mini 本地）

1. **AdsPower**：常驻运行，保持所有账号为登录状态
2. **进程托管**：用 `launchd` 或 `pm2` 托管 `start.sh`
3. **每日巡检**：
   - 异常账号数量
   - `blocked_verification` 数量
   - 整体发送成功率
4. **数据备份**：
   - `backend/runtime.db`（发送记录）
   - `artifacts/screenshots/`（发送截图，生产环境可关闭截图功能）

---

## 安全注意事项

- **仅对已授权 / 白名单目标执行触达**，避免平台与合规风险
- **不要对外分享 `.env` 文件**，里面有飞书和账号的密钥
- 遇到验证码或身份验证提示时，**建议人工介入**，不要让机器人继续执行
- Twitter/X 对私信发送有严格限制，建议单账号每日发送量控制在 5-20 条以内

---

## 开发

```bash
# 验证语法
npm run lint  # 前端
python -m py_compile backend/*.py  # 后端

# 构建
cd frontend && npm run build
```

---

## License

MIT
