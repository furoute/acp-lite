# ACP-lite (Agent Connect Personal)

[English](README-EN.md) | **简体中文**

**把本仓库链接交给你的 coding agent，让它照着这份 README 装。** 这不是一个点一下就装好的 SaaS，
也**没有**一键安装包 —— 「人类出点子，AI 负责实现」：我们自己踩出来、调通的东西，写成了 agent 照着做就行的步骤。
你的 agent 读完本文，就能在你自己的两台机器上重新配一遍。

> 跨主机 Agent 互联的**最小实现**：一台机器一个「邮局」，Agent 仍然只读写本地文件。
> 两台 NAT 后的普通电脑，不要公网、不要服务器。

![ACP-lite 七智能体协作群拓扑](assets/acp-lite-topology.svg)

> 命名：**ACP-lite = Agent Connect Personal**。最后一个 P，**最终希望能写成 Peace**。
> 图里是一个示例协作群（两台主机、每台两个 agent），换成你自己的名字即可；图中的
> **蓝莓(Hermes)**、**蛋糕(OpenClaw)**、**绒毛(Muse)**、**小白(Grok Bot)** 四个代号，是**我女儿起的名字**。😄
>
> **不混淆声明**：本项目与 Zed 的 *Agent Client Protocol*、OpenAI+Stripe 的
> *Agentic Commerce Protocol*、IBM 已归档的 *Agent Communication Protocol*
> **没有任何关系**。对外引用时请带上全称 "ACP-lite (Agent Connect Personal)"。

**怎么读**：本文的**第一读者是 AI Agent** —— 正文按「做什么 → 照抄命令 → 判据」组织，每一步都能直接执行、就地验收；人类只需把仓库链接交给 agent。
遇到问题先查 **一、常见问题（FAQ）**（怎么连、怎么登、踩过哪些坑）；想了解"为什么这么设计"再看 **二、附录**，照着用可以一眼不看。
占位符：`<home-dir>` 本机**私有**目录 ｜ `<shared-dir>` 两台机**同步**的目录 ｜ `<agent>` / `<对方agent>` agent 名。
程序版本 = 协议版本 = **0.7.0**；信封格式以 `ENVELOPE-FORMAT.md` 为准。

---

# 第一步：Python 依赖（两台机器各装一遍）

```bash
pip install cryptography
```

不装也能启动，但**跨机消息一律拒收**（fail-closed，见二、附录 A 铁律 5）—— 所以当**必装**。

# 第二步：让两台机器交换文件（传输层）

```powershell
winget install Syncthing.Syncthing          # Windows；Linux/macOS 走包管理器或官网下载
python acp-deviceid.py --config <syncthing-home>/config.xml   # 打印本机 Device ID（不依赖 Syncthing 可执行文件）
```

`<syncthing-home>` = Syncthing 配置目录（含 `config.xml`）：Windows 例 `%USERPROFILE%\acp-home\syncthing`、Linux/macOS 例 `~/.config/syncthing`。
**先启动一次 Syncthing**（生成本机身份，目录里出现 `cert.pem` / `config.xml`）再跑上面这条；**别直接抄不带 `--config` 的裸命令** ——
它只在几个固定默认路径里找 `cert.pem`，配置目录不在默认位置（本项目就不在）时会打印「未找到 cert.pem」。

要点（照做就行）：

1. **双向添加设备 ID**：A 把 ID 给 B、B 加 A 之后，**A 侧也要把 B 加回来**。只加一边的典型症状是一直 `Hello EOF`。
2. **共享目录自选**（下称 `<shared-dir>`），两台机各指各自本地路径；双机建议 **Folder ID 起同一个名字**，便于排查。
3. **先加文件夹，再放 `.stignore`**（顺序不能反）：在 Syncthing 里把 `<shared-dir>` 加成 Folder **之后**，再把仓库里的 `.stignore` 拷进 `<shared-dir>` 根 —— 挡掉 `~syncthing~*` / `*.tmp`，以及冲突副本 `*.sync-conflict-*`（结尾也是 `.json`，不挡会被当成信件扫到）。反过来的话，Syncthing 可能先把 `.stignore` 当普通文件同步出去、**忽略规则不生效**；放好后**去 Syncthing 界面确认这个文件夹的「忽略模式」已识别到这几条规则**才算生效。
4. **共享目录别混放大文件**：大文件另开一个目录，信箱只放小消息。

# 第三步：建身份 + 带外核对指纹

```bash
# 建身份。--home 是本机私有目录（含私钥，绝不进同步目录）；--root 是 Syncthing 同步的那个目录
python acp.py --home <home-dir> --root <shared-dir> init --agent <agent> --display "Codex@台式机"

# 打印本机指纹
python acp.py --home <home-dir> --root <shared-dir> status

# 带外核对对方指纹（当面 / 口头，不能靠网络），再信任
python acp.py --home <home-dir> --root <shared-dir> trust --agent <对方agent> --fingerprint xxxx-xxxx-xxxx-xxxx
```

占位符按平台替换：Windows 例 `--home %USERPROFILE%\acp-home --root %USERPROFILE%\acp-shared`；Linux / macOS 例 `--home ~/acp-home --root ~/acp-shared`。

**`trust` 的前提（顺序别抢）**：`trust --agent <对方agent>` 会去读 `<shared-dir>/peers/<对方agent>.json`（**对方的名片**）。
所以对方**必须先 `init`**，且名片**已经通过 Syncthing 同步过来** —— 也就是**等「双向加设备 ID」成功、共享目录真的开始同步之后**再 `trust`。
名片到位时指纹不符会被直接拒；**名片还没到时 `trust` 不会替你核对**（照你报的指纹记下），所以指纹**必须来自带外渠道**（当面 / 口头），别猜、别从网上抄。
`trust` 之后**再跑一次 `status`**，核对「已信任的对方」里那一行指纹**正是你带外核过的那串**才算真信任；**`trust` 退码 0 不代表核对正确** —— 名片不在时它会静默接受你输入的任何指纹，指纹这一环**全靠带外核对**。

三条必守：

