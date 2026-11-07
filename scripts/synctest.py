#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""大文件同步测速：盯着对端的完成度，自动测出传输耗时与速率。

用法：
  python synctest.py --syncthing-home D:\\LLM\\ACP-lite\\syncthing \
      --device <对端设备ID> --folder shared-files [--timeout 1800]

它做三件事：
  1. 等待对端"接受文件夹"（此时完成度会从 100% 掉下来，或者一直不动的 100% 很可疑）；
  2. 记录传输开始时刻；
  3. 每 5 秒打印进度，到 100% 时给出总耗时与平均速率。
"""

import argparse
import datetime
import json
import sys
import time
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path


def api_key(home):
    root = ET.parse(Path(home) / "config.xml").getroot()
    node = root.find("./gui/apikey")
    return node.text if node is not None else ""


def get(path, key):
    req = urllib.request.Request(f"http://127.0.0.1:8384{path}", headers={"X-API-Key": key})
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode("utf-8"))


def stamp():
    return datetime.datetime.now().strftime("%H:%M:%S")


def main(argv=None):
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            pass
    p = argparse.ArgumentParser(prog="synctest")
    p.add_argument("--syncthing-home", required=True)
    p.add_argument("--device", required=True)
    p.add_argument("--folder", required=True)
    p.add_argument("--timeout", type=int, default=1800)
    p.add_argument("--interval", type=float, default=5.0)
    p.add_argument("--log", default=None, help="同时写入这个文件（后台跑时用）")
    args = p.parse_args(argv)

    fh = open(args.log, "a", encoding="utf-8") if args.log else None

    def say(text):
        print(text)
        if fh:
            fh.write(text + "\n")
            fh.flush()

    key = api_key(args.syncthing_home)
    deadline = time.time() + args.timeout
    started = None
    base_pct = None
    last_bytes = None
    prev_totals, prev_t = None, None
    say(f"开始盯：folder={args.folder}  device={args.device[:7]}…  超时 {args.timeout}s")

    while time.time() < deadline:
        try:
            f = get(f"/rest/db/status?folder={args.folder}", key)
            c = get(f"/rest/db/completion?folder={args.folder}&device={args.device}", key)
            conns = get("/rest/system/connections", key).get("connections", {})
            info = conns.get(args.device, {})
            totals = (info.get("inBytesTotal", 0), info.get("outBytesTotal", 0))
        except Exception as exc:  # noqa: BLE001
            say(f"{stamp()} 查询失败：{exc}")
            time.sleep(args.interval)
            continue
        now_t = time.time()
        if prev_totals and prev_t:
            dt = now_t - prev_t
            if dt > 0:
                din = (totals[0] - prev_totals[0]) / dt
                dout = (totals[1] - prev_totals[1]) / dt
                if din > 1024 or dout > 1024:
                    say(f"{stamp()} 速率  收 {din/1e6:6.2f} MB/s  发 {dout/1e6:6.2f} MB/s")
        prev_totals, prev_t = totals, now_t
        pct = c.get("completion", 0.0)
        need = c.get("needBytes", 0)
        total = c.get("globalBytes", 0)
        if base_pct is None:
            base_pct = pct
            say(f"{stamp()} 初始完成度 {pct:.1f}%（本机全网 {total/1e6:.1f} MB，"
                f"对方还缺 {need/1e6:.1f} MB）")
            if pct >= 100:
                say("  → 对方已是 100%：要么它早就有这些文件，要么它还没接受该文件夹。")
        if need and need > 0 and started is None:
            started = time.time()
            say(f"{stamp()} ★ 传输开始（对方还缺 {need/1e6:.1f} MB）")
        if started is not None and need:
            # 进度按"剩余量"报；真正的速率看上面基于字节计数的采样行（这一行不再自作聪明算速率）
            say(f"{stamp()} {pct:5.1f}%  剩余 {need/1e6:7.1f} MB")
        last_bytes = need
        if started is not None and (pct >= 100 or need == 0):
            el = time.time() - started
            mb = (total or 0) / 1e6
            say(f"{stamp()} ✅ 传完：{mb:.1f} MB / {el:.1f} 秒 = 平均 {mb/el:.2f} MB/s"
                f"（{mb*8/el:.1f} Mbps）")
            return 0
        time.sleep(args.interval)
    say(f"{stamp()} 超时结束（{args.timeout}s 内没等到传输完成）")
    return 1


if __name__ == "__main__":
    sys.exit(main())
