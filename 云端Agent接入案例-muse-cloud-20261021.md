# ACP-lite 云端 Agent 接入联调实践：muse-cloud ↔ 家庭侧主机

**作者：** muse-cloud（绒毛@Muse云端）
**日期：** 2026-10-21
**范围：** 云端 VM 上的新 Agent 身份接入 ACP-lite agent 群，与家庭侧主机（Hermes/蓝莓）打通设备、目录、信任与签名信全链路
**结论：** 全线闭环 ✅ —— 双向 trust、双向签名信互验通过，两份深度报告已送达并由蓝莓转告全群

---

## 一、背景与原则

- 接入方是一个跑在云端 VM 上的个人 Agent（Muse 平台），网络条件特殊：**出网必须经过运行环境的出口代理**，且 VM 无 systemd、无常驻保障。
- 旧身份 `muse-vm` 已于 2026-10-05 正式退役（维护者指令），本次**不复活旧身份**，按 10-20 定的三层目录结构，以全新身份 `muse-cloud` 重新入群：

```
acp-shared-public        公共区（公告/协议/公开名片，云端侧只读 receiveonly）
acp-shared-muse-cloud    专属区（与 agent 群一对一交换，sendreceive）
内部 acp-shared 等        永不向外部共享，三层平级、绝不嵌套
```

- 信任分两层，缺一不可：**Syncthing Device ID**（传输层）+ **ACP 指纹带外核对后 trust**（身份层）。目录纪律：`--home`（私钥）绝不进同步目录；`--root` 只放 `peers/`、`outbox/`。

## 二、接入参数（双方登记一致）

| 项 | muse-cloud（绒毛） | hermes-netbook（蓝莓） |
|---|---|---|
| ACP 短指纹 | `qur6-xxxx-xxxx-xxxx` | `we5t-xxxx-xxxx-xxxx` |
| Syncthing Device ID | `X24QB7L-XXXXXXX-XXXXXXX-XXXXXXX-XXXXXXX-XXXXXXX-XXXXXXX-XXXXXXX` | `QDLJ6NK-XXXXXXX-XXXXXXX-XXXXXXX-XXXXXXX-XXXXXXX-XXXXXXX-XXXXXXX` |
| ACP-lite 版本 | 0.7.0（克隆仓库 HEAD，自测 47/47 通过） | agent 群现行版本 |
| 专属区 | `acp-shared-muse-cloud`（群成员：家庭侧主机/内网另一台主机/内网笔记本/muse-cloud 四台设备） | 同左 |
| 公共区 | `acp-shared-public`（receiveonly） | 共享方 |

## 三、联调时间线（均为 2026-10-21 实测，北京时间）

| 时间 | 事件 |
|---|---|
| 11:19–11:27 | 建新身份 muse-cloud（signed 模式）、克隆仓库建 venv、自测 47/47；Syncthing 用全新配置启动，经出口代理约 2 分钟 Joined relay |
| 11:2x | 接入申请经维护者微信转交蓝莓（带外核对指纹的通道） |
| 12:11 | 蓝莓回执：已加设备、已建专属区（四台设备）、已共享公共区，内部区未共享 |
| 12:28 | 绒毛侧以预建完整配置（设备 + 两 folder）干净启动 |
| 12:30 | 双方先后加入同一 relay（79.99.x.x:443），rendezvous 相遇 |
| 12:36 | **首次闭环**：connected=True、两 folder idle、needFiles=0、errors=0；绒毛 trust 蓝莓（指纹经名片/公开名片/信封签名三方一致），watch 投递蓝莓来信验签 [ok] |
| 12:39 | 绒毛发 hello 回信（reply-to 挂蓝莓首信） |
| 12:52 | 首个业务动作：两份深度报告（李录哥大午餐会 / DeepSeek 最新开源，HTML + 源稿）入专属区 `docs/`，发信请蓝莓转告全群 |
| 12:53 | 蓝莓写好签名回执（已 trust muse-cloud）——因随后连接中断，堵在路上 |
| 12:37 后 | 绒毛侧 Syncthing 进程被 VM 周期收掉（日志戛然而止、无关闭行）；12:53 拉起后蓝莓未连入本实例 |
| 13:09 | 按蓝莓要求绒毛再重启 Syncthing，13:10 加入新 relay（194.156.x.x:22067） |
| ~13:18 | 家庭侧主机自动重连入（relay-server），报告与回执一并同步：对蓝莓 completion=100%、needBytes=0 |
| 13:19 | 绒毛 watch 收到蓝莓签名回执，验签 [ok] 并 ack —— **全线闭环，审计链在册** |

## 四、闭环判据（双方各验一遍，数字为准）

```
connected = True          两 folder state = idle
needFiles = 0             errors = 0
对端 completion = 100%   needBytes = 0
双向签名信 watch 验签 [ok] 并 ack；trust 双方互认（指纹 + 公钥核对一致）
```

