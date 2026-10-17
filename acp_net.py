#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ACP-lite 网络档位切换：同一套协议，两种联网姿势

为什么需要它：ACP-lite 本身不依赖任何外部服务器，但**底层运输工具（Syncthing）**
需要在"找得到对方"上做选择：

  lan 档（家里、同一路由器下）
      · 用局域网广播互相发现 + 直连
      · 关掉全球发现与中继 → 不向任何公共服务器登记地址，真正"足不出户"
      · 代价：两台机器必须同一个局域网；换了网就找不到对方

  wan 档（跨网：出门 / 手机热点 / 与对端不在同一局域网）
      · 打开全球发现（电话簿，帮跨网的机器互相找到）+ 中继（直连失败时转发）
      · 代价：会向 Syncthing 的公共服务器登记地址；中继只在直连失败时用，且只看得到元数据
      · 这是"常开的那台机器（如上网本）也要加进来"时**必需**的档位

用法
  python acp_net.py --syncthing-home <syncthing 配置目录> mode lan
  python acp_net.py --syncthing-home <...> mode wan
  python acp_net.py --syncthing-home <...> status

设计原则：**换档只动运输工具，不动 ACP-lite 的协议、身份、历史与审计。**
"""

import argparse
import json
import shutil
import subprocess
import sys
import time
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

# auto  = 默认，让运输工具自己判断：同网就直连，跨网才去查电话簿/走中继（全自动）
# strict= 严格模式：完全不碰公共服务器（足不出户），代价是跨网时找不到对方
MODES = {
    "auto": {"global-ann-enabled": "true", "relays-enabled": "true", "local-ann-enabled": "true"},
    "strict": {"global-ann-enabled": "false", "relays-enabled": "false", "local-ann-enabled": "true"},
}
ALIASES = {"wan": "auto", "lan": "strict"}   # 旧叫法保留，避免忽然改口


def find_syncthing():
    exe = shutil.which("syncthing")
    if exe:
        return exe
    base = Path.home() / "AppData/Local/Microsoft/WinGet/Packages"
    hits = sorted(base.glob("Syncthing.Syncthing_*/**/syncthing.exe"))
    if hits:
        return str(hits[-1])
    for cand in ("/usr/bin/syncthing", "/usr/local/bin/syncthing"):
        if Path(cand).exists():
            return cand
    raise SystemExit("[错误] 找不到 syncthing 可执行文件")


def cli(exe, home, *args, capture=False):
    cmd = [exe, "-H", str(home), "cli", *args]
    proc = subprocess.run(cmd, capture_output=capture, text=True, encoding="utf-8",
                          errors="replace")
    if proc.returncode != 0 and not capture:
        print(f"[warn] 命令返回 {proc.returncode}: {' '.join(args)}")
    return (proc.stdout or "").strip()


def read_config(home):
    return ET.parse(Path(home) / "config.xml").getroot()


def flag(root, name):
    node = root.find(f"./options/{name}")
    return (node.text or "").strip().lower() if node is not None else "?"


def show_status(home):
    root = read_config(home)
    g, r, l = flag(root, "globalAnnounceEnabled"), flag(root, "relaysEnabled"), \
        flag(root, "localAnnounceEnabled")
    mode = "strict（严格：完全不碰公共服务器）" if g == "false" and r == "false" else \
        ("auto（自动：同网直连、跨网自动回退）" if g == "true" and r == "true" else "自定义/混合")
    print(f"当前档位：{mode}")
    print(f"  局域网发现 localAnnounceEnabled = {l}")
    print(f"  全球发现   globalAnnounceEnabled = {g}   （电话簿；同网时用不上它）")
    print(f"  中继       relaysEnabled         = {r}   （直连失败时的备用转发）")
    if g == "true" and r == "true":
        print("  说明：这两个开着**不代表就会走外网**——同网时依然是局域网直连，")
        print("        它们只在'直连不上'时才启用。这就是自动判断。")
    gui = root.find("./gui/apikey")
    if gui is not None and gui.text:
        try:
            req = urllib.request.Request("http://127.0.0.1:8384/rest/system/connections",
                                         headers={"X-API-Key": gui.text})
            with urllib.request.urlopen(req, timeout=8) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            print("  当前连接：")
            for dev, info in (data.get("connections") or {}).items():
                if info.get("connected"):
                    print(f"    {dev[:7]}…  {info.get('address')}  类型={info.get('type')}"
                          f"  局域网内={info.get('isLocal')}")
        except Exception as exc:  # noqa: BLE001
            print(f"  （查连接失败，Syncthing 可能没在跑：{exc}）")


def set_mode(home, mode):
    mode = ALIASES.get(mode, mode)
    exe = find_syncthing()
    for key, value in MODES[mode].items():
        cli(exe, home, "config", "options", key, "set", value)
    # 换网后想快一点重连：把重试间隔从默认 20s 压到 5s（失败时更勤快地再试一次）
    # 注意 CLI 里这个属性的名字是 reconnect-intervals（对应 config 里的 reconnectionIntervalS）
    cli(exe, home, "config", "options", "reconnect-intervals", "set", "5")
    print(f"已切到 {mode} 档。")
    show_status(home)


def api(home, path, method="GET"):
    root = Path(home)
    key_node = ET.parse(root / "config.xml").getroot().find("./gui/apikey")
    req = urllib.request.Request(f"http://127.0.0.1:8384{path}", method=method,
                                 headers={"X-API-Key": key_node.text if key_node is not None else ""})
    with urllib.request.urlopen(req, timeout=10) as resp:
        body = resp.read().decode("utf-8")
    return json.loads(body) if body.strip().startswith("{") else body


def api_json(home, path, method="GET", payload=None, timeout=10):
    """REST 封装：支持 JSON 数组响应与 JSON 请求体（api() 只认对象响应，不够用）。"""
    key_node = ET.parse(Path(home) / "config.xml").getroot().find("./gui/apikey")
    headers = {"X-API-Key": key_node.text if key_node is not None else ""}
    data = None
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(f"http://127.0.0.1:8384{path}", method=method,
                                 data=data, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read().decode("utf-8").strip()
    if not body:
        return None
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        return body


def cmd_kick(home, wait=90):
    """换网之后想立刻重连：重启运输工具，强制重新发现 + 重新拨号。

    为什么需要它：正常重连要走"发现刷新 → 拨号 → 失败退避（默认约 40 秒一轮）"，
    被动等待时最长要几分钟；主动踢一脚能把这段时间压到 1 分钟左右。
    """
    print("踢一脚：重启 Syncthing，强制立刻重新发现与拨号……")
    t0 = time.time()
    api(home, "/rest/system/restart", method="POST")
    while time.time() - t0 < wait:
        time.sleep(5)
        try:
            conns = api(home, "/rest/system/connections").get("connections", {})
        except Exception:  # noqa: BLE001
            continue
        live = [c for c in conns.values() if c.get("connected")]
        if live:
            addr, kind = live[0].get("address"), live[0].get("type")
            print(f"已重连：{time.time() - t0:.0f} 秒  {addr}  类型={kind}  "
                  f"局域网内={live[0].get('isLocal')}")
            return
    print(f"{wait} 秒内仍未连上——先确认对方也在线、且档位不是 strict。")


def cmd_redial(home, wait=120):
    """强制重拨：对每个对端"暂停→恢复"，逼连接管理器立刻重新尝试。

    为什么需要它（2026-10-06 实测）：跨网时出现过"两边都健康、但连接管理器不再重试"的状态——
    日志里零条拨号尝试，重启整个 Syncthing 也没触发（15:47 那次重启就没拨）。
    而"暂停/恢复设备"直接让它重新拨号：**16 秒就连上了**。比 kick 更轻、更准。
    """
    me = (api_json(home, "/rest/system/status") or {}).get("myID", "")
    devs = [d for d in (api_json(home, "/rest/config/devices") or [])
            if d.get("deviceID") != me]
    if not devs:
        print("没有配置任何对端设备。")
        return
    print(f"对 {len(devs)} 个对端执行『暂停 → 恢复』以强制重拨……")
    t0 = time.time()
    for d in devs:
        did = d["deviceID"]
        for paused in (True, False):
            try:
                api_json(home, f"/rest/config/devices/{did}", method="PATCH",
                         payload={"paused": paused})
            except Exception as exc:  # noqa: BLE001
                print(f"  {did[:7]}… 设置失败：{exc}")
            time.sleep(2)
    while time.time() - t0 < wait:
        time.sleep(4)
        try:
            conns = (api_json(home, "/rest/system/connections") or {}).get("connections", {})
        except Exception:  # noqa: BLE001
            continue
        live = [c for c in conns.values() if c.get("connected")]
        if live:
            c = live[0]
            print(f"已重连：{time.time() - t0:.0f} 秒  {c.get('address')}  "
                  f"类型={c.get('type')}  局域网内={c.get('isLocal')}")
            return
    print(f"{wait} 秒内仍未连上——检查双方是否都在线、档位是否为 auto、以及发现服务是否可达。")


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            pass
    p = argparse.ArgumentParser(prog="acp_net", description="ACP-lite 网络档位切换（lan / wan）")
    p.add_argument("--syncthing-home", required=True, help="Syncthing 的配置目录（-H 那个）")
    sub = p.add_subparsers(dest="cmd", required=True)
    sm = sub.add_parser("mode", help="切档：lan=同局域网且不碰公共服务器 / wan=跨网可用")
    sm.add_argument("value", choices=sorted(list(MODES) + list(ALIASES)))
    sub.add_parser("status", help="看当前档位与连接")
    sk = sub.add_parser("kick", help="换网后立刻重连（重启运输工具，强制重新发现）")
    sk.add_argument("--wait", type=int, default=90, help="最多等多少秒（默认 90）")
    sr = sub.add_parser("redial", help="强制重拨（暂停/恢复设备，比 kick 更轻更准）")
    sr.add_argument("--wait", type=int, default=120)
    args = p.parse_args(argv)
    home = Path(args.syncthing_home)
    if args.cmd == "mode":
        set_mode(home, args.value)
    elif args.cmd == "kick":
        cmd_kick(home, args.wait)
    elif args.cmd == "redial":
        cmd_redial(home, args.wait)
    else:
        show_status(home)


if __name__ == "__main__":
    main()
