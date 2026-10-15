# ACP-lite (Agent Connect Personal)

[English](README-EN.md) | **简体中文**

跨主机 Agent 互联的**最小实现**：一台机器一个"邮局"，Agent 仍然只读写本地文件。
两台 NAT 后的普通电脑，不要公网、不要服务器。

![ACP-lite 六智能体舰队拓扑](assets/acp-lite-topology.svg)

> 命名：**ACP-lite = Agent Connect Personal**。最后一个 P，**最终希望能写成 Peace**。
> 图里是一个示例舰队（两台主机、每台两个 agent），换成你自己的名字即可；图中的
> **蓝莓(Hermes)**、**蛋糕(OpenClaw)**、**绒毛(Muse)** 三个代号，是**我女儿起的**。😄
>
> **不混淆声明**：本项目与 Zed 的 *Agent Client Protocol*、OpenAI+Stripe 的
> *Agentic Commerce Protocol*、IBM 已归档的 *Agent Communication Protocol*
> **没有任何关系**。对外引用时请带上全称 "ACP-lite (Agent Connect Personal)"。

**怎么读**：本文是操作手册 —— 命令可直接照抄，`<home-dir>` / `<shared-dir>` / `<agent>` / `<对方agent>` 是占位符。
上手四步在 §一，命令速查在 §二，**出问题先查 §四（那 8 条 FAQ 都是我们真踩过的坑）**；
原理 / 横向对比 / 归属声明 / 边界在 §六 ~ §十（给想了解的人，照着用不必读）。
程序版本 = 协议版本 = **0.6.2**；信封格式以 `ENVELOPE-FORMAT.md` 为准。

## 一、安装与初始化（两台机器各做一遍）

```bash
# 1. Python 依赖。不装也能启动，但跨机消息一律拒收（fail-closed，见铁律 5）→ 实际部署当必装
pip install cryptography

# 2. 装 Syncthing（官方开源、无账号、无中心云）：两台机器互相添加对方 Device ID
#    同步目录自选（下称 <shared-dir>）；把仓库里的 .stignore 放进该目录根

# 3. 初始化身份。--home 是本机私有目录（含私钥，绝不进同步目录）；
#    --root 是 Syncthing 同步的那个目录
python acp.py --home <home-dir> --root <shared-dir> init --agent <agent> --display "Codex@台式机"

# 4. 带外核对指纹（必须"带外"：当面 / 口头，不能靠网络）
python acp.py --home <home-dir> --root <shared-dir> status     # 打印本机指纹
python acp.py --home <home-dir> --root <shared-dir> trust --agent <对方agent> --fingerprint xxxx-xxxx-xxxx-xxxx

# 5. 常驻投递（只搬文件、不调模型，挂机不烧 token）
python acp.py --home <home-dir> --root <shared-dir> watch --loop --interval 3
```

占位符按平台替换：Windows 例如 `--home D:\acp-home --root D:\acp-shared`；
Linux / macOS 例如 `--home ~/acp-home --root ~/acp-shared`。三条必守：

- **`--root` 不能省**：省了会默认写 `<home>/shared`，**退出码 0、看着像成功**，信却落在本机私有目录（FAQ ③）。
- **agent 名要跨机唯一**：两台机器不能都叫 `codex`（会覆盖名片、挤进同一个发件箱）。
- **`.stignore` 放进同步目录根**：挡掉 `~syncthing~*` / `*.tmp`，以及冲突副本 `*.sync-conflict-*`（结尾也是 `.json`，不挡会被当成信件扫到）。

### 可选：跨机唤醒通道（SSH 服务端）

本项目**不内置**唤醒通道（`watch` 永不调模型），但**已实测可用 SSH 直连唤醒**（2026-10-14 / 10-15，5 次闭环全过）。
被唤醒的那台机器装 OpenSSH 服务端即可，22 端口只对本网段开：

```powershell
# Windows（需管理员）
Add-WindowsCapability -Online -Name OpenSSH.Server~~~~0.0.1.0
Set-Service sshd -StartupType Automatic; Start-Service sshd
New-NetFirewallRule -Name OpenSSH-Server-In-TCP-LAN -DisplayName 'OpenSSH Server (LAN only)' `
  -Enabled True -Direction Inbound -Protocol TCP -Action Allow -LocalPort 22 -RemoteAddress 192.168.0.0/24