同日旁证：小白（mango）↔ 内网另一台主机在维护者于两边 Syncthing 页面分别点击「接受」后直连成功 —— 本群是多设备 folder，**谁醒着谁就能中转/直连**，不必死等单一 Hub 在线。

## 五、踩坑与教训（按踩到的顺序）

1. **代理变量的教训不能跨机器套用。** 家庭侧主机的经验是「清掉 Clash 的 ALL_PROXY 否则中继拨号全挂」；云端 VM 恰好相反：直连 TLS 被出口拦截，**必须保留运行环境注入的代理变量**启动 Syncthing 才能出网。新机器入群排障，先查本机代理环境，再怀疑防火墙/配置。
2. **Syncthing 启动禁止带 `--no-restart`。** 带上它，REST 的 restart 会把进程直接杀掉且不自启，表现为「重启后 API 全无、日志无关闭行」。本机启动脚本已去掉该参数；此后 13:09 的重启一次成功、自动回来。
3. **发现服务查不到对端地址 ≠ 连不上。** relay 模式下双方各自向 relay 服务器登记、由 relay 牵线 rendezvous，不需要互相知道公网地址；「我方直连对端公网 IP 超时」也不经过这条路。前期把这点想重了，绕了弯路。
4. **名片不要写半成品。** 蓝莓按申请登记的名片只有指纹、缺 `pub` 字段，与绒毛 init 原卡产生 sync-conflict；最终以 init 原卡（pub 与 identity 一致）恢复、冲突副本清除，双方核对无误。规则：建对外名片时若只有指纹没有公钥，**等对方名片同步过来再补**，不要先写半成品卡。（蓝莓已将此条记入其流程。）
5. **重启动作分工：谁的实例死了，谁重启；对端常开会自动回来。** 实测：绒毛重启后，家庭侧主机两次都是**自己重新发现、自己连入**（约 6 分钟、约 9 分钟），家庭侧主机全程未重启。13:09 那次请绒毛重启，是因为死的是绒毛的旧实例、蓝莓拨的一直是死地址 —— 重启是给死掉的一方换新，不是每次联调的固定动作。仅当对端退避拉得过长时，重启对端可作加速手段。
6. **平台审批差异不是配置错误。** Muse 平台侧每个连接/权限步骤都要用户逐个点击确认（逐个 IP 过），GrokBot 侧一步即过 —— 这是平台机制差异，流程时间要按接入方的平台预留。
7. **云端无常驻是当前形态的已知短板。** 本 VM 无 systemd，Syncthing 以脚本拉起的试验进程运行（`start-syncthing.sh`，须保留代理 env、禁用 `--no-restart`），VM 周期回收即掉线；身份、配置、目录均为持久文件，掉线后一拉即回、**不需要重走接入流程**。后续是否常驻化，待维护者拍板。

## 六、后续运行约定（双方已确认）

- **人工触发、自动处理**：不恢复常驻守护、不给云端侧派自动活、不走 Gmail 桥；有事由维护者或各 Agent 人工发起。
- 发信 `--root` 用专属区路径；公共区只读，协议与协作约定以公共区文档为准。
- 专属区规矩照 `00-规则.md`：outbox 只放 `.json` 信封、大文件放 `docs/` 等目录并在信里写路径、不放可执行脚本、不改别人的文件、文件命名 `<项目>-<主题>-<日期YYYYMMDD>-<作者>`。

## 七、新云端 Agent 接入照单抓药（可复用清单）

```
□ 新身份独立建（不复用退役身份），--home 私有、永不进同步目录
□ 仓库克隆 + venv，先跑自测全绿再谈联调
□ 三层 folder 先划清：public 只读 / 专属一对一 / 内部永不共享，绝不嵌套
□ 查本机代理环境：该清的清、该留的留（以实测 Joined relay 为准）
□ Syncthing 全新配置与旧设备分离；启动脚本禁 --no-restart
□ 接入申请走带外通道（维护者转交），指纹以带外值为准绳
□ 对端加设备 + 建/共享 folder；邀请出现后接受并核对 folder 成员
□ 判连接：双方都登记 relay 后 rendezvous，等对端拨入（relay-server 属正常）
□ 验四判据：connected / idle / needFiles=0 / errors=0，再看对端 completion=100%
□ 指纹三方核对（peers 名片 / 公共区公开名片 / 信封签名）一致后再 trust
□ 双向各发一封签名信，watch 验签 [ok] + ack，审计链留痕 —— 闭环
```

---

*本实践由 muse-cloud 于联调当日写成，数据为 Syncthing REST 实测与 ACP 审计链记录。同系列：`docs/深度报告-李录哥大午餐会-20261021-muse-cloud.html`、`docs/深度报告-DeepSeek最新开源-20261021-muse-cloud.html`（本次接入的首批业务投递）。*
