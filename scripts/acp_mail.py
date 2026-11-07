#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ACP-lite 邮件传输桥（给"公网邮箱当房间"用）

设计原则：**只做传输，不改语义**。
  · pull：把邮箱里带 [ACP-lite] 标签的邮件取出来，还原成 ACP 信封，
          写进 <root>/outbox/<from>/<id>.json —— 之后就交给原来的 watch 走验签/信任/去重/审计；
  · push：把 <root>/outbox/<自己>/ 里还没发过的信封，按房间约定的格式发出去；
  · card：把自己的名片当邮件发进房间。
因此 acp.py 一行都不用改，这条通道和 Syncthing 是并列的"运输工具"。

线格式（严格按《给 Codex 的 Gmail 信箱接入说明》，不要自创）
  信封邮件：主题 `[ACP-lite] <from> -> <to> <envelope-id>`
            正文 = 本地 outbox/<自己>/<id>.json 的**原文**（原样粘贴，不改空白、不转义）
  名片邮件：主题 `[ACP-lite] card <agent>`
            正文 = peers/<agent>.json 的**原文**

用法
  python acp_mail.py --home H --root R selftest     # 离线自检（不联网）
  python acp_mail.py --home H --root R card         # 发名片邮件
  python acp_mail.py --home H --root R push [--dry-run]
  python acp_mail.py --home H --root R pull
  python acp_mail.py --home H --root R sync --loop  # 收+发，常驻

配置：<home>/mail.json
  { "address": "you@gmail.com", "app_password": "xxxx xxxx xxxx xxxx",
    "room": "you@gmail.com",
    "imap_host": "imap.gmail.com", "imap_port": 993,
    "smtp_host": "smtp.gmail.com", "smtp_port": 465,
    "proxy": "http://127.0.0.1:7897" }