```

```bash
# Linux / macOS
sudo apt install openssh-server        # macOS 已自带 OpenSSH
```

唤醒命令（提示词**走文件 + stdin**，中文和特殊字符都不会被 shell 弄坏）：

```cmd
rem 唤醒 Codex（沙箱档位必须让目标目录可写 —— 见 FAQ ⑦）
codex exec -s workspace-write --skip-git-repo-check -C D:\_wake ^
  --add-dir D:\SharedFiles --add-dir D:\ACP-Shared --add-dir D:\LLM\ACP-lite\home ^
  - < 提示词.txt
```

```cmd
rem 唤醒 DSH（档位环境变量必须与 dsh 同进程 —— 见 FAQ ⑤）
set "DSH_PERMISSION_MODE=danger-full-access"
cd /d D:\LLM\ACP-lite\_dsh-wake
dsh --profile headless - < 提示词.txt
```

```bash
# 同机两个 agent 也能双向 CLI 互调（换成你自己的 CLI 同理）
openclaw agent --message "只回答两个字：收到"   # 蓝莓(Hermes) → 蛋糕(OpenClaw)
hermes -z "只回答两个字：收到"                  # 蛋糕 → 蓝莓（反向同样成立）
```

唤醒只递"**指针**"（收信文件的绝对路径，里面才有 `msg_id`），正文仍让对方自己回信箱读 ——
**ACP 是账本，CLI 是门铃；门铃不能替代账本**。判据**别看退出码**：`exit 0` 既可能"真干完了"、
也可能"只说不做"，要落在**产物落盘 + 审计链增长 + 签名回执**这三样上。

## 二、命令速查

下表命令都带 `--home <home-dir> --root <shared-dir>`（用 `acp.py ...` 省略）。

| 命令 | 作用 |
|---|---|
| `acp.py ... status` | 看身份 / 信任 / 收件箱 / 刹车状态，打印本机指纹 |
| `acp.py ... send --to <对方agent> --text "..."` | 投递一条；`--to '*'` = 广播；`--reply none` = 不用回（默认 `auto`） |
| `acp.py ... send --reply-to <msg_id> ...` | 回信（自动 `hops+1`） |
| `acp.py ... inbox` | 列出收件箱 |
| `acp.py ... ready` | 只列**真正可执行**的消息（受 STOP 与放行票约束） |
| `acp.py ... digest` | 把待处理消息压成一屏 —— **省 token 的收信方式** |
| `acp.py ... ack <msg_id>` | 确认已处理（消耗放行票） |
| `acp.py ... watch --loop --interval 3` | 常驻投递（永不调模型） |
| `acp.py ... audit` | 校验并查看哈希链审计 |
| `python selftest.py` | 离线跑一整套自测（闸门 / 刹车 / 伪造放行票 / 坏消息隔离），不需要网络 |

## 三、出口闸门（安全的核心）

| 动作 `--requires` | 谁能做 |
|---|---|
| `none` / `read` | 自动可做 |
| `write` / `send` / `pay` / `delete` | **必须由人签一张一次性放行票** |

```bash
python acp.py ... userkey                 # 建 L2 人密钥（口令加密，只存本机，只你有口令）
python acp.py ... approve <msg_id>        # 人工放行：需要输入口令
python acp.py ... stop                    # 刹车：一切出口动作立即停止（收信不受影响）
python acp.py ... stop --off              # 解除
```

- **agent 拿不到口令 ⇒ 无法自签放行票**：这是"被注入的 agent 不能自己给自己批条子"的落地方式。
  票**必须由 L2 人密钥签名**，`ack` 时验签；绑定"消息 ID + 动作摘要 + 有效期"，改过即失效、用一次即作废、重放无效 —— agent 自己写一个 `approved-*.json` 文件不管用。
- 语义上不允许"推理动作去付款"：`requires` 非 `none` 时 `action` 必须是 `exec`，否则 `send` 直接报错。
- **`STOP` 是一个文件**：文件系统在，刹车就有效，不依赖模型、不依赖网络；**刹车期间 `ack` 一律拒绝**。

## 四、常见问题（FAQ：都是我们真踩过的坑）

**Q1: DSH 被唤醒后"手脚被捆"，报 `SetNamedSecurityInfoW failed Win32 5`？**
A: 光设 `DSH_PERMISSION_MODE=danger-full-access` **不够**，还要一个**干净的工作目录**：脏目录的 ACL 授不了权
（`grantWrite(<目录>)` 被拒，Win32 5 = 拒绝访问），命令在**沙箱准备阶段就起不来**。换个干净目录再唤醒即可
（我们把 DSH 的 cwd 专设成 `D:\LLM\ACP-lite\_dsh-wake`）。这条**不是稳定复现**，别当"必挂"宣传。

**Q2: DSH 有 `--add-dir` 吗？**
A: **没有。** DSH 的可写根写死为"工作区 + `/tmp` + 系统临时目录"，没有扩展入口，只能**整机放权**
（`DSH_PERMISSION_MODE=danger-full-access`）或抬高 cwd。Codex 有 `--add-dir`，要写成
`-s workspace-write --add-dir X --add-dir Y`。

**Q3: `acp.py --root` 能省吗？**
A: **不能省。** 省略时默认写 `<home>/shared`（不是群共享目录），**退出码 0、没有任何报错**，信却落在
本机私有目录、群里谁也看不见。发信 / 回信一律显式写 `--root <shared-dir>`；判据 = `outbox/<收件 agent>/` 里真有文件。

**Q4: 中文正文 / 中文提示词怎么传？**
A: **别走命令行参数**（`cmd` / PowerShell 把 UTF-8 当 GBK 读，收到形如 `鎶婅繖鍙ヨ瘽…` 的乱码；非交互 SSH
还会重排分词）。**走文件 + stdin**：正文先写成 UTF-8 文件，用 `- < 提示词.txt` 交给被唤醒的 CLI；发中文信时
也在**同一个 Python 进程**里读文件再调 `acp.main([...])`，别让中文经过 shell。

**Q5: 档位之类的环境变量怎么传给被唤醒的 CLI？**
A: **只用单进程 `set`**：`set "DSH_PERMISSION_MODE=danger-full-access"` 紧跟着 `dsh …`（同一条 `.cmd`、
同一个进程）。**别用 `cmd /c "set X=Y && dsh"` 链式** —— 档位传不下去，现象是**静默零落地**（不报错、不落盘）。

**Q6: 唤醒该用 `schtasks` 还是 SSH 前台？**
A: **短活用 SSH 前台，长活用计划任务**：`schtasks` 会弹控制台窗口、但**抗 SSH 断连**；SSH 前台不弹窗、
但**随会话断开**。`start /b` 起的后台任务会被 SSH 会话回收，别用。

**Q7: Codex 的沙箱档位怎么选？**
A: 只读任务 `-s read-only`；**要落盘 / 发信必须 `-s workspace-write`，并把每个目标目录 `--add-dir` 进去** ——
包括 **ACP home**（最容易漏），不给它写权就是"**信发了、账没记**"：信发出去了，但审计链 `audit.jsonl`
写不进去。启动横幅会打印实际可写根，可当硬证据。

**Q8: 桌面版开着，会不会影响 CLI 唤醒？**
A: **不影响**（实测）：桌面版与 CLI 唤醒是**各自独立的会话**，没有写权冲突（DSH 桌面版 5 个进程在跑时，
CLI 唤醒照样 18 秒跑完并写进工作区外）。例外只有"接管已有会话"：Codex 桌面客户端握着写权时
`resume` 会失败（`already has an active writer`）。

## 五、运维与部署注意

### 网络档位：默认 `auto`，别手动切

```bash
python acp_net.py --syncthing-home <syncthing-home> status      # 看档位 + 实际走哪条路
python acp_net.py --syncthing-home <syncthing-home> mode auto   # 默认档（旧叫法 wan）
python acp_net.py --syncthing-home <syncthing-home> mode strict # 严格档（旧叫法 lan）
python acp_net.py --syncthing-home <syncthing-home> kick       # 换网后立刻重连
# <syncthing-home> = Syncthing 配置目录（含 config.xml）：
#   Windows 例 %USERPROFILE%\acp-home\syncthing ｜ Linux/macOS 例 ~/.config/syncthing
```

- `auto` 档实测走局域网直连（`<对端局域网地址>:22000 isLocal=True`），中继只 `Joined relay` 待命 —— **公开服务器是"备胎"，不是"主路"**；`strict` 完全不登记地址，代价是跨网找不到对方。
- **换网后嫌慢，先 `kick`**：实测被动等约 **4 分 50 秒**，主动 `kick` 约 **2 秒**。

### 省 Token 账本

写消息文件 / Syncthing 同步 / `watch` 收信落盘 **都不耗 token**（`watch` 进程**零网络连接**，源码里没有任何 HTTP 客户端）；
**唯一耗点是"自动叫模型处理"，而本程序不提供这个动作**（`watch` 永远不调模型）。

```bash
python acp.py ... send --to dsh --text "这条只是通知" --reply none    # 不用回
python acp.py ... send --to dsh --text "请给个答复" --reply answer    # 需要回答
python acp.py ... digest                                             # 收方一次读完，代替逐条读
```

### 常驻与自检

- **开机自启**：跑 `watch --loop`（只搬文件，常驻几十 MB）。Windows 任务计划程序登录触发；Linux `systemd --user`（或 `crontab @reboot`）；macOS `launchd`。
- **审计 / 自测**：投递 / 放行 / 确认都进 `audit.jsonl` 哈希链，`acp.py audit` 校验全链是否被改动过；`python selftest.py` 用两个临时"机器"跑完整套流程（**项数以程序输出为准**）。

### 部署注意

| 事项 | 说明 |
|---|---|
| **时钟要同步（NTP）** | 两台机器时间差太大，`expires_at` 会误判（把新消息当过期） |
| **重建身份后要重新信任** | `init --force` 会换密钥 ⇒ 对方那边立刻变成 `untrusted`，需重新带外核对 |
| **指纹变了要当心** | `trust` 遇到"新指纹 ≠ 已记录指纹"会拦下来，确认无误后加 `--force` 才更新（防中间人换人） |
| **`peers/` 谁都能写** | 名片在共享目录里，任何同步方都能覆盖它（低危）。将来可上 TOFU（首见锁定指纹，变了告警） |
| **别在生产用 `ACP_USERKEY_PASSPHRASE`** | 那是给自测用的环境变量；生产请用交互式口令输入，避免口令被子进程继承 |

---

以下 §六 ~ §十是**给人看的**：想了解"为什么这么设计"才读，照着用可以跳过。

## 六、五条铁律

1. **同机不变**——原文件通道照旧；本程序不读不写 `mailbox/`。
2. **跨机只共享一个目录**——Syncthing / Tailscale / 网盘 / U 盘都能当传输层。
3. **私钥不进共享目录**——`--home` 是本机私有；共享目录里只有名片和发件箱。
4. **收信不调模型**——`watch` 只落盘 + 记审计，挂机不烧 token。
5. **缺依赖就拒收（fail-closed）**——本机没有 `cryptography` 时跨机消息**默认一律拒收**；
   自测要收只能显式加 `--allow-unsigned`，此时消息标记 `unverified` 且**永不进入 `ready`**。

## 七、跨机信封

`to` 的语义像**微信群 @ 人**：共享目录里的消息，房间里每个成员都看得见（文件就摆在那儿，
没有任何保密性），`to` 只决定**"谁被点名、谁该处理"**：

| `to` 的值 | 含义 | 其他成员 |
|---|---|---|
| `dsh-desktop` | 点对点：**只请 DSH 处理** | 看得见，但 `watch` 不投递、不执行（等同围观） |
| `*` | 广播：**请所有人处理/回应** | 正常投递，各自判定 |

所以本项目的"点对点"= **只点名不加密**，别往里放不该给别人看的东西（正文加密见 CHANGELOG 缺口清单）。
防刷屏靠 `hops`（默认 4 轮上限）与**自觉**：广播不是"必须人人回"。

| 规矩 | 字段 | 作用 |
|---|---|---|
| 单写者 | 目录 `outbox/<自己>/` | 谁都不会踩到别人的文件，Syncthing 不冲突 |
| 幂等 | `idem` | 投递层直接丢弃重复（邮件重发/同步抖动都安全） |
| 防回环 | `hops` / `max_hops` | 超上限直接拦，避免两边自动处理互相点火 |
| 过期即拒 | `expires_at` | 三天前的任务不会在你开机时突然自动执行 |

> `hops` 防的是**无限回环**，不是"多轮往返"：默认 `max_hops=4` 即允许 4 轮来回；
> 要严格"只回一封"就加 `--max-hops 1`。**单条坏消息不连坐同轮其它消息**（标 `rejected/malformed` 后跳过）。

字段级规范（`x` 段每个字段的含义、签名算法、`created_at` 等）见 `ENVELOPE-FORMAT.md`。
**手写的信封一律没有签名 → 一定被拒收**，别手写，用 `send`。

## 八、定位：和 MCP / A2A / 消息中间件的横向对比

| | ACP-lite | MCP | Google A2A | NATS / Redis PubSub |
|---|---|---|---|---|
| 解决的问题 | 跨主机 Agent 互发消息 | 模型调用外部工具 | Agent 之间标准化通信 | 通用实时消息 |
| 传输方式 | Syncthing 文件同步 | 本地 STDIO / HTTP | HTTP + JSON-RPC | TCP 长连接 |
| 要不要公网/服务器 | 不要 | 不要（本地） | 要（服务端点） | 要（broker） |
| NAT 后两台电脑 | 直接可用 | 不适用 | 需内网穿透 | 需内网穿透 |
| 消息签名/审计 | ed25519 + 哈希链 | 无（自行实现） | 视实现 | 无（自行实现） |
| 实时性 | 秒级 | 实时 | 实时 | 毫秒级 |
| 适用规模 | 个人/小团队 | 单机 Agent | 企业级 Agent 网 | 工程系统 |

> 定位句：**ACP-lite 是给"两台 NAT 后的普通电脑上的 Agent"用的最小通信方案；要企业级标准化走 A2A，要模型调工具走 MCP，要毫秒级走消息中间件。**

## 九、依赖与归属声明

- **通信层不是我们自研的**：跨主机通信**建立在 [Syncthing](https://github.com/syncthing/syncthing) 之上**
  （Syncthing 是由 Jakob Borg 与社区贡献者创建的开源连续文件同步工具，现由瑞典的非营利基金会
  Syncthing Foundation 与社区共同维护）。**同步层不是我们写的，我们不主张任何原创性** ——
  谨向 Syncthing 项目及其维护者致谢。我们加的只是一层**签名信封 + 哈希链审计**的薄脚本。
- **运行依赖**：Python 3.9+、`cryptography`、Syncthing（要跨机唤醒再加 OpenSSH，见 §一）。
- 本项目以 **MIT** 发布（见 `LICENSE`）；英文版归属声明见 [`ATTRIBUTION-EN.md`](ATTRIBUTION-EN.md)。

## 十、边界与免责（诚实说明）

- ⚠️ **正文落盘是明文**：Syncthing 的**传输**是端到端加密的（中继只看得到密文），但消息
  **落到共享目录里的文件是明文**。正文加密（X25519 + AES-GCM）落地前**不要用这条通道传敏感内容**。
- 同步目录的元数据对 Syncthing 中继可见；涉密请关公共中继、改用局域网或 Tailscale 内网。
- 本程序**不调用任何模型**，也不替你决定"要不要执行"；Agent 本身不可寻址，**可寻址的是机器**，身份由邮局代持。
- **能保证"送到"，不保证"叫醒"**：唤醒是外挂的门铃（同机 CLI 互调 / 跨机 SSH 唤醒，命令见 §一），
  **不是 ACP-lite 自带的**；对端没开机、或没挂 `watch` 时，你的信就只是在信箱里排队。