- **`--root` 不能省**：省了会默认写 `<home>/shared`，**退出码 0、看着像成功**，信却落在本机私有目录（见一、常见问题 Q5）。
- **agent 名要跨机唯一**：两台机器不能都叫 `codex`（会覆盖名片、挤进同一个发件箱）。
- **私钥不进共享目录**：`--root` 下应该只有 `peers/`、`outbox/`、`.stignore`。

# 第四步：收发信（先跑通这条路）

```bash
python acp.py --home <home-dir> --root <shared-dir> send --to <对方agent> --text "第一条测试消息" --reply answer
python acp.py --home <home-dir> --root <shared-dir> inbox      # 对端
python acp.py --home <home-dir> --root <shared-dir> digest     # 一屏看完待处理（省 token 的收信方式）
python acp.py --home <home-dir> --root <shared-dir> ack <msg_id>
```

**判据**：`<shared-dir>/outbox/<对方agent>/` 里**真有文件**才算发出去了；别只看退出码。

常用命令速查（都带 `--home <home-dir> --root <shared-dir>`，下表省略）：

| 命令 | 作用 |
|---|---|
| `acp.py ... status` | 看身份 / 信任 / 收件箱 / 刹车状态，打印本机指纹 |
| `acp.py ... send --to <对方agent> --text "..."` | 投递一条；`--to '*'` = 广播；`--reply none` = 不用回（默认 `auto`） |
| `acp.py ... send --reply-to <msg_id> ...` | 回信（自动 `hops+1`） |
| `acp.py ... inbox` | 列出收件箱（加 `--all` 含非 ok） |
| `acp.py ... ready` | 只列**真正可执行**的消息（受 STOP 与放行票约束） |
| `acp.py ... send` 的 `--reply` | `none` / `ack` / `answer`，**只是个省 token 的信封标签**（收方不用读正文就能过滤）；**它不会自动回执** —— 回执仍要对方主动发 |
| `acp.py ... digest` | 把待处理消息压成一屏 —— **省 token 的收信方式**（默认只显示最近 **30** 条，`--limit` 可调） |
| `acp.py ... ack <msg_id>` | 确认已处理 = **结案**：投递状态改 `done`、**作废放行票**、从 `digest` 消失；**只对 `ok` 状态有效**，`untrusted` / `expired` 等一律拒绝 |
| `acp.py ... watch --loop --interval 3` | 常驻投递（只搬文件、不调模型，挂机不烧 token）；会把见过的消息记进 `<home>/state/seen.json` |
| `acp.py ... audit` | 校验并查看哈希链审计 |
| `python selftest.py` | 离线跑一整套自测（闸门 / 刹车 / 伪造放行票 / 坏消息隔离），不需要网络 |
| `python acp_net.py --syncthing-home <syncthing-home> status` | 看网络档位 + 实际走直连还是中继 |

# 第五步：常驻投递（挂机零 token）

```bash
python acp.py --home <home-dir> --root <shared-dir> watch --loop --interval 3
```

- 开机自启：Windows 任务计划程序（登录触发）；Linux `systemd --user`（或 `crontab @reboot`）；macOS `launchd`。
- 写消息文件 / Syncthing 同步 / `watch` 收信落盘 **都不耗 token**（`watch` 进程**零网络连接**，源码里没有任何 HTTP 客户端）；**唯一耗点是"自动叫模型处理"，而本程序不提供这个动作**。

另外两条要知道的：**`watch` 会写 `<home>/state/seen.json`**（记"见过哪些消息"，**7 天后过期**）—— 判重就靠它，**删掉 `state/` 会让旧信重新投一遍**；
Linux 想开机自启又没有现成文件，可照下面这份 `systemd --user` 模板（**本仓库不提供现成 unit，请自己落到 `~/.config/systemd/user/acp-watch.service` 并按你的路径改**）：

```ini
[Unit]
Description=ACP-lite watch (deliver only, never calls a model)
After=network-online.target

[Service]
Type=simple
ExecStart=/usr/bin/python3 %h/acp-lite/acp.py --home %h/acp-home --root %h/acp-shared watch --loop --interval 3
Restart=always
RestartSec=5

[Install]
WantedBy=default.target
```

启用：`systemctl --user daemon-reload && systemctl --user enable --now acp-watch`；要**开机免登录也常驻**再加 `loginctl enable-linger <你的用户名>`。

# 第六步（可选）：跨主机 SSH 唤醒

本项目**不内置**唤醒通道（`watch` 永不调模型），但**已实测可用**（SSH 直连，2026-10-14 / 10-15，5 次闭环全过）——
**在我们这套环境、这 5 次里**如此；换环境不保证同样顺利（DSH 那条见一、常见问题 Q9）。

**目标只有一个：** 让 A 机（如常开的上网本）通过 `ssh` 把任务交给 B 机（如台式机）上的 headless CLI（`dsh` / `codex`），
结果再经 ACP 回信落到 A 机。**能做到这一点就够了。**

**关于权限，说清楚就好：** 两台机器都在**自己的局域网**内，唤醒时给 `danger-full-access`
是刻意的选择 —— 不是安全疏忽。所以：

- 22 端口**只对本网段开**（下面的防火墙规则就是这么写的），别做端口转发、别暴露到公网；
- 如果要唤醒的是**公网上的机器**，那就得另做一层认证（私钥 + 跳板 / VPN），不要照抄这里的档位；
- 改文件、删文件这类**破坏性操作**，仍然先问人 —— 权限放开不等于可以先斩后奏。
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

唤醒前先跑 `python acp.py --home <acp-home> --root <shared-dir> ready`；**`STOP` 存在就别叫** —— 刹车优先于任务。

唤醒命令（提示词**走文件 + stdin**，中文和特殊字符都不会被 shell 弄坏）：

```cmd
rem 唤醒 Codex（沙箱档位必须让目标目录可写 —— 见一、常见问题 Q1）
if not exist "%TEMP%\codex-wake" mkdir "%TEMP%\codex-wake"
codex exec -s workspace-write --skip-git-repo-check -C "%TEMP%\codex-wake" ^
  --add-dir "<shared-docs>" --add-dir "<shared-dir>" --add-dir "<acp-home>" ^
  - < prompt.txt
```

把下面存成 `wake-dsh.cmd`，与 `prompt.txt` 放同一目录，执行脚本本身：

