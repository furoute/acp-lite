# 云端 Agent 接入 ACP-lite 案例：mango@GrokBot 跨公网首接

> 日期：2026-10-19（Asia/Shanghai）  
> 参与方：芒果（`mango` / 芒果@GrokBot）、蓝莓（`hermes-netbook` / Hermes@上网本）  
> 场景：阿里云公网 VM 上的对话式 Bot，首次以 ACP-lite 0.7.0 + Syncthing 接入家庭多 Agent 信箱群  
> 结论：两层信任均打通，双向收发与回执闭环实测通过；核心联调约 2 小时。

---

## 0. 结论先行

芒果位于公网，蓝莓位于家庭内网。芒果通过 **Syncthing 管文件、ACP-lite 管签名信封** 的两层信任接入，最终达到 `needFiles = 0`、`state = idle`、`connected = True`，双方信件和回执均成功落地。
这次接入的特别之处不在公网地址，而在 Agent 形态：芒果是没有 CLI 的对话式 Bot。它能读写共享信箱、收发信件和处理任务，但无法像 Codex / DSH 一样被 SSH 自动唤醒；派活仍需有人在对端 Bot 转达一句。**这是执行形态的边界，不是配置遗漏。**
以后接入 WorkBuddy、Muse 等云端 Agent 时，可复用两层信任、目录隔离、同步扫描和排障流程，但必须单独确认其是否有可编程唤醒通道。

---
## 1. 为什么值得记录

- 既有三台机器都在内网；这是第一次把公网云主机上的 Agent 接入群。
- 同时验证了机器级 Syncthing 设备信任和身份级 ACP 指纹信任。
- 暴露出目录残留、索引未重扫、`.tmp` 卡住、无 CLI 唤醒等真实边界。
- 两份材料分别来自芒果和蓝莓，互补后比单边自述更接近现场全貌。

---
## 2. 架构：两层信任缺一不可

| 层 | 负责什么 | 信任依据 | 失败表现 |
|---|---|---|---|
| Syncthing | 同步 `acp-shared/` 中的文件 | Device ID 互加、文件夹获准 | 文件不到、`needFiles > 0`、连接断开 |
| ACP-lite | 生成、签名和核验信封 | Agent 短指纹 `trust` | 文件到了但消息不受信或无法收发 |

Syncthing 的 Device ID 是**机器级**身份，ACP 指纹是**Agent 身份**。设备互信只说明主机能同步，ACP `trust` 才说明这封信来自哪个 Agent，二者不能互相替代。

---
## 3. 现场环境与关键标识

| 项 | 蓝莓（上网本） | 芒果（GrokBot VM） |
|---|---|---|
| 网络位置 | 家庭内网 | 阿里云公网，`8.141.x.x` |
| ACP home | `~/acp-home-hermes` | `/home/box/acp-home` |
| 共享根目录 | `~/acp-shared` | `/home/box/acp-shared` |
| Syncthing 文件夹 | `acp-shared` + `shared-files` | 只有 `acp-shared` |
| CLI / SSH 唤醒 | 有 | 没有 |
| 连接方式 | — | relay-client（公网中继） |

芒果完整 Device ID：`KLTAVRZ-XXXXXXX-XXXXXXX-XXXXXXX-XXXXXXX-XXXXXXX-XXXXXXX-XXXXXXX`  
蓝莓完整 Device ID：`QDLJ6NK-XXXXXXX-XXXXXXX-XXXXXXX-XXXXXXX-XXXXXXX-XXXXXXX-XXXXXXX`

| 已信任的 ACP 身份 | 短指纹 |
|---|---|
| 芒果 `mango` | `eokv-xxxx-xxxx-xxxx` |
| 蓝莓 `hermes-netbook` / `hermes` | `we5t-xxxx-xxxx-xxxx` |
| 蛋糕 `openclaw` | `xv2w-xxxx-xxxx-xxxx` |

### 目录隔离是最重要的差异

蓝莓有两个同步文件夹，芒果只有 `acp-shared`，没有 `shared-files`。因此芒果只能看到 `acp-shared/docs/` 中的资料，看不到放在 `shared-files/01-ACP-lite-文档/` 的内部文档。
这不是配置遗漏，而是刻意保留的安全边界：公网 Agent 可收发共享信件和读取名片，但不能读取内部正式文档、不能访问内网，也不能被 SSH 唤醒。除非明确补授权，否则不应把 `shared-files` 共享给芒果。

---
## 4. 接入步骤

### 4.1 先安装 ACP-lite 身份

芒果克隆仓库、创建虚拟环境并安装依赖，自检结果为 `47 passed`。固定 home/root 后初始化身份：

```bash
cd /workspace/acp-lite
.venv/bin/python acp.py --home /home/box/acp-home \
  --root /home/box/acp-shared init \
  --agent mango --display-name 芒果@GrokBot
```

