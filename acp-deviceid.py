#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""acp-deviceid — 生成 Syncthing 设备 ID（供 ACP-lite 群成员互相添加使用）

背景
    接入 ACP-lite 群时，除了 ACP 自己的「名片指纹」（短/全长），
    跨机同步层 Syncthing 还需要一个「设备 ID」（Device ID）。
    Hermes / Muse 把自己机器的设备 ID 发给用户，用户再转给 Codex 互相添加。
    本脚本让我们这台机器也能生成同样的东西，且**不依赖 Syncthing 可执行文件**。

原理（已用真实数据验证）
    Syncthing 设备 ID = base32(SHA-256(DER 编码的 TLS 证书)) + Luhn32 校验位，
    然后每 7 个字符用 '-' 连接，共 8 组 56 字符（不含连字符）。

    关键细节（我第一版算错过，记下来免得后人再踩）：
      · 校验位不是"整串加 1 位"，而是**每 13 个字符插 1 位 Luhn32**；
      · Luhn32 的字母表是 base32 的 ABCDEFGHIJKLMNOPQRSTUVWXYZ234567；
      · 最终是 56 字符 = 4 组 (13+1)，再按每 7 字符切分显示成 8 段。

用法
    python acp-deviceid.py                          # 用默认证书路径
    python acp-deviceid.py --cert D:\\path\\cert.pem  # 指定证书
    python acp-deviceid.py --config <config.xml>    # 直接从 Syncthing 配置里读（推荐）
"""

import argparse
import base64
import hashlib
import pathlib
import re
import sys

ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567"

# 常见 Syncthing 配置位置（Windows）
DEFAULT_CANDIDATES = [
    r"%LOCALAPPDATA%\Syncthing",
    r"%APPDATA%\Syncthing",
    r"%USERPROFILE%\.config\syncthing",
]


def luhn32(chunk: str) -> str:
    """Syncthing 的 Luhn mod N 校验位（N = 32）。"""
    factor, total, n = 1, 0, len(ALPHABET)
    for ch in reversed(chunk):
        codepoint = ALPHABET.index(ch)
        addend = factor * codepoint
        factor = 1 if factor == 2 else 2
        addend = (addend // n) + (addend % n)
        total += addend
    remainder = total % n
    if remainder != 0:
        remainder = n - remainder
    return ALPHABET[remainder]


def luhnify(s: str, chunk_size: int = 13) -> str:
    """每 chunk_size 个字符插一个校验位。"""
    out = []
    for i in range(0, len(s), chunk_size):
        chunk = s[i : i + chunk_size]
        out.append(chunk + luhn32(chunk))
    return "".join(out)


def device_id_from_cert(cert_path: pathlib.Path) -> str:
    """从 PEM 证书算设备 ID。"""
    raw = cert_path.read_bytes()
    # 剥掉 PEM 头尾，取 base64 正文
    b64 = b"".join(
        line for line in raw.splitlines() if not line.startswith(b"-----")
    )
    der = base64.b64decode(b64)
    digest = hashlib.sha256(der).digest()
    plain = base64.b32encode(digest).decode("ascii").rstrip("=")
    luhnified = luhnify(plain)
    return "-".join(luhnified[i : i + 7] for i in range(0, len(luhnified), 7))


def find_cert_dir(explicit: str | None) -> pathlib.Path | None:
    """定位含 cert.pem 的 Syncthing 配置目录。"""
    import os

    cands = [explicit] if explicit else DEFAULT_CANDIDATES
    for c in cands:
        if not c:
            continue
        p = pathlib.Path(os.path.expandvars(c))
        if (p / "cert.pem").exists():
            return p
    return None


def read_own_id_from_config(cfg: pathlib.Path) -> tuple[str | None, list[tuple[str, str]]]:
    """从 config.xml 读本机（无 name 或 name 匹配主机名）与远端设备。"""
    import os

    text = cfg.read_text(encoding="utf-8", errors="replace")
    own, peers = None, []
    host = os.environ.get("COMPUTERNAME", "")
    for m in re.finditer(r'<device id="([^"]*)"([^>]*)>', text):
        did, attrs = m.group(1), m.group(2)
        if not did:
            continue
        nm = re.search(r'name="([^"]*)"', attrs)
        name = nm.group(1) if nm else ""
        if name and (name.upper() == host.upper() or name == ""):
            own = did
        elif name:
            peers.append((name, did))
    return own, peers


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            pass

    ap = argparse.ArgumentParser(
        description="生成 Syncthing 设备 ID（ACP-lite 群互通用）"
    )
    ap.add_argument("--cert", help="cert.pem 路径")
    ap.add_argument("--dir", help="Syncthing 配置目录（含 cert.pem）")
    ap.add_argument("--config", help="config.xml 路径（可列出全部设备）")
    args = ap.parse_args()

    print("=== 本机 Syncthing 设备 ID ===\n")

    # 优先从 cert.pem 精算
    ctx = find_cert_dir(args.dir or (str(pathlib.Path(args.cert).parent) if args.cert else None))
    if args.cert:
        ctx = pathlib.Path(args.cert).parent
    if ctx and (ctx / "cert.pem").exists():
        did = device_id_from_cert(ctx / "cert.pem")
        print(f"  设备 ID : {did}")
        print(f"  证书    : {ctx / 'cert.pem'}")
    else:
        print("  [未找到 cert.pem]")
        print("  提示：用 --dir 指定 Syncthing 配置目录，或用 --cert 指定证书。")
        print("  候选路径：")
        for c in DEFAULT_CANDIDATES:
            print(f"    - {c}")
        print()

    # 若给了 config.xml，顺便列出所有已知设备
    cfg = pathlib.Path(args.config) if args.config else (ctx / "config.xml" if ctx else None)
    if cfg and cfg.exists():
        own_cfg, peers = read_own_id_from_config(cfg)
        print("\n=== 本机 config.xml 中已知的设备 ===")
        if own_cfg:
            print(f"  [本机] {'(hostname match)':<18} {own_cfg}")
        if peers:
            for name, did in peers:
                print(f"         {name:<18} {did}")
        if not own_cfg and not peers:
            print("  （config.xml 里没有已配置的设备）")

    print("\n提示：把上面这串设备 ID 发给群友（Codex 会转给对端），")
    print("      对端在 Syncthing 里「添加远程设备」后，两边都要接受才算连上。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