"""

import argparse
import base64
import imaplib
import json
import os
import re
import smtplib
import socket
import ssl
import sys
import time
from email.message import EmailMessage
from pathlib import Path
from urllib.parse import urlparse

TAG = "[ACP-lite]"
BEGIN = "[ACP-lite envelope v0.6]"
END = "[/ACP-lite envelope]"


def read_json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name("~syncthing~" + path.name + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


# ---------------------------------------------------------------- 代理隧道

def tunnel(proxy_url, host, port, timeout=30):
    """经 HTTP 代理建立到 host:port 的 CONNECT 隧道。国内直连 Gmail 通常不可达，这一步是必需的。"""
    u = urlparse(proxy_url)
    sock = socket.create_connection((u.hostname or "127.0.0.1", u.port or 8080), timeout)
    req = f"CONNECT {host}:{port} HTTP/1.1\r\nHost: {host}:{port}\r\n"
    if u.username:
        cred = base64.b64encode(f"{u.username}:{u.password or ''}".encode()).decode()
        req += f"Proxy-Authorization: Basic {cred}\r\n"
    req += "Proxy-Connection: keep-alive\r\n\r\n"
    sock.sendall(req.encode())
    buf = b""
    while b"\r\n\r\n" not in buf:
        chunk = sock.recv(4096)
        if not chunk:
            raise OSError("代理提前关闭了连接")
        buf += chunk
    status = buf.split(b"\r\n")[0].decode("latin-1")
    if " 200" not in status:
        raise OSError(f"代理 CONNECT 失败：{status}")
    return sock


class ProxiedIMAP4SSL(imaplib.IMAP4_SSL):
    proxy = None

    def _create_socket(self, timeout=None):
        if not self.proxy:
            return super()._create_socket(timeout)
        raw = tunnel(self.proxy, self.host, self.port, timeout or 30)
        return self.ssl_context.wrap_socket(raw, server_hostname=self.host)


class ProxiedSMTPSSL(smtplib.SMTP_SSL):
    proxy = None

    def _get_socket(self, host, port, timeout):
        if not self.proxy:
            return super()._get_socket(host, port, timeout)
        raw = tunnel(self.proxy, host, port, timeout)
        return self.context.wrap_socket(raw, server_hostname=host)


# ---------------------------------------------------------------- 邮件 <-> 信封

def subject_for(env):
    return f"{TAG} {env.get('from')} -> {env.get('to')} {env.get('id')}"


def build_message(cfg, env, raw_body=None, subject=None):
    """正文默认用"原始 JSON 文本"原样发出（与说明书一致）；不给原文时才序列化。"""
    body = raw_body if raw_body is not None else json.dumps(env, ensure_ascii=False)
    msg = EmailMessage()
    msg["From"] = cfg["address"]
    msg["To"] = cfg.get("room") or cfg["address"]
    msg["Subject"] = subject or subject_for(env)
    # UTF-8 正文：含中文时 Python 会自动用 quoted-printable，解码后与原文字节一致；
    # 不要用 7bit 硬发长行，否则被中间环节折行会破坏 JSON。
    msg.set_content(body, subtype="plain", charset="utf-8")
    return msg


def extract_envelope(raw_bytes):
    """从邮件正文还原 JSON（信封或名片）：正文原文优先，其次标记块，最后兜底扫描。"""
    import email
    from email import policy
    msg = email.message_from_bytes(raw_bytes, policy=policy.default)
    texts = []
    for part in msg.walk():
        if part.get_content_type() == "text/plain":
            try:
                texts.append(part.get_content())
            except Exception:  # noqa: BLE001
                payload = part.get_payload(decode=True) or b""
                texts.append(payload.decode("utf-8", "replace"))
    text = "\n".join(texts)
    for cand in (text.strip(), text):
        try:
            obj = json.loads(cand)
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            pass
    m = re.search(re.escape(BEGIN) + r"\s*(\{.*?\})\s*" + re.escape(END), text, re.S)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass
    for cand in re.findall(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", text, re.S):
        try:
            obj = json.loads(cand)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict) and obj.get("id") and obj.get("from"):
            return obj
    return None


def extract_card(raw_bytes):
    """名片邮件：正文就是名片 JSON。"""
    obj = extract_envelope(raw_bytes)
    return obj if obj and obj.get("agent") and obj.get("pub") is not None else None


def subject_kind(subject):
    """返回 ('card', agent) / ('envelope', None) / (None, None)。"""
    s = (subject or "").strip()
    if not s.startswith(TAG):
        return None, None
    m = re.match(rf"{re.escape(TAG)}\s+card\s+(\S+)\s*$", s, re.I)
    if m:
        return "card", m.group(1)
    if "->" in s:
        return "envelope", None
    return None, None


# ---------------------------------------------------------------- 收发

def connect_imap(cfg):
    cls = ProxiedIMAP4SSL
    cls.proxy = cfg.get("proxy")
    host = cfg.get("imap_host", "imap.gmail.com")
    port = int(cfg.get("imap_port", 993))
    m = cls(host, port, timeout=30)
    m.login(cfg["address"], cfg["app_password"])
    return m


def connect_smtp(cfg):
    cls = ProxiedSMTPSSL
    cls.proxy = cfg.get("proxy")
    host = cfg.get("smtp_host", "smtp.gmail.com")
    port = int(cfg.get("smtp_port", 465))
    s = cls(host, port, timeout=30, context=ssl.create_default_context())
    s.login(cfg["address"], cfg["app_password"])
    return s


def cmd_pull(args):
    home, root = Path(args.home), Path(args.root)
    cfg = read_json(home / "mail.json")
    if not cfg:
        die(f"缺少配置：{home / 'mail.json'}")
    state_path = home / "mail-state.json"
    state = read_json(state_path) or {}
    seen_uids = [str(u) for u in state.get("seen_uids", [])]
    imap = connect_imap(cfg)
    env_n = card_n = skipped = 0
    try:
        imap.select("INBOX")
        # 按主题搜，不用 UNSEEN —— 房间和 fu 的日常邮箱是同一个，他手点开过也不能漏
        typ, data = imap.uid("search", None, "SUBJECT", f'"{TAG}"')
        uids = (data[0] or b"").split()
        for uid in uids[-300:]:
            suid = uid.decode()
            if suid in seen_uids:
                continue
            typ, blob = imap.uid("fetch", uid, "(RFC822)")
            if typ != "OK" or not blob or not isinstance(blob[0], tuple):
                continue
            raw = blob[0][1]
            import email
            from email import policy
            head = email.message_from_bytes(raw, policy=policy.default)
            kind, card_agent = subject_kind(head.get("Subject"))
            if kind == "card":
                card = extract_card(raw)
                if not card:
                    skipped += 1
                else:
                    write_json(root / "peers" / f"{card.get('agent', card_agent)}.json", card)
                    card_n += 1
            elif kind == "envelope":
                env = extract_envelope(raw)
                if not env or not env.get("id") or env.get("from") == args.agent:
                    skipped += 1
                else:
                    target = root / "outbox" / str(env["from"]) / f"{env['id']}.json"
                    if target.exists():
                        skipped += 1
                    else:
                        write_json(target, env)
                        env_n += 1
            else:
                skipped += 1
            seen_uids.append(suid)
            imap.uid("store", uid, "+FLAGS", "(\\Seen)")
        state["seen_uids"] = seen_uids[-500:]
        write_json(state_path, state)
        print(f"pull 完成：信封 {env_n} 条、名片 {card_n} 张、跳过 {skipped} 条")
    finally:
        try:
            imap.logout()
        except Exception:  # noqa: BLE001
            pass


def cmd_push(args):
    home, root = Path(args.home), Path(args.root)
    cfg = read_json(home / "mail.json")
    if not cfg:
        die(f"缺少配置：{home / 'mail.json'}")
    state_path = home / "mail-state.json"
    state = read_json(state_path) or {}
    pushed = state.get("pushed", {})
    outbox = root / "outbox" / args.agent
    if not outbox.exists():
        print("自己没有待发消息")
        return
    pending = [p for p in sorted(outbox.glob("*.json")) if p.stem not in pushed]
    if not pending:
        print("没有新的待发消息")
        return
    if args.dry_run:
        for p in pending:
            env = read_json(p) or {}
            print(f"[dry-run] 将发送：{subject_for(env)}")
        return
    smtp = connect_smtp(cfg)
    try:
        for p in pending:
            env = read_json(p)
            if not env:
                continue
            # 按说明书：正文用本机信封文件**原文**，不改空白、不转义
            raw_text = p.read_text(encoding="utf-8")
            smtp.send_message(build_message(cfg, env, raw_body=raw_text))
            pushed[p.stem] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
            print(f"已发送：{subject_for(env)}")
    finally:
        try:
            smtp.quit()
        except Exception:  # noqa: BLE001
            pass
    state["pushed"] = pushed
    write_json(state_path, state)


def cmd_card(args):
    home, root = Path(args.home), Path(args.root)
    cfg = read_json(home / "mail.json")
    if not cfg:
        die(f"缺少配置：{home / 'mail.json'}")
    card_path = root / "peers" / f"{args.agent}.json"
    card = read_json(card_path)
    if not card:
        die(f"找不到名片：{card_path}（先运行 acp.py init）")
    subject = f"{TAG} card {args.agent}"
    raw_text = card_path.read_text(encoding="utf-8")
    if args.dry_run:
        print(f"[dry-run] 将发送名片邮件：{subject}")
        print(raw_text)
        return
    smtp = connect_smtp(cfg)
    try:
        smtp.send_message(build_message(cfg, None, raw_body=raw_text, subject=subject))
    finally:
        try:
            smtp.quit()
        except Exception:  # noqa: BLE001
            pass
    print(f"名片邮件已发送：{subject}")


def cmd_sync(args):
    while True:
        try:
            cmd_pull(args)
            cmd_push(args)
        except Exception as exc:  # noqa: BLE001
            print(f"[warn] sync 循环异常：{exc}")
        if not args.loop:
            return
        time.sleep(args.interval)


def cmd_selftest(args):
    """离线自检：按说明书的线格式构造邮件 → 用同一套解析还原 → 比对。不联网。"""
    ok = True

    def check(name, cond, detail=""):
        nonlocal ok
        ok = ok and bool(cond)
        print(f"  {'✅' if cond else '❌'} {name}" + (f"  — {detail}" if detail and not cond else ""))

    cfg = {"address": "you@gmail.com", "room": "you@gmail.com"}
    sample = {
        "version": "0.6", "id": "codex-desktop-20261005-210000-aaaa",
        "from": "codex-desktop", "to": "*", "type": "task",
        "payload": {"action": "infer", "data": "群里的中文与换行\n第二行", "timeout": 1800},
        "created_at": "2026-10-05T21:00:00+08:00",
        "x": {"hops": 0, "max_hops": 4, "idem": "codex-desktop-20261005-210000-aaaa",
              "requires": "none", "expires_at": "2026-10-06T21:00:00+08:00"},
    }
    # ① 信封邮件：正文 = 本机 outbox 文件的原文（模拟"原样粘贴"）
    raw_text = json.dumps(sample, ensure_ascii=False, indent=2)
    mail = build_message(cfg, sample, raw_body=raw_text).as_bytes()
    back = extract_envelope(mail)
    check("主题符合约定 [ACP-lite] <from> -> <to> <id>",
          subject_for(sample) == f"[ACP-lite] codex-desktop -> * {sample['id']}",
          subject_for(sample))
    check("收件方按主题识别为信封邮件", subject_kind(subject_for(sample))[0] == "envelope")
    check("正文原样还原成信封", back is not None and back["id"] == sample["id"])
    check("中文与换行无损（quoted-printable 解码正确）",
          back is not None and back["payload"]["data"] == sample["payload"]["data"])
    check("x 段（幂等/签名位）保留",
          back is not None and back["x"]["idem"] == sample["x"]["idem"])
    # ② 名片邮件：主题 [ACP-lite] card <agent>，正文 = 名片 JSON 原文
    card = {"agent": "codex-desktop", "display": "Codex@台式机", "pub": "AAAA",
            "fingerprint": "xxxx-xxxx-xxxx-xxxx", "mode": "signed"}
    cmail = build_message(cfg, None, raw_body=json.dumps(card, ensure_ascii=False),
                          subject=f"{TAG} card codex-desktop").as_bytes()
    kind, who = subject_kind(f"{TAG} card codex-desktop")
    check("名片主题解析正确", (kind, who) == ("card", "codex-desktop"), f"{kind}/{who}")
    check("名片正文还原正确", (extract_card(cmail) or {}).get("agent") == "codex-desktop")
    # ③ 兜底：正文是单行 JSON（没有标记块）也要能解析
    smashed = ("Subject: " + subject_for(sample) + "\n\n"
               + json.dumps(sample, ensure_ascii=False))
    check("单行 JSON 兜底解析",
          (extract_envelope(smashed.encode("utf-8")) or {}).get("id") == sample["id"])
    # ④ 无关邮件必须被忽略（房间和 fu 的日常邮箱是同一个）
    check("无关邮件不会被误判", subject_kind("Re: 周末聚餐") == (None, None))
    print("邮件通道自检" + ("全部通过 ✅" if ok else "存在失败 ❌"))
    return 0 if ok else 1


def die(msg, code=2):
    print(f"[错误] {msg}")
    sys.exit(code)


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            pass
    p = argparse.ArgumentParser(prog="acp_mail",
                                description="ACP-lite 邮件传输桥（公网邮箱当房间）")
    p.add_argument("--home", required=True, help="本机私有目录（mail.json 放在这里）")
    p.add_argument("--root", required=True, help="共享目录（与 acp.py 的 --root 相同）")
    p.add_argument("--agent", default="codex-desktop", help="自己的 agent 名")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("pull", help="取邮件 → 落进共享目录（交给 watch 处理）").set_defaults(func=cmd_pull)
    sp = sub.add_parser("push", help="把本地发件箱里没发过的信封发出去")
    sp.add_argument("--dry-run", action="store_true")
    sp.set_defaults(func=cmd_push)
    sc = sub.add_parser("card", help="发名片邮件（进房间报到用）")
    sc.add_argument("--dry-run", action="store_true")
    sc.set_defaults(func=cmd_card)
    ss = sub.add_parser("sync", help="收+发")
    ss.add_argument("--loop", action="store_true")
    ss.add_argument("--interval", type=float, default=60.0)
    ss.set_defaults(func=cmd_sync)
    sub.add_parser("selftest", help="离线自检，不联网").set_defaults(func=cmd_selftest)
    args = p.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