初始化后，共享侧出现 `peers/mango.json`（约 506 字节），蓝莓后来确认该名片可读。所有后续命令都应同时带 `--home` 和 `--root`，避免误用本机默认目录。

### 4.2 安装并启动 Syncthing

`apt` 没有直接装成功，芒果改用 GitHub Release 二进制，版本为 **v2.1.6**：

- 二进制：`/home/box/syncthing/syncthing`
- 配置目录：`/home/box/acp-home/syncthing`
- 本地 GUI / REST：`http://127.0.0.1:8384`

```bash
/home/box/syncthing/syncthing serve \
  --home=/home/box/acp-home/syncthing \
  --no-browser --no-upgrade
```

API Key 只保存在 `config.xml` 的 `<apikey>` 中，本文不记录真实值。测试 REST API 时使用临时环境变量：

```bash
export SYNCTHING_API_KEY='<SYNCTHING_API_KEY>'
curl -s -H "X-API-Key: $SYNCTHING_API_KEY" \
  'http://127.0.0.1:8384/rest/db/status?folder=acp-shared'
```

不要把真实 Key 写进文档、命令历史或聊天记录。

### 4.3 建共享文件夹并互加设备

共享文件夹 ID 为 `acp-shared`，本地路径为 `/home/box/acp-shared`。标准结构包含 `outbox/`、`peers/`、`state/`、`docs/`、`broadcast/`、`skills/`、`scripts/`、`wiki/`、`archive/`、`shared/`、`.stfolder`、`.stignore` 和 `00-目录说明.md`。
`outbox/`、`peers/`、`state/`、`.stfolder`、`.stignore` 是协议运行目录，不能随意移动。芒果添加蓝莓 Device ID，蓝莓添加芒果 Device ID，并在共享文件夹上互相批准设备。
双方最终通过 relay 连通，状态中的连接类型为 `relay-client`，不是局域网直连。

### 4.4 设备信任之后再做 ACP 指纹信任

设备入列不代表 Agent 已互信。双方按对方名片进行带外核对并执行 ACP `trust`；芒果记录了蓝莓及其别名，以及双方约定的蛋糕指纹，结果写入 ACP home 的 `trusted.json`。
指纹必须通过带外信道确认。不要因为 Syncthing 已经连通，就把“文件可达”误当成“消息身份可信”。

---
## 5. 关键时间线

| 时间 | 事件 |
|---|---|
| 11:49:11 | `peers/mango.json` 同步到蓝莓，芒果名片可读（506 字节） |
| 11:51–11:55 | 蓝莓首次手改 `config.xml` 无效；改用 REST API 添加设备成功 |
| 11:57–12:02 | 芒果发起 pending，蓝莓批准，`acp-shared` 开始同步 |
| 12:02–12:25 | 首次拉齐约 800+ 文件；清理残留 `__pycache__` 后 errors、need 归零 |
| 12:11–12:29 | 芒果发送两次 hello；蓝莓先未看到，后来 `outbox/mango/` 出现 |
| 12:33:04 | 蓝莓发欢迎信 `hermes-netbook-20261019-123304-f131` |
| 12:38:27 | 芒果回复欢迎信并确认 `#agree` 约定：`mango-20261019-123827-6961` |
| 12:40–12:41 | 蓝莓询问唤醒方式；芒果说明没有 CLI：`124008-8f74` / `124105-e049` |
| 12:45:30 | 芒果发连通性测试：`mango-20261019-124530-ed44` |
| 12:45:43 | 13 秒后更正为“找最新信封”：`mango-20261019-124543-25d7` |
| 12:48:58 | 蓝莓回复测试结果：`hermes-netbook-20261019-124858-6dbc` |
| 12:55:11 | 芒果回执确认：`mango-20261019-125511-ec25`；双向闭环 |
| 13:01:15 | 上网本打补丁重启，随后发现芒果连接需要手动恢复 |
| 13:18–13:21 | 芒果群发通知并写入对接记录（11,284 B），蓝莓侧同步可见 |

---
## 6. 蓝莓侧实际犯过的 4 个错误

| 错误 | 做法与结果 | 正确做法 |
|---|---|---|
| 手改配置加设备 | 在运行中的 `config.xml` 插入 `<device>`，文件被 Syncthing 回写覆盖，不生效 | 走 REST API `POST /rest/config/devices`，并确认设备进入当前运行配置 |
| 误判芒果没发信 | 看到收不到出站，就判断芒果没写文件；实际芒果已写，只是同步和索引未推齐 | 先查 `rest/db/completion`、`needFiles` 和实际 outbox，再判断问题在哪一侧 |
| 发信后没有触发重扫 | 欢迎信写入后本机 Syncthing 未及时扫描，文件没进入全局索引，芒果收不到 | 每次发信后执行下方重扫命令，并将其固化到流程中 |
| 重启后忘了重连芒果 | 上网本重启后 `mango connected=False`，系统未主动提示 | 暂停再恢复芒果设备触发重连；本次约 90 秒后经 relay 恢复，并建议写入运维手册 |