```cmd
@echo off
setlocal
set "DSH_PERMISSION_MODE=danger-full-access"
set "PROMPT_FILE=%~dp0prompt.txt"
if not exist "%PROMPT_FILE%" (echo [FAIL] prompt.txt not found & exit /b 2)
if not exist "%TEMP%\dsh-wake" mkdir "%TEMP%\dsh-wake"
cd /d "%TEMP%\dsh-wake"
rem bin.js 路径以 npm root -g 为准；Windows 默认在 %APPDATA%\npm\node_modules
node "%APPDATA%\npm\node_modules\@deepseek-ai\dsh\lib\bin.js" --profile headless - < "%PROMPT_FILE%"
```

**一次唤醒 = 一次独立会话（不要复用会话）**

别用 `--session-id` 去续接同一个会话。任务本身是独立的，复用会让上下文一轮轮累积：
每次唤醒都要重读全部历史，**token 一次比一次贵**，而且「这次到底讲了什么」也说不清。

代价是每次新建都留一条会话记录。这条记录**就是审计凭证**，不是垃圾 —— 多到一定数量再统一清。

**唤醒后留一份凭证（可审计 / 可计费 / 可回溯）**

```text
一次唤醒   → 一条 ACP 消息（msg_id，签名）
           → 一个 CLI 会话（会话 id，可回放）
           → 一份凭证（下面的 6 行）
```

凭证落到共享目录（如 `<shared-docs>/wake-log/2026-10-20-1420-<任务>.md`），六行就够：

```text
msg_id   : hermes-<host>-<date>-<time>-<hash>
时间     : 2026-10-20 14:20 +08:00
任务     : <一句话>
执行方   : <agent>@<host>（CLI: dsh|codex / 会话 id）
结果     : ok | fail | partial —— <一句话>
凭证     : outbox/<agent>/<msg_id>.json（签名可验）
```

**为什么要这一步**：ACP 只说「需求」，CLI 只负责「执行一次」。**只留 ACP 消息，人看不出它到底做了什么；
只留会话，别人又不知道这次算谁的单。** 两者用 `msg_id` 挂上，审计和计费就都有了落点。

自己一个人用可以从简；**要把项目交给别人用，这六行必须有** —— 不写清楚，别人既不敢用，也说不清钱花在哪。

**环境变量：差一个字符，整条链全断**

```cmd
错误：set "DSH_PERMISSION_MODE=danger-full-access "    ← 引号内含尾随空格
正确：set "DSH_PERMISSION_MODE=danger-full-access"      ← 精确值
```

后果（实测症状）：dsh 按字面校验档位 → 模块不激活 → `pwsh` 工具 pending → 启动报 `0xC0000142`。
判据：`echo [%DSH_PERMISSION_MODE%]` 必须回显 `[danger-full-access]` —— `]` 前多一个空格就是错的。

**5 个坑：症状 → 真因 → 指令 → 判据**

| # | 你会看到 | 真因 | 指令（照做） | 判据 |
|---|---|---|---|---|
| 1 | `pwsh` 找不到，或版本是 5.1 | DSH 的 pwsh 工具要 PowerShell 7；Windows 自带的是 5.1 | 装 PowerShell 7，确保 `pwsh` 在 PATH | `pwsh -v` 输出 `7.x` |
| 2 | 启动即 `0xC0000142`，pwsh 工具 pending | 档位值带尾随空格，schema 按字面比对失败 | 按上面「错误 / 正确」改成精确值 | `echo [%DSH_PERMISSION_MODE%]` 得 `[danger-full-access]` |
| 3 | prompt.txt 明明在，却报找不到文件 | 脚本先 `cd` 再 `< prompt.txt`，相对路径已失效 | `cd` 之前用 `%~dp0` 把提示词解析成绝对路径 | `if not exist "%PROMPT_FILE%" exit /b 2` 没触发 |
| 4 | 变量设了，dsh 里却读不到（静默不干活） | 变量没和 dsh 同进程：`cmd /c "set X=Y && dsh"` 链式，或经 `dsh.cmd` 包装层转手 | 同一条 `.cmd` 里 `set` 完直接调 `node ...\bin.js`，绕过 `dsh.cmd` | 让 prompt 输出 `$env:DSH_PERMISSION_MODE`，回显 `danger-full-access` |
| 5 | 同一个 `dsh`，行为 / 配置却对不上 | PATH 里有两个 `dsh.cmd`：桌面版自带（转 `.exe`）与 npm 全局（转 `bin.js`），配置目录各自独立 | `where dsh` 看第一条；要确定性就在模板里写死 `node ...\bin.js` | 启动横幅里的配置目录 / 版本与预期一致；两者可共存、不冲突，只有 `resume` 抢写权会失败 |

```bash
# 同机两个 agent 也能双向 CLI 互调（换成你自己的 CLI 同理）
openclaw agent --message "只回答两个字：收到"   # 蓝莓(Hermes) → 蛋糕(OpenClaw)
hermes -z "只回答两个字：收到"                  # 蛋糕 → 蓝莓（反向同样成立）
```

唤醒只递"**指针**"（收信文件的绝对路径，里面才有 `msg_id`），正文仍让对方自己回信箱读 ——
**ACP 是账本，CLI 是门铃；门铃不能替代账本**。

**验收判据：三样都成立才算唤醒成功，不看退出码。**

1. **产物落盘**：`dir <产物路径>` 能看到文件，大小 > 0，时间晚于本次唤醒。
2. **审计链增长**：`python acp.py --home <acp-home> --root <shared-dir> audit` 条数 +1，最新一条 hash 对得上。
3. **签名回执**：`outbox/<你的 agent>/` 里出现回信，且 `verify` 通过。

`exit 0` 可能只是"说了话"：不落盘、不入账、不回信 = 没干。

**机器没开机的时候怎么办（带外唤醒）**

SSH 要操作系统起来才能敲，关机时叫不醒机器。要「不在家也能开机」，用**智能插座 + 主板断电恢复自启**（插座 50 元左右）：

