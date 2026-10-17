#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ACP-lite 链路探针：记录"换网络时它自己怎么换路"的时间线。

用途：验证"同一内网 / 跨网络自动切换"——换 WiFi、换热点、换办公网时，
      每 N 秒记一行：本机 IP、实际用的连接地址与类型、是否局域网内、同步状态。

用法
  python acp_probe.py --syncthing-home D:\\LLM\\ACP-lite\\syncthing --minutes 20
  python acp_probe.py --syncthing-home ... --interval 5 --once     # 只采一次

输出：控制台 + 同目录 probe-<时间戳>.log（可随时中断，Ctrl+C）
"""

import argparse
import datetime
import json
import socket
import sys
import time
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path


def local_ips():
    ips = []
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if ip not in ips and not ip.startswith("127."):
                ips.append(ip)
    except OSError:
        pass
    return ips


def syncthing_state(home):
    root = ET.parse(Path(home) / "config.xml").getroot()
    key_node = root.find("./gui/apikey")
    api = key_node.text if key_node is not None else None
    out = {"connections": [], "folder": None}
    if not api:
        return out
    try:
        req = urllib.request.Request("http://127.0.0.1:8384/rest/system/connections",
                                     headers={"X-API-Key": api})
        with urllib.request.urlopen(req, timeout=6) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        for dev, info in (data.get("connections") or {}).items():
            if info.get("connected"):
                out["connections"].append({
                    "device": dev[:7], "address": info.get("address"),
                    "type": info.get("type"), "lan": info.get("isLocal"),
                })
    except Exception as exc:  # noqa: BLE001
        out["connections"] = [{"error": str(exc)}]
    try:
        req = urllib.request.Request("http://127.0.0.1:8384/rest/db/status?folder=acp-shared",
                                     headers={"X-API-Key": api})
        with urllib.request.urlopen(req, timeout=6) as resp:
            st = json.loads(resp.read().decode("utf-8"))
        out["folder"] = {"state": st.get("state"), "errors": st.get("errors"),
                         "needFiles": st.get("needFiles")}
    except Exception:  # noqa: BLE001
        pass
    return out


def sample(home):
    ts = datetime.datetime.now().strftime("%H:%M:%S")
    st = syncthing_state(home)
    ips = local_ips()
    parts = []
    for c in st["connections"]:
        if "error" in c:
            parts.append(f"连接查询失败:{c['error'][:40]}")
        else:
            parts.append(f"{c['device']}… {c['address']} 类型={c['type']} 局域网内={c['lan']}")
    f = st.get("folder") or {}
    line = (f"{ts}  本机IP={','.join(ips) or '?'}  "
            f"连接={' | '.join(parts) if parts else '（无已连接对端）'}  "
            f"同步={f.get('state')} 错误={f.get('errors')} 缺文件={f.get('needFiles')}")
    return line


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            pass
    p = argparse.ArgumentParser(prog="acp_probe", description="ACP-lite 链路探针")
    p.add_argument("--syncthing-home", required=True)
    p.add_argument("--interval", type=float, default=10.0, help="采样间隔秒（默认 10）")
    p.add_argument("--minutes", type=float, default=20.0, help="最多记录多少分钟（默认 20）")
    p.add_argument("--out", default=None, help="日志文件（默认 <syncthing-home>/probe-<时间>.log）")
    p.add_argument("--once", action="store_true", help="只采一次")
    args = p.parse_args(argv)

    home = Path(args.syncthing_home)
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    logpath = Path(args.out) if args.out else (home / f"probe-{stamp}.log")
    deadline = time.time() + args.minutes * 60
    print(f"探针启动：每 {args.interval:.0f} 秒一行，最多 {args.minutes:.0f} 分钟；日志 {logpath}")
    with open(logpath, "a", encoding="utf-8") as fh:
        fh.write(f"# ACP-lite 链路探针 开始 {datetime.datetime.now().isoformat(timespec='seconds')}\n")
        while True:
            line = sample(home)
            print(line)
            fh.write(line + "\n")
            fh.flush()
            if args.once or time.time() >= deadline:
                break
            time.sleep(args.interval)
    print(f"探针结束。日志：{logpath}")


if __name__ == "__main__":
    main()
