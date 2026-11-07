#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""跨机延迟实测：往共享文件夹写一个小文件，量到"对端确认拿到"的耗时。

为什么这么量：中继节点常常禁 ICMP（ping 不通但可用），所以 ping 不能当中继延迟的判据。
而 Syncthing 的 REST 会告诉我们"对端还缺多少字节"（/rest/db/completion 的 needBytes），
于是可以把它当成一个应用层的往返探针：文件写入 → 对端确认收到。

输出三段：
  T1 本地扫描+公告   ：写入文件 → 本机索引里出现该文件（needBytes 首次 > 0）
  T2 跨网往返        ：本机公告 → 对端确认拿到（needBytes 回到 0）
  T总               ：写入 → 对端确认

用法：
  python acp_latency.py --syncthing-home <目录> --device <对端ID> --folder shared-files
"""

import argparse
import json
import os
import sys
import time
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path


def api(home, path, timeout=10):
    key = ET.parse(Path(home) / "config.xml").getroot().find("./gui/apikey").text
    req = urllib.request.Request(f"http://127.0.0.1:8384{path}", headers={"X-API-Key": key})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main(argv=None):
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            pass
    p = argparse.ArgumentParser(prog="acp_latency")
    p.add_argument("--syncthing-home", required=True)
    p.add_argument("--device", required=True)
    p.add_argument("--folder", required=True)
    p.add_argument("--size-kb", type=int, default=64)
    p.add_argument("--timeout", type=float, default=60.0)
    args = p.parse_args(argv)

    folders = api(args.syncthing_home, "/rest/config/folders")
    f = next((x for x in folders if x.get("id") == args.folder), None)
    if not f:
        print(f"[错误] 找不到文件夹 {args.folder}")
        return 2
    path = Path(f["path"])
    name = f"latency-probe-{int(time.time())}.bin"
    target = path / name

    def need():
        c = api(args.syncthing_home,
                f"/rest/db/completion?folder={args.folder}&device={args.device}")
        return int(c.get("needBytes", 0))

    print(f"探针文件：{target}  ({args.size_kb} KB)")
    baseline = need()
    print(f"初始：对端还缺 {baseline} 字节")

    t0 = time.time()
    target.write_bytes(os.urandom(args.size_kb * 1024))
    t1 = None
    deadline = t0 + args.timeout
    while time.time() < deadline:
        n = need()
        if t1 is None:
            if n > baseline:
                t1 = time.time()
                print(f"  T1 本地扫描+公告：{(t1 - t0) * 1000:.0f} ms（对端此时缺 {n} 字节）")
        elif n <= baseline:
            t2 = time.time()
            print(f"  T2 跨网往返     ：{(t2 - t1) * 1000:.0f} ms")
            print(f"  T总             ：{(t2 - t0) * 1000:.0f} ms（写入 → 对端确认拿到）")
            return 0
        time.sleep(0.2)
    print(f"[超时] {args.timeout}s 内没等到对端确认（已建 T1={t1 is not None}）")
    return 1


if __name__ == "__main__":
    sys.exit(main())