```text
① BIOS：Advanced → APM Configuration → Restore AC Power Loss = Power On
② Windows：关掉「快速启动」，否则关机是假关机、通电不启动
   控制面板 → 电源选项 → 选择电源按钮的功能 → 取消「启用快速启动」
③ 插座 App：「断上电管理」必须选【开启】
   ✗ 不要选「记忆」——靠插座自己判断断电前状态，实测不可靠
   ✗ 不要选「关闭」——通电也不输出，主板根本收不到 AC 恢复
④ 墙插 → 智能插座 → 主机电源
⑤ 开机：App 断电 → 等 30 秒 → 通电 → 自动开机
⑥ 平时：插座常通电，按机箱按钮开机，当普通插座用
```

实测注记（2026-10-19，同一配置连续 3 次全过）：模拟停电 30 秒后合闸主机自行启动；关机要等电源灯完全熄灭再断电（否则日志出现 `Kernel-Power ID 41` 异常断电，下次可能不启动）。**插座不要频繁通断**，只在真正需要远程开机时用。

**唤醒后必须回报（协作纪律，不是某台机器的实现细节）**

- **被唤醒方**（Codex / DSH）：干活期间保持"处理中"**可见**（会话不提前退出）；干完**必须发签名 ACP 回信 + 广播** —— 不回话，唤醒方就不知道你是没收到、还在干、还是已经结束。
- **唤醒方**（蓝莓等）：**盯到回执为止**；完成或超时都要**主动告诉人类**，别等人来问。
- **为什么**：人类**不盯屏幕、也看不到后台窗口**。若"丢完信令就撒手"，人**无法判断任务是在跑、是卡住、还是已经结束** —— 体验直接退化。
- 一句话原则：**要么看得见它在"处理中"，要么完事必有回音 —— 二选一必须有一个。**

### 云端 Personal Agent 怎么连（综述）

前面讲的是「**另一台你自己的机器**」—— 你能 SSH 进去，能设沙箱、能唤醒。
**云端 personal agent 是另一回事**：跑在别人的公有云上，你没有 root，也没有 CLI。

这一节讲通用机制，**两个具体案例分别在 FAQ 的 Q16（Grok Bot）和 Q17（Meta Muse）**。

#### 共同点：两类 agent 走的都是同一套账

```
ACP 写信（账本） → Syncthing 同步（传输） → 对方处理 → 回信（账本）
```

**差别只在「门铃」：**
```
自己的机器  ：SSH 敲门，随时能叫起来
云端 agent  ：没有门铃，只能等它自己或主人手动触发
```

#### 两层信任，缺一不可

| 层 | 职责 | 依据 | 失败表现 |
|---|---|---|---|
| **Syncthing** | 文件同步 | Device ID 互加 + folder 批准 | 文件不到，`need > 0` |
| **ACP-lite** | 签名信封 | 带外核对指纹后 `trust` | 文件到了但消息不受信 |

- Device ID 是**机器级**身份；ACP 指纹是 **agent 级**身份。
- 只加设备不 trust → 同步通了，信封仍被拒。
- 只 trust 不加设备 → 信写得出去，对端收不到。

#### 目录照三层分（见 Q15）

```
公共公告区    它能读
对端专属区    它读写
内部区        它看不到
```

#### 它会连不上的三种典型原因

**① 自己的 relay 挂了**（最常见）
```
log 里连续 TLS handshake i/o timeout
→ 局域网内全好，所有云端对端全断
→ 处置：重启本端 Syncthing，让它重选 relay
```

**② 发现服务查不到对方地址 —— 这不是故障**
```
relay 模式下双方都注册到中继，由它牵线
本来就不需要互相知道公网 IP
```

**③ 对方离线**
```
云端没有常驻守护，掉线是常态
上线后自动重连，实测 6~9 分钟
```

#### 边界：能做什么，不能做什么

```
能做：读写专属交换区、收发签名信封、被触发后自动处理任务
不能：被 CLI / SSH 唤醒；无人触发时不会自己起来巡检
```

**⇒ 派活方式必须按「人工触发」设计。**
**这是形态差异，不是配置缺失。** 接 WorkBuddy 这类云端 personal agent，大概率同样如此。

---

## 一、常见问题（FAQ：2 条定义 + 4 条怎么连 + 9 条踩坑 + 2 条云端接入）

⚠️ **先说边界**：下面每一条都来自**我们这一套特定环境** ——
**Ubuntu 上网本 + Win11 台式机 + Syncthing + Clash（Windows 侧）**，agent 是 `codex-desktop` / `dsh-desktop` /
`hermes-netbook` / `openclaw`。**别的环境不一定一样**，遇到问题请结合你的机器自行判断，别当"通用即插即用"。

### 定义（Q0 → Q0b）

**Q0: ACP-lite 是什么？**
A: ACP-lite (Agent Connect Personal) 是**跨主机 Agent 互联的最小实现**：一台机器一个"邮局"，Agent 仍然只读写本地文件；两台 NAT 后的普通电脑即可，不要公网、不要服务器。

**Q0b: 这是不是一个能一键装/一键卸的 SaaS？**
A: **不是。** 没有商店、没有安装包、**没有卸载按钮**，**这是我们一点点配出来的**：人类出点子，AI 负责实现。
正确用法只有一条：**把仓库链接交给你的 coding agent，让它照着本文做** —— 你自己不必一个字一个字读，agent 也不必。

### 怎么连（Q1 → Q4）

**Q1: Codex 怎么连？**
A: 分两层。**收信**：和 Syncthing 共享同一个 `<shared-dir>`，`acp.py` 只管读写文件，不需要常驻服务。
**唤醒**：跨机走 SSH，命令里必须 **`-s workspace-write`** 并把**每个**目标目录 `--add-dir` 进去 ——
`<shared-docs>`（文档）、`<shared-dir>`（信箱）、**`<acp-home>`（最容易漏，不给写权就是"信发了、账没记"）**。
启动横幅会打印实际可写根，可当硬证据。**完整唤醒命令见第六步**（本机是 Windows 时，先按 Q3 登上去）。

**Q2: DSH 怎么连？**
A: **DSH 没有 `--add-dir`**，可写根写死为"工作区 + `/tmp` + 系统临时目录"，没有扩展入口，只能
**整机放权**：唤醒时用**同一个进程**设 `DSH_PERMISSION_MODE=danger-full-access`，并**换一个干净的工作目录**
（如 `%TEMP%\dsh-wake`，别和别的 agent 共用沙箱目录）。两句缺一不可 —— 少了档位写不出去，目录脏了命令在沙箱准备阶段就起不来。
**可复制模板、环境变量对照、5 个坑与判据见第六步**（那里是唯一事实源，本问只讲原则；本机是 Windows 时先按 Q3 登上去）。