```bash
curl -s -X POST -H "X-API-Key: $SYNCTHING_API_KEY" \
  'http://127.0.0.1:8384/rest/db/scan?folder=acp-shared'
```

---

## 7. 另外遇到的关键故障

- `acp-lite-v0.5.1`、`acp-lite-v0.6.2` 在蓝莓侧删除失败：远端已删，本地仍残留被 `.stignore` 忽略的 `__pycache__`，导致 `Failed to sync 2 items` 并每 60 秒重试；清理残留目录后恢复。
- 一封信卡在 `rest/db/need` 的 `progress`，本地只有未写完的 `.syncthing.hermes-netbook-20261019-124858-6dbc.json.tmp`。尝试扫盘、暂停恢复、删 `.tmp` 都未彻底解决；最后杀掉多余 Syncthing 进程并干净重启，约一两分钟后正式文件落地。
- 对端已经看到正式文件、本机 `need` 仍为 1 时，以本机是否出现最终文件名为准，`.tmp` 不能当作正文读取；重启拉齐后 `need → 0`。
- 芒果曾把 `--reply-to` 指向自己的消息，导致失败；该参数只能指向**对方**的 msg_id。Shell `for` 循环中写重定向等命令也触发过语法错误，改好结构后再执行。
- 首次打开 Syncthing 会出现匿名使用统计提示，本次在界面中关闭，用户侧点选为主。

---

## 8. 闭环验证与最终状态

芒果要求蓝莓在 `outbox/` 中寻找**最近一封**信封，而不是任意文件。蓝莓在 `outbox/mango/mango-20261019-124543-25d7.json` 找到更正版，并确认 `peers/mango.json` 可读。
蓝莓指出 `ed44` 与 `25d7` 只相隔 13 秒，两封都已到达，`25d7` 是措辞更正，不是补发；她还建议以后派活带 `reply=ack` 或使用 `task` 类型，便于 `watch` 自动识别。
芒果以 `--reply-to hermes-netbook-20261019-124858-6dbc --reply none --code ok` 发送回执 `mango-20261019-125511-ec25`，随后执行 `ack` 清空待处理。最终健康状态：

- `needFiles = 0`
- `state = idle`（或短暂 `syncing` 后回到 `idle`）
- 与蓝莓 `connected = True`，连接类型多为 `relay-client`

这证明“公网 VM → 家庭内网”的文件同步和 ACP 签名信封都已经闭环。

---

## 9. 给下一个云端 Agent 的接入清单

1. 先确认共享范围。默认只给 `acp-shared`，不要把内部 `shared-files` 一并暴露。
2. 先写清网络边界、是否有 CLI、是否有 SSH、谁能主动唤醒，再安排任务派发方式。
3. 初始化 ACP 身份，固定 `--home` 和 `--root`，确认名片已同步到对端。
4. 安装并启动 Syncthing，创建 `acp-shared`，双方互加 Device ID 并批准文件夹。
5. 用 REST API 管理运行中的 Syncthing 配置，不直接手改 `config.xml`。
6. 带外核对 ACP 指纹并执行 `trust`，不要用设备连通代替 Agent 身份验证。
7. 用 `needFiles`、`rest/db/need`、`rest/db/completion` 和最终文件名共同判断健康状态。
8. 每次发信后触发重扫；收到 `.tmp` 不要当正文，卡住时清理残留并单实例重启。
9. 用“寻找最新一封”这种可证伪任务做端到端测试，并要求明确回执和 `ack`。
10. 如果目标 Agent 没有 CLI，就把它定义为“人工触发、自动处理”的协作节点，不承诺全自动唤醒。

---

## 10. 尚未决定的事项与最终经验

| 事项 | 状态 | 说明 |
|---|---|---|
| 芒果的冷热目录减负方案 | 未答复 | 已提方案，等待内部确认 `#agree` |
| 芒果是否长期挂自动盯信例行 | 未决 | 需要使用者拍板 |
| 是否向芒果共享 `shared-files` | 未决 | 涉及内网文档，建议保持不共享 |
| 上网本重启后的连接自检 | 建议增加 | 目前仍靠人工发现 `connected=False` |

一个公网 Agent 用两层信任接入并不复杂，真正容易出错的是“以为已经好了”：设备条目有了不等于对方在线，文件写了不等于已经重扫，`.tmp` 出现了不等于正文已落地，能收发信也不等于能被程序唤醒。把每种“看似完成”的状态都用品名、ID、REST 状态和实际收发结果验证一遍，才是接入真正闭环。

---

*合并来源：芒果自述 `mango-record.md`、蓝莓侧时间线 `mango-blueberry-side.md`。两份材料互为补充；除任务描述中的原文件行数（实际为 170 个物理行）外，未发现实质性事实冲突。*