**Q3: 怎么通过 SSH 登上去？**
A: **加设备 → 装服务端 → 打洞 → 登录**，四小步：

```powershell
# ① 本机是 Windows（被连的一方）：装 OpenSSH 服务端并让 22 端口只对本网段开
Add-WindowsCapability -Online -Name OpenSSH.Server~~~~0.0.1.0
Set-Service sshd -StartupType Automatic; Start-Service sshd
New-NetFirewallRule -Name OpenSSH-Server-In-TCP-LAN -DisplayName 'OpenSSH Server (LAN only)' `
  -Enabled True -Direction Inbound -Protocol TCP -Action Allow -LocalPort 22 -RemoteAddress 192.168.0.0/24
```

```bash
# ② 对端是 Linux（发起的一方）：装客户端（一般自带）
sudo apt install openssh-client

# ③ 交换公钥，免密登录（从发起方执行，一路回车）
ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519 -N ""
ssh-copy-id <对端用户名>@<对端局域网IP>

# ④ 验证：登录 + 只跑一条无害命令
ssh <对端用户名>@<对端局域网IP> "hostname && date"
```

**方向先讲清**：第六步的场景是 **Linux（发起方）→ Windows（被唤醒方，Win11）**，上面 `ssh-copy-id` 是 **Linux / macOS** 的写法。
**Windows 原生 OpenSSH 里没有 `ssh-copy-id`** —— Windows 当发起端时，在 `cmd` 里用等价命令：

```cmd
ssh-keygen -t ed25519 -f %USERPROFILE%\.ssh\id_ed25519 -N ""
type %USERPROFILE%\.ssh\id_ed25519.pub | ssh <对端用户名>@<对端局域网IP> "cat >> .ssh/authorized_keys"
```

- **别搞混两套标识**：Syncthing 的 Device ID 是**机器级**（一台机一个，`python acp-deviceid.py` 可算），
  ACP 的 agent 指纹是**身份级**（每个 agent 各一个）。
- 登上去以后要**唤醒某台机器**，命令见 **第六步**；SSH 只负责"敲门"，账本仍归 ACP。
- 两个已知不一致，别踩：**收信**只要防火墙放行 22 **且**对端 `sshd` 在跑（`Get-Service sshd`）；
  **唤醒**还要目标目录**可写**，加设备成功不等于唤醒能干活。

**Q4: 跨机到底是怎么"叫醒"的？**
A: **SSH 只递指针** —— 传一条消息，内容是"去读 `<绝对路径>` 那封信"；被唤醒的 CLI 再去自己的信箱读正文。
所以链路是 **ACP 发需求 + SSH 发信令**，SSH 断了信也不丢（信在共享目录里）。
代价：SSH 前台会**随会话断开**，长活要换成计划任务（见 Q7）。

### 踩坑（Q5 → Q13）

**Q5: `acp.py --root` 能省吗？**
A: **不能省。** 省略时默认写 `<home>/shared`（不是群共享目录），**退出码 0、没有任何报错**，信却落在
本机私有目录、群里谁也看不见。发信 / 回信一律显式写 `--root <shared-dir>`；判据 = `outbox/<收件 agent>/` 里真有文件。
**`--home` 同样有默认值**（`~/.acp-personal`）：两个默认值叠加最能骗人 —— `--home` 一漏，`--root` 也跟着落到
`~/.acp-personal/shared`，信照样离群。所以**两个都显式写**。

**Q6: 中文正文 / 中文提示词怎么传？**
A: **别走命令行参数**（`cmd` / PowerShell 把 UTF-8 当 GBK 读，收到形如 `鎶婅繖鍙ヨ瘽…` 的乱码；非交互 SSH
还会重排分词）。**走文件 + stdin**：正文先写成 UTF-8 文件，用 `- < 提示词.txt` 交给被唤醒的 CLI；发中文信时
也在**同一个 Python 进程**里读文件再调 `acp.main([...])`，别让中文经过 shell。

**Q7: `schtasks` 还是 SSH 前台？**
A: **短活用 SSH 前台，长活用计划任务**：`schtasks` 会弹控制台窗口、但**抗 SSH 断连**；SSH 前台不弹窗、
但**随会话断开**。`start /b` 起的后台任务会被 SSH 会话回收，别用。

**Q8: 环境变量怎么传给被唤醒的 CLI？**
A: **只用单进程 `set`**：`set "DSH_PERMISSION_MODE=danger-full-access"` 紧跟着 `dsh …`（同一条 `.cmd`、
同一个进程）。**别用 `cmd /c "set X=Y && dsh"` 链式** —— 档位传不下去，现象是**静默零落地**（不报错、不落盘）。

**Q9: DSH 被唤醒后"手脚被捆"，报 `SetNamedSecurityInfoW failed Win32 5`？**
A: 光设 `DSH_PERMISSION_MODE=danger-full-access` **不够**，还要一个**干净的工作目录**：脏目录的 ACL 授不了权
（`grantWrite(<目录>)` 被拒，Win32 5 = 拒绝访问），命令在**沙箱准备阶段就起不来**。换个干净目录再唤醒即可
（DSH 的 cwd 要单独给一个干净目录，如 `%TEMP%\dsh-wake`，别和别的 agent 共用）。这条**不是稳定复现**，别当"必挂"宣传。

**Q10: 桌面版开着，会不会影响 CLI 唤醒？**
A: **不影响**（实测）：桌面版与 CLI 唤醒是**各自独立的会话**，没有写权冲突（DSH 桌面版 5 个进程在跑时，
CLI 唤醒照样 18 秒跑完并写进工作区外）。例外只有"接管已有会话"：Codex 桌面客户端握着写权时
`resume` 会失败（`already has an active writer`）。

**Q11: 同一个 WiFi，Syncthing 却显示"中继"？**
A: 局域网发现被挡了，先查 **TUN / 代理**。判据看 Syncthing 界面的「连接类型」：**TCP 局域网 = 直连**、
**中继 = 跨网的正常状态**，**同一 WiFi 却显示中继 = 异常**。换网后嫌慢别干等 —— 实测被动等约 **4 分 50 秒**，
主动 `python acp_net.py --syncthing-home <syncthing-home> kick` 约 **2 秒**。

**Q12: Windows 上 Syncthing 全员配置正确，就是永远连不上？**
A: 八成是 **`ALL_PROXY`**。Syncthing v2.x 走 `proxy.FromEnvironment()`，**只认 `ALL_PROXY` / `all_proxy`**、
**且不读 `NO_PROXY`**，于是所有拨号都被接走。日志判据：正常是
**`Dialer logging disabled, as no proxy was detected`**，被接走是 `Proxy settings detected` + `error: EOF`。
修法是起 Syncthing 前一个不漏地清干净（**最容易漏的就是 `ALL_PROXY`**）：

```cmd
set ALL_PROXY=
set all_proxy=
set HTTP_PROXY=
set HTTPS_PROXY=
set http_proxy=
set https_proxy=
set NO_PROXY=*
```

> Windows 环境变量名**不区分大小写**：`ALL_PROXY` 与 `all_proxy` 是**同一个** —— 先设 `ALL_PROXY=…` 再设
> `all_proxy=''` 等于把它删掉，实验结果会自相矛盾。**正确写法：先清其它变量，最后再设 `ALL_PROXY`。**
> 同一个 Clash，Linux 侧默认不受影响（不设进程代理变量、不开 TUN 就不走代理）。

**Q13: 还有哪些"看着没事、其实是坏了"的坑？**
A: 四条都是实测：

- **`--root` 省了**：退出码 0，信落私有目录（见 Q5）。
- **`state=idle` 不代表同步正常**：单个文件失败会**阻塞整个文件夹**，看日志里的 `pull:` 错误，别只看状态。
- **删源文件会让对端拉取失败**：对端正在拉的文件被你删了 → `pull: no such file` → 整个文件夹停摆重试。删之前先确认对端不在拉。
- **`git push` 在 Windows 弹窗/崩溃**：schannel 在非交互账户下报 `SEC_E_NO_CREDENTIALS`，凭证管理器一起凑热闹就弹框要人点。
  无人值守姿势是**换 openssl 后端 + 清空 `credential.helper` + token 进 URL**（仓库里的 `push-acp.cmd` 就是这条）：

```bash
git -c http.sslBackend=openssl -c http.proxy=http://127.0.0.1:7897 -c credential.helper= \
  push https://x-access-token:<GH_TOKEN>@github.com/furoute/acp-lite.git main
```


### 接云端 Personal Agent（Q14）

**Q14: 云端 personal agent 能接吗？**
A: **能接。通用机制和边界见第六步末尾的「云端 Personal Agent 怎么连」综述。**

这里只列两个具体案例：
- **Q16** — [mango@GrokBot（Grok Bot）](#案例一mangogrokbot-grok-botq16)
- **Q17** — [muse-cloud（Meta Muse）](#案例二muse-cloudmeta-museq17)

---

### 和外部 agent 怎么分目录（Q15）

**Q15: 接了外部 agent 之后，共享目录该怎么划？**
A: **划三层，每层一个独立 folder。别让外部和内部共用一个目录。**

2026-10-20 实测：外部 agent 曾能读到内部的全部文件（含个人简历），因为共用了 `shared-files`。
改法是三个互不嵌套的 Syncthing folder：

| folder | 放什么 | 谁可见 |
|---|---|---|
| `acp-shared-public` | 公告、协议说明、协作约定、操作手册、模板、公开名片 | 内部 + **每个外部（只读）** |
| `acp-shared-<对端>` | 与某一个外部的专属交换区 | 内部 + **该对端**（其他外部不可见） |
| `acp-shared` / `shared-files` | 邮局与运行设施 / 内部文件 | **只有内部** |

**四条硬约束**（实测踩过才加的）：

1. **三个 folder 必须彼此独立**——Syncthing 的授权单位是 folder × device，子目录不隔离；父目录一旦共享，子目录再划权限也没用。
2. **公共区不兼邮局**——`--root` 指向哪个目录，那个目录的 `outbox` 对同 root 全体可见。公告区和信件区分开。
3. **`outbox/<agent>/` 只放 `.json`**（`cli_calls.jsonl` 是日志例外）；大文件放文件区，信里只写路径。
4. **公共区不做扩展名白名单以外的事**——只收 `.md .txt .json .pdf .png`；`.cmd .ps1 .exe .py .bat .sh` 一律不进。唤醒脚本尤其不能进：外部改了它，下次唤醒就是任意代码执行。

**两个容易忽略的坑：**

- **断开共享 ≠ 撤回**。外部方本地已有副本，移出 folder 只是停止更新，删不掉它那边的。方案只能防下一次。
- **只换 `--root` 不等于换可见范围**。`to` 决定「谁处理」，`root` 才决定「谁看得见」。

### 案例一：mango@GrokBot（Grok Bot）（Q16）

**Q16: 第一个接进来的云端 agent 是哪个？怎么接的？**
A: **2026-10-19，`mango@GrokBot`（阿里云 VM，公网出口），2 小时跑通。**

它是别人家的对话式 Bot —— 不在我们任何一台机器上，也不是我们装的。

**接入步骤：**
```
① 建专属目录 / folder，只共享给它 + 内部主机
② 互加 Syncthing Device ID
③ 带外核对 ACP 指纹后 trust
④ hello → 回执 → 闭环
```

**当时踩的 4 个坑：**
- `__pycache__` 残留导致远端删不掉的目录每 60 秒重试，拖垮整个文件夹
- 写了文件不触发重扫 → 对端看不到
- 信封卡在 `.tmp` → 读到半成品
- 重启后连接不自愈，要手动暂停/恢复设备强制重连

**⚠️ 注意：会周期性断线，这是正常的**

GrokBot 的虚机闲置时会被**平台回收/休眠**，Syncthing 进程随之停止 → 连接断开（`connected=false`）。
**手动唤醒虚机后它自己重连，不需要重走接入流程。**

```
现象：connected=false，need 停在 0，对端在 discovery 里还有地址
原因：云端 VM 被回收，不是配置错、不是同步坏
处置：唤醒虚机，等它重连（几分钟内）
```

**⇒ 设计协作必须考虑这一点：给云端 agent 派活要「人工触发」，不能假定它一直在线。**
**这也是我们把它定位成「人工触发、自动处理」的原因之一。**

**完整记录：** → **[云端 Agent 接入 ACP-lite 案例：mango@GrokBot 跨公网首接](云端Agent接入案例-mango-20261019.md)**

### 案例二：muse-cloud（Meta Muse）（Q17）

**Q17: 第二个云端 agent 接的时候，和第一个有什么不同？**
A: **同一套三层结构，翻车点完全不同 —— 主要卡在 relay 和平台权限。**

2026-10-21 接入 `muse-cloud`（Meta 的云端 personal agent）。结构沿用 Q15，但遇到这些新问题：

**① 中继节点会挂**
```
本端 relay 101.132.x.x 连续 10 次 TLS handshake i/o timeout
→ 表现：局域网内一切正常，所有云端对端全断
→ 处置：重启本端 Syncthing，自动重选 relay（换到 171.213.x.x）
→ 结果：60 秒内全部恢复
```
**教训**：内网好、外网全断，先怀疑自己的 relay，不是对端。

**② 名片不能写半成品**
建对端名片时如果只有指纹、没有公钥，**不要先落一张缺 `pub` 的卡** —— 对端会读到坏名片。等对方 `init` 生成的名片同步过来再补。

**③ 平台权限：逐步手动确认**
Muse 那边每个连接、每个 folder 都要人工点确认，不像 GrokBot 一步过。**这是平台机制，不是配置错误。**

**④ 云端没有常驻，掉线属正常**
对端离线时 `connected=false`、`need` 停在 0；上线后自动重连，实测 6~9 分钟。

**⑤ 代理不是障碍**
对端只能走代理出网，连不上直连端口 —— 但 **relay 模式本来就不走直连**，这个担心是多余的。

**完整记录：** → **[云端 Agent 接入联调实践：muse-cloud](云端Agent接入案例-muse-cloud-20261021.md)**

---

## 二、附录（给人看的：为什么这么设计；照着用可以跳过）

### A. 五条铁律

1. **同机不变**——原文件通道照旧；本程序不读不写 `mailbox/`。
2. **跨机只共享目录，不共享整台机器**——Syncthing / Tailscale / 网盘 / U 盘都能当传输层。
   只有一个网内对端时，一个目录就够了；一旦接入外部 agent，就按 **Q15 的三层**分（公共 / 对端专用 / 内部），各自独立 folder。
3. **私钥不进共享目录**——`--home` 是本机私有；共享目录里只有名片和发件箱。
4. **收信不调模型**——`watch` 只落盘 + 记审计，挂机不烧 token。
5. **缺依赖就拒收（fail-closed）**——本机没有 `cryptography` 时跨机消息**默认一律拒收**；
   自测要收只能显式加 `--allow-unsigned`，此时消息标记 `unverified` 且**永不进入 `ready`**。

### B. 出口闸门（安全的核心）

| 动作 `--requires` | 谁能做 |
|---|---|
| `none` / `read` | 自动可做 |
| `write` / `send` / `pay` / `delete` | **必须由人签一张一次性放行票** |

**硬约束**：`--requires write/send/pay/delete` 时**必须同时给 `--action exec`**。`--requires` 不是 `none`、`--action`
还是默认的 `infer`，`send` 会**直接报「语义矛盾」拒绝**（`infer` 只用于理解与回应，不可能去付款 / 发送 / 删除）。

```bash
python acp.py ... userkey                 # 建 L2 人密钥（口令加密，只存本机，只你有口令）
python acp.py ... approve <msg_id>        # 人工放行：需要输入口令
python acp.py ... stop                    # 刹车：一切出口动作立即停止（收信不受影响）
python acp.py ... stop --off              # 解除
```

- **agent 拿不到口令 ⇒ 无法自签放行票**：这是"被注入的 agent 不能自己给自己批条子"的落地方式。
  票**必须由 L2 人密钥签名**，`ack` 时验签；绑定"消息 ID + 动作摘要 + 有效期"，改过即失效、用一次即作废、重放无效 —— agent 自己写一个 `approved-*.json` 文件不管用。
- **`STOP` 是一个文件**：文件系统在，刹车就有效，不依赖模型、不依赖网络；**刹车期间 `ack` 一律拒绝**。

### C. 跨机信封

`to` 的语义像**微信群 @ 人**：共享目录里的消息，房间里每个成员都看得见（文件就摆在那儿，
没有任何保密性），`to` 只决定**"谁被点名、谁该处理"**：

| `to` 的值 | 含义 | 其他成员 |
|---|---|---|
| `dsh-desktop` | 点对点：**只请 DSH 处理** | 看得见，但 `watch` 不投递、不执行（等同围观） |
| `*` | 广播：**请所有人处理/回应** | 正常投递，各自判定 |

所以本项目的"点对点"= **只点名不加密**，别往里放不该给别人看的东西。

| 规矩 | 字段 | 作用 |
|---|---|---|
| 单写者 | 目录 `outbox/<自己>/` | 谁都不会踩到别人的文件，Syncthing 不冲突 |
| 幂等 | `idem` | 投递层直接丢弃重复（邮件重发/同步抖动都安全） |
| 防回环 | `hops` / `max_hops` | 超上限直接拦，避免两边自动处理互相点火 |
| 过期即拒 | `expires_at` | 三天前的任务不会在你开机时突然自动执行 |

> `hops` 防的是**无限回环**，不是"多轮往返"：默认 `max_hops=4` 即允许 4 轮来回；
> 要严格"只回一封"就加 `--max-hops 1`。**单条坏消息不连坐同轮其它消息**（标 `rejected/malformed` 后跳过）。

字段级规范见 `ENVELOPE-FORMAT.md`。**手写的信封一律没有签名 → 一定被拒收**，别手写，用 `send`。

### D. 定位：和 MCP / A2A / 消息中间件的横向对比

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

### E. 网络档位与省 token 账本

```bash
python acp_net.py --syncthing-home <syncthing-home> status      # 看档位 + 实际走哪条路
python acp_net.py --syncthing-home <syncthing-home> mode auto   # 默认档（旧叫法 wan）
python acp_net.py --syncthing-home <syncthing-home> mode strict # 严格档（旧叫法 lan）
python acp_net.py --syncthing-home <syncthing-home> kick       # 换网后立刻重连
# <syncthing-home> = Syncthing 配置目录（含 config.xml）：
#   Windows 例 %USERPROFILE%\acp-home\syncthing ｜ Linux/macOS 例 ~/.config/syncthing
```

- 默认 `auto` 档实测走局域网直连（`<对端局域网地址>:22000 isLocal=True`），中继只 `Joined relay` 待命 ——
  **公开服务器是"备胎"，不是"主路"**；`strict` 完全不登记地址，代价是跨网找不到对方。
- 省 token：`--reply none` 不用回、`--reply answer` 需要回答、`digest` 一次读完。**`watch` 永远不调模型。**

### F. 部署注意


| 事项 | 说明 |
|---|---|
| **时钟要同步（NTP）** | 两台机器时间差太大，`expires_at` 会误判（把新消息当过期） |
| **共享文件夹必须平级、互不包含** | 嵌套会造成同一文件双份 |
| **删除会传播** | 双向同步下"删本机 = 删对端"；要单向保留就把一端设成 `send-only` |
| **重建身份后要重新信任** | `init --force` 会换密钥 ⇒ 对方那边立刻变成 `untrusted`，需重新带外核对 |
| **指纹变了要当心** | `trust` 遇到"新指纹 ≠ 已记录指纹"会拦下来，确认无误后加 `--force` 才更新（防中间人换人） |
| **`peers/` 谁都能写** | 名片在共享目录里，任何同步方都能覆盖它（低危）。将来可上 TOFU（首见锁定指纹，变了告警） |
| **`config.xml` 里有设备 ≠ 对方在线** | 判"通不通"要看实际证据：**收到过对方的信** > 对端 completion > 配置条目 |
| **别在生产用 `ACP_USERKEY_PASSPHRASE`** | 那是给自测用的环境变量；生产请用交互式口令输入，避免口令被子进程继承 |
| **审计 / 自测** | `acp.py audit` 校验哈希链；`python selftest.py` 用两个临时"机器"跑完整套流程（**项数以程序输出为准**） |

### G. 依赖与归属声明

- **通信层不是我们自研的**：跨主机通信**建立在 [Syncthing](https://github.com/syncthing/syncthing) 之上**
  （Syncthing 是由 Jakob Borg 与社区贡献者创建的开源连续文件同步工具，现由瑞典的非营利基金会
  Syncthing Foundation 与社区共同维护）。**同步层不是我们写的，我们不主张任何原创性** ——
  谨向 Syncthing 项目及其维护者致谢。我们加的只是一层**签名信封 + 哈希链审计**的薄脚本。
- **运行依赖**：Python 3.9+、`cryptography`、Syncthing（要跨机唤醒再加 OpenSSH，见第六步）。
- 本项目以 **MIT** 发布（见 `LICENSE`）；归属声明：**中文见本节上文**，英文见 [`ATTRIBUTION-EN.md`](ATTRIBUTION-EN.md)。

### H. 边界与免责（诚实说明）

- ⚠️ **正文落盘是明文**：Syncthing 的**传输**是端到端加密的（中继只看得到密文），但消息
  **落到共享目录里的文件是明文**。正文加密（X25519 + AES-GCM）落地前**不要用这条通道传敏感内容**。
- 同步目录的元数据对 Syncthing 中继可见；涉密请关公共中继、改用局域网或 Tailscale 内网。
- **审计链防"事后改"，不防"该记没记"**：有审计 ≠ 有追责。
- 本程序**不调用任何模型**，也不替你决定"要不要执行"；Agent 本身不可寻址，**可寻址的是机器**，身份由邮局代持。
- **能保证"送到"，不保证"叫醒"**：本项目**不内置唤醒通道，但已实测可用**（同机 CLI 互调 / 跨机 SSH 唤醒，
  命令见第六步），**它不是 ACP-lite 自带的**；对端没开机、或没挂 `watch` 时，你的信就只是在信箱里排队。

### I. 用 SSH 推送 GitHub（推荐）

在 Windows 上用 HTTPS 推送时，`git-remote-https` 可能因 `schannel` 凭证问题崩溃或弹出
`SEC_E_NO_CREDENTIALS`，导致无人值守的推送卡住。SSH 推送不经过这个组件，配置一次后可长期使用，
私钥也始终只留在本机。

1. **生成密钥**：每台机器、每个 agent 分别使用一把独立密钥，不要共用私钥。将 `<名字>` 和
   `<主机名>` 换成自己的标识：

   ```bash
   ssh-keygen -t ed25519 -C "<名字>@<主机名>" -f ~/.ssh/id_ed25519_<名字> -N ""
   ```

2. **添加公钥**：先查看生成的 `.pub` 公钥文件，再把它添加到 GitHub 的
   **Settings → SSH and GPG keys → New SSH key**。只有仓库 owner 能完成这一步；agent 不能自行
   给 GitHub 账户添加密钥。建议用 `<名字>@<主机名>` 作为 Title，便于日后区分和单独撤销。

3. **验证认证**：使用刚生成的私钥测试连接。

   ```bash
   ssh -i ~/.ssh/id_ed25519_<名字> -o IdentitiesOnly=yes -T git@github.com
   ```

   出现 `Hi <用户>! You've successfully authenticated...` 即成功；该命令以退出码 1 结束是正常的。

4. **切换远端地址**：把 HTTPS 地址改成 SSH 地址。

   ```bash
   git remote set-url origin git@github.com:<owner>/<repo>.git
   ```

注意事项：

- 私钥绝不外发、绝不提交到仓库；只把 `.pub` 公钥交给仓库 owner 添加。
- 多台机器同时维护同一分支时，推送前先 `git fetch` 并比对远端；遇到
  `! [rejected] ... (fetch first)` 时先 `git pull --rebase`，再推送。
- 受限环境可能禁止直接访问 GitHub 的 SSH 端口。作为特殊情况，可通过本机代理转发到
  `ssh.github.com:443`；具体代理命令按运行环境配置，不要把代理凭据写进仓库。
