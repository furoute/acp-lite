#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ACP-lite (Agent Connect Personal) — v0.4 draft

跨主机 Agent 互联的"邮局"最小实现。依赖：Python 3.9+；cryptography 可选
（缺失时降级为"无签名"并明确告警，便于先跑通链路）。

名字说明：本项目全称 Agent Connect Personal（最后一个 P 亦可读作 Peace）；
与 Zed 的 Agent Client Protocol、OpenAI+Stripe 的 Agentic Commerce Protocol、
IBM 已归档的 Agent Communication Protocol 无关。对外引用请带上全称。

四条铁律
  1. 同机继续用原有 ACP-Lite 文件通道；本程序不读不写 mailbox/。
  2. 跨机只共享一个目录（Syncthing / Tailscale / 网盘 / U 盘皆可）；
     每个 agent 只写自己的 outbox/<自己>/，别人的只读（单写者）。
  3. 私钥不进共享目录、不进 agent 上下文；"写/发/付/删"必须由人
     签一张一次性放行票，agent 自己签的不算。
  4. 收信不调用模型：watch 只落盘 + 记审计；花不花 token 由人和定时任务决定。
  5. 缺 cryptography 时 fail-closed：无签名消息**默认拒收**（三家评审一致意见）。

目录
  --home（本机私有，切勿同步）              --root（跨机共享，Syncthing 同步这个）
    identity.json   机器身份 Ed25519          peers/<agent>.json          名片(含公钥/指纹)
    userkey.json    L2 人密钥(口令加密)        outbox/<agent>/<msgid>.json 单写者发件箱
    inbox/<msgid>.json  已投递（本地生成）
    approvals/<msgid>.json  已签发放行票
    audit.jsonl     哈希链审计
    STOP            刹车文件（存在即停一切出口）
"""

import argparse
import base64
import datetime
import hashlib
import json
import os
import secrets
import sys
import time
from pathlib import Path

try:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import (
        Ed25519PrivateKey,
        Ed25519PublicKey,
    )
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    HAVE_CRYPTO = True
except Exception:  # noqa: BLE001
    HAVE_CRYPTO = False

NAME = "ACP-lite (Agent Connect Personal)"
VERSION = "0.7.0"  # 0.7.0 = 跨主机 SSH 唤醒里程碑（信封字段与 0.6.2 相同，不改协议格式）
MAX_HOPS = 4
REQUIRES = ("none", "read", "write", "send", "pay", "delete")
GATED = ("write", "send", "pay", "delete")  # 必须有人签发放行票的出口动作
REPLY_KINDS = ("none", "ack", "answer")     # 省 token 用：none=不用回 / ack=回执即可 / answer=需要回答
DEFAULT_TTL = 86400
UNSIGNED_WARN = "!! 未安装 cryptography，本机降级为无签名模式（仅用于先跑通链路）"


# ---------------------------------------------------------------- 基础工具

def now():
    return datetime.datetime.now().astimezone()


def _nodename():
    """跨平台取主机名（Windows 上 os.uname() 不存在）。"""
    getter = getattr(os, "uname", None)
    return getter().nodename if getter else "localhost"


def now_iso():
    return now().isoformat(timespec="seconds")


def parse_iso(text):
    """解析 ISO 时间；无时区的按本机时区补全（跨实现互通时很常见）。"""
    try:
        dt = datetime.datetime.fromisoformat(str(text))
    except (TypeError, ValueError):
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=now().tzinfo)


def canonical(obj):
    """签名用的确定性序列化（键排序、无空格）。"""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def b64e(raw):
    return base64.b64encode(raw).decode("ascii")


def b64d(text):
    return base64.b64decode(text)


def read_json(path):
    try:
        # utf-8-sig：兼容 PowerShell 写出的 BOM
        return json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None


def write_json(path, data):
    """原子写入：先写 .tmp 再 replace（Syncthing 同步目录里必须这样做）。"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # 前缀 ~syncthing~ 属于 Syncthing 保留命名空间，会被排除同步；
    # 否则这个中间态可能被同步到对端（DSH 用文件监视器实测捕获过）。
    tmp = path.with_name("~syncthing~" + path.name + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def fingerprint(pub_raw):
    """公钥指纹：SHA-256 -> base32 -> 16 字符，按 4-4-4-4 分组，便于口头核对。"""
    digest = hashlib.sha256(pub_raw).digest()
    text = base64.b32encode(digest).decode("ascii").rstrip("=").lower()[:16]
    return "-".join(text[i : i + 4] for i in range(0, 16, 4))


def fingerprint_full(pub_b64):
    """全长指纹（完整 SHA-256，base32）。短码用于人读，全长用于机器比对。"""
    try:
        digest = hashlib.sha256(b64d(pub_b64)).digest()
        return base64.b32encode(digest).decode("ascii").rstrip("=").lower()
    except Exception:  # noqa: BLE001
        return ""


def audit(home, event, **fields):
    """append-only 哈希链审计：改一条，后面全断。"""
    path = Path(home) / "audit.jsonl"
    head_path = Path(home) / "state" / "audit-head.json"
    head = read_json(head_path) or {}
    prev, seq = head.get("hash", "genesis"), int(head.get("seq", 0))
    if not head and path.exists():
        # 首次或缓存丢失时回退全量扫描（之后走缓存，避免 O(n)）
        try:
            for line in path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    rec = json.loads(line)
                    prev = rec.get("hash", prev)
                    seq = int(rec.get("seq", seq))
        except (OSError, json.JSONDecodeError, ValueError):
            pass
    rec = {"seq": seq + 1, "ts": now_iso(), "event": event, **fields, "prev": prev}
    rec["hash"] = hashlib.sha256(prev.encode("utf-8") + canonical(rec)).hexdigest()[:32]
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    write_json(head_path, {"hash": rec["hash"], "seq": rec["seq"]})
    return rec


# ---------------------------------------------------------------- 身份与签名

def identity_path(home):
    return Path(home) / "identity.json"


def load_identity(home, required=True):
    ident = read_json(identity_path(home))
    if not ident and required:
        die("未初始化：请先运行  acp.py init --agent <名字>")
    return ident


def sign_envelope(env, ident):
    if not HAVE_CRYPTO:
        return env
    priv = Ed25519PrivateKey.from_private_bytes(b64d(ident["priv"]))
    sig = priv.sign(canonical(env))
    env.setdefault("x", {})["sig"] = {
        "alg": "ed25519",
        "key": ident["fingerprint"],
        "value": b64e(sig),
    }
    return env


def verify_envelope(env, root, allow_unsigned=False):
    """返回 (ok: bool, reason: str)。缺 cryptography 时默认 fail-closed（拒收）。"""
    x = env.get("x") or {}
    sig = x.get("sig")
    if not HAVE_CRYPTO:
        # 无签名模式不是"放行"，而是"验不了"。默认拒收，避免静默信任旁路。
        return (True, "unsigned-mode") if allow_unsigned else (False, "unsigned")
    if not sig:
        return False, "unsigned"
    card = read_json(Path(root) / "peers" / f"{env.get('from')}.json")
    if not card or not card.get("pub"):
        return False, "no-card"
    body = json.loads(json.dumps(env))
    body.get("x", {}).pop("sig", None)
    try:
        pub = Ed25519PublicKey.from_public_bytes(b64d(card["pub"]))
        pub.verify(b64d(sig["value"]), canonical(body))
    except Exception:  # noqa: BLE001
        return False, "bad-signature"
    if card.get("fingerprint") != sig.get("key"):
        return False, "key-mismatch"
    return True, "ok"


def local_mode():
    return "signed" if HAVE_CRYPTO else "unsigned"


def check_mode_consistency(home):
    """本机当前模式与身份/名片记录的模式不一致时告警（换了 Python 环境就会出现）。"""
    ident = read_json(identity_path(home)) or {}
    recorded = ident.get("mode") or ("signed" if ident.get("signed") else "unsigned")
    if ident and recorded != local_mode():
        print(f"[告警] 身份记录的模式是 {recorded}，但本机当前是 {local_mode()}。"
              f"这会让名片与实际签名能力不符——建议重新 init 或补齐 cryptography。")
        return False
    return True


def trusted_fingerprint(home, agent):
    return (read_json(Path(home) / "trusted.json") or {}).get(agent)


def make_envelope(me, to, mtype, data, action, requires, ttl, hops, reply_to, timeout,
                  max_hops=MAX_HOPS, reply="answer", code=None):
    created = now()
    mid = f"{me}-{created:%Y%m%d-%H%M%S}-{secrets.token_hex(2)}"
    env = {
        "version": VERSION,
        "id": mid,
        "from": me,
        "to": to,
        "type": mtype,
        "payload": {"action": action, "data": data, "timeout": timeout},
        "created_at": created.isoformat(timespec="seconds"),
        "x": {
            "msg_id": mid,
            "hops": hops,
            "max_hops": max_hops,
            "expires_at": (created + datetime.timedelta(seconds=ttl)).isoformat(timespec="seconds"),
            "idem": mid,
            "requires": requires,
            "reply": reply,
        },
    }
    if reply_to:
        env["x"]["reply_to"] = reply_to
        # v0.7 待定项：顶层也放一份 reply_to（老端读 x.reply_to，不认识的字段会被忽略，故向后兼容）
        env["reply_to"] = reply_to
    if code:
        # v0.7 待定项：可选机器可读状态码（提案词表：ok / fail / need-info / partial）
        env["code"] = code
    return env


# ---------------------------------------------------------------- 命令实现

def die(msg, code=2):
    print(f"[错误] {msg}")
    sys.exit(code)


def cmd_init(args):
    home, root = Path(args.home), Path(args.root)
    home.mkdir(parents=True, exist_ok=True)
    for sub in ("peers", "outbox", "state"):
        (root / sub).mkdir(parents=True, exist_ok=True)
    for sub in ("inbox", "approvals"):
        (home / sub).mkdir(parents=True, exist_ok=True)
    if identity_path(home).exists() and not args.force:
        die(f"已存在身份文件：{identity_path(home)}（确要重建请加 --force）")
    # DSH 在入群时踩到：--home 传错（例如指到用户主目录）时，会静默在错误位置建好一整套身份。
    # 这里加一道"目标目录看起来不是 ACP-lite 的 home"的拦截，默认拒建，确认后加 --force。
    if home.exists():
        known = {"identity.json", "inbox", "approvals", "state", "trusted.json",
                 "audit.jsonl", "STOP", "userkey.json", "shared"}
        unexpected = sorted(p.name for p in home.iterdir() if p.name not in known)
        if unexpected and not args.force:
            die(f"目标目录不是空的、也不像是 ACP-lite 的 home：\n      {home}\n"
                f"      里面已有：{', '.join(unexpected[:5])}"
                + ("…" if len(unexpected) > 5 else "") + "\n"
                f"      这通常说明 --home 传错了（比如指到了用户主目录）。\n"
                f"      确认无误请加 --force；否则换一个专用目录再试。")
    if not HAVE_CRYPTO:
        print(UNSIGNED_WARN)
        ident = {"agent": args.agent, "display": args.display or args.agent,
                 "fingerprint": "unsigned", "pub": "", "priv": "",
                 "mode": "unsigned", "created_at": now_iso(), "signed": False}
    else:
        priv = Ed25519PrivateKey.generate()
        priv_raw = priv.private_bytes(
            serialization.Encoding.Raw, serialization.PrivateFormat.Raw,
            serialization.NoEncryption())
        pub_raw = priv.public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw)
        ident = {"agent": args.agent, "display": args.display or args.agent,
                 "fingerprint": fingerprint(pub_raw), "pub": b64e(pub_raw),
                 "priv": b64e(priv_raw), "mode": "signed",
                 "created_at": now_iso(), "signed": True}
    card_path = root / "peers" / f"{args.agent}.json"
    existing = read_json(card_path)
    if existing and existing.get("fingerprint") != ident["fingerprint"] and not args.force:
        die(f"共享目录里已有同名名片 {args.agent}"
            f"（指纹 {existing.get('fingerprint')}，本机是 {ident['fingerprint']}）。\n"
            f"      agent 名就是身份目录名，两台机器同名会互相覆盖名片、挤进同一个 outbox —— \n"
            f"      请改用限定名（如 {args.agent}@台式机 / {args.agent}@上网本），或加 --force 覆盖。")
    write_json(identity_path(home), ident)
    write_json(card_path, {
        "agent": args.agent,
        "display": ident["display"],
        "pub": ident["pub"],
        "fingerprint": ident["fingerprint"],
        "fingerprint_full": fingerprint_full(ident["pub"]) if HAVE_CRYPTO else "unsigned",
        "mode": ident["mode"],
        "signed": ident["signed"],
        "protocol": VERSION,
        "requires": list(REQUIRES),
        "transport": "shared-dir (Syncthing / Tailscale / 网盘 / U 盘)",
        "updated_at": now_iso(),
    })
    audit(home, "init", agent=args.agent, fingerprint=ident["fingerprint"])
    print(f"已初始化  身份={args.agent}  指纹={ident['fingerprint']}")
    print(f"  本机私有目录 : {home}   （不要同步）")
    print(f"  跨机共享目录 : {root}   （用 Syncthing 同步这个）")
    print("下一步：把本机指纹口头/扫码告诉对方，并运行  trust --agent <对方> --fingerprint <对方指纹>")


def cmd_status(args):
    home, root = Path(args.home), Path(args.root)
    ident = load_identity(home, required=False)
    print(f"ACP {VERSION}")
    if ident:
        print(f"  身份      : {ident['agent']}（{ident['display']}）")
        print(f"  指纹      : {ident['fingerprint']}")
        print(f"  模式      : {ident.get('mode', 'unsigned')}"
              + ("（ed25519 签名）" if ident.get("signed") else "（无签名：默认拒收跨机消息）"))
        if ident.get("pub"):
            print(f"  全长指纹  : {fingerprint_full(ident['pub'])}")
    else:
        print("  身份      : 未初始化")
    print(f"  home      : {home}")
    print(f"  root      : {root}")
    print(f"  L2 人密钥 : {'已设置' if (home / 'userkey.json').exists() else '未设置（无法签发放行票）'}")
    print(f"  刹车 STOP : {'生效中（一切出口已停）' if (home / 'STOP').exists() else '未生效'}")
    trusted = read_json(home / "trusted.json") or {}
    print(f"  信任的对方: {', '.join(f'{k}={v}' for k, v in trusted.items()) or '（无）'}")
    inbox = sorted((home / "inbox").glob("*.json")) if (home / "inbox").exists() else []
    tickets = sorted((home / "approvals").glob("approved-*.json")) if (home / "approvals").exists() else []
    print(f"  收件箱    : {len(inbox)} 条")
    print(f"  已签放行票: {len(tickets)} 张")
    if (root / "peers").exists():
        peers = [p.stem for p in sorted((root / "peers").glob("*.json"))]
        print(f"  共享名片  : {', '.join(peers) or '（无）'}")


def cmd_trust(args):
    home = Path(args.home)
    card = read_json(Path(args.root) / "peers" / f"{args.agent}.json")
    if card and card.get("mode") == "unsigned" and not args.force:
        die(f"{args.agent} 的名片是无签名模式（mode=unsigned）：没有可核对的密钥指纹。\n"
            f"      请先让对方安装 cryptography 重建身份；确要在本机自测中继续请加 --force。")
    if card and card.get("fingerprint") != args.fingerprint:
        die(f"指纹不符！名片上是 {card.get('fingerprint')}，你核对的是 {args.fingerprint}")
    data = read_json(home / "trusted.json") or {}
    old = data.get(args.agent)
    if old and old != args.fingerprint and not args.force:
        die(f"{args.agent} 的指纹变了！已记录 {old}，本次核对为 {args.fingerprint}。\n"
            f"      这可能意味着对方换了机器，也可能有人在中间替换身份。\n"
            f"      请通过带外渠道再次确认；确认无误后加 --force 更新。")
    data[args.agent] = args.fingerprint
    write_json(home / "trusted.json", data)
    audit(home, "trust", agent=args.agent, fingerprint=args.fingerprint, out_of_band=True)
    print(f"已信任 {args.agent}（指纹 {args.fingerprint}）—— 这次核对必须来自带外渠道")


def cmd_send(args):
    home, root = Path(args.home), Path(args.root)
    ident = load_identity(home)
    if args.requires not in REQUIRES:
        die(f"--requires 只能是 {REQUIRES}")
    if args.requires != "none" and args.action != "exec":
        die(f"语义矛盾：requires={args.requires} 是出口动作，action 必须是 exec"
            f"（action=infer 只用于理解与回应，不可能去付款/发送/删除）")
    hops = args.hops
    reply_to = None
    if args.reply_to:
        parent = read_json(home / "inbox" / f"{args.reply_to}.json")
        if not parent:
            die(f"收件箱里没有 {args.reply_to}，无法回信")
        hops = int((parent.get("x") or {}).get("hops", 0)) + 1
        reply_to = args.reply_to
        if hops > MAX_HOPS:
            die(f"回环保护：hops={hops} 已超过上限 {MAX_HOPS}，拒绝发送")
    # auto：手工回的信不该再要求对方回信（呼应"不回环/只回一封"）；新任务按"需要回答"处理
    rep = args.reply
    if rep == "auto":
        rep = "none" if reply_to else "answer"
    mtype = "reply" if reply_to else "task"
    env = make_envelope(ident["agent"], args.to, mtype, args.text, args.action,
                        args.requires, args.ttl, hops, reply_to, args.timeout,
                        max_hops=args.max_hops, reply=rep, code=args.code)
    sign_envelope(env, ident)
    out = root / "outbox" / ident["agent"] / f"{env['id']}.json"
    write_json(out, env)
    audit(home, "send", msg_id=env["id"], to=args.to, requires=args.requires, hops=hops)
    print(f"已投递 {env['id']} -> {args.to}"
          f"（action={args.action} requires={args.requires} hops={hops}）")
    print(f"  {out}")


def _deliver(home, root, env, status, note="", reason=""):
    entry = dict(env)
    entry["_delivery"] = {"status": status, "note": note, "reason": reason, "at": now_iso(),
                          "requires": (env.get("x") or {}).get("requires", "none")}
    write_json(Path(home) / "inbox" / f"{env['id']}.json", entry)
    audit(home, "deliver", msg_id=env["id"], frm=env.get("from"), status=status)
    return entry


def watch_once(home, root, verbose=True, allow_unsigned=False):
    """把共享 outbox 里发给我、且没见过的消息投进本机 inbox。不调用模型。

    单条隔离：一封坏消息不得挡住同一轮里其它消息（三方评审一致要求）。
    """
    home, root = Path(home), Path(root)
    ident = load_identity(home)
    me = ident["agent"]
    seen = read_json(home / "state" / "seen.json") or {}
    outbox = root / "outbox"
    if not outbox.exists():
        return []
    delivered = []
    for peer_dir in sorted(p for p in outbox.iterdir() if p.is_dir()):
        if peer_dir.name == me:
            continue
        for path in sorted(peer_dir.glob("*.json")):
            mid = path.stem
            try:
                env = read_json(path)
                if not isinstance(env, dict):
                    continue
                dest = env.get("to")
                # 支持 to='*' 广播：发给"房间里所有人"，但自己发的不再收回来
                if dest != me and dest != "*":
                    continue
                x = env.get("x") if isinstance(env.get("x"), dict) else {}
                idem = str(x.get("idem") or env.get("id") or mid)
                if idem in seen:
                    continue
                # 幂等不依赖 seen 上限：投递过就跳过（Muse 建议）
                if (home / "inbox" / f"{env.get('id', mid)}.json").exists():
                    seen[idem] = now_iso()
                    continue
                ok, reason = verify_envelope(env, root, allow_unsigned=allow_unsigned)
                exp = parse_iso(x.get("expires_at"))
                if not ok:
                    status, note = "rejected", reason
                elif reason == "unsigned-mode":
                    # 无签名模式：可见，但永不自动执行
                    status, note = "unverified", "对方未签名；本机以 --allow-unsigned 收下，仅供人工查看"
                elif trusted_fingerprint(home, env.get("from")) != (x.get("sig") or {}).get("key"):
                    status, note = "untrusted", "对方指纹未核对（运行 trust --agent ... --fingerprint ...）"
                elif int(x.get("hops", 0)) > int(x.get("max_hops", MAX_HOPS)):
                    status, note = "loop-guard", "超过最大跳数，疑为回环"
                elif exp and now() > exp:
                    # DSH §八.2 改动三：过期即拒，绝不自动执行
                    status, note = "expired", "已过 expires_at，只能降级为人工确认"
                else:
                    status, note = "ok", ""
                _deliver(home, root, env, status, note, reason)
                seen[idem] = now_iso()
                delivered.append((env.get("id", mid), status))
                if verbose:
                    print(f"  [{status:11}] {env.get('id', mid)}  from {env.get('from')}"
                          + (f"  ({note})" if note else ""))
            except Exception as exc:  # noqa: BLE001
                # 单条隔离：坏消息记为 malformed，继续处理下一条
                _deliver(home, root, {"id": mid, "from": "?", "to": me, "x": {}},
                         "rejected", f"malformed: {exc}", "malformed")
                seen[mid] = now_iso()
                delivered.append((mid, "rejected"))
                if verbose:
                    print(f"  [{'rejected':11}] {mid}  malformed: {exc}")
    # seen 改按时间过期（三家同指：固定留 1000 条会让老 id 被丢弃后旧信重投）
    cutoff = now() - datetime.timedelta(days=7)
    seen = {k: v for k, v in seen.items() if (parse_iso(v) or now()) >= cutoff}
    write_json(home / "state" / "seen.json", seen)
    fresh = _recheck_untrusted(home, root, allow_unsigned, verbose)
    if fresh:
        delivered.extend(fresh)
    return delivered


def _recheck_untrusted(home, root, allow_unsigned, verbose):
    """补 trust 之后，历史 untrusted 消息原地改判为 ok（DSH 建议）。

    动机："先入群、后核对指纹"是**正常顺序**，但旧逻辑下它会产出需要人工清理的死信，
    而人工清理还得同时动 inbox 和 seen.json 两处内部结构 —— 对普通用户等于救不回来。
    这里让 watch 每轮顺手用**当前**信任状态重判一次 untrusted 条目即可。

    注意：只改判 untrusted。expired 不翻案（过期就是过期，不能破坏"过期即拒"的语义），
    loop-guard / rejected 也不动（那两类是结构性问题，不是"信任来晚了"）。
    """
    out = []
    for path in sorted((home / "inbox").glob("*.json")):
        entry = read_json(path)
        if not isinstance(entry, dict):
            continue
        d = entry.get("_delivery") or {}
        if d.get("status") != "untrusted":
            continue
        x = entry.get("x") if isinstance(entry.get("x"), dict) else {}
        # 关键：_delivery 是投递时**追加**的字段，不在签名覆盖范围内，
        # 重新验签前必须先摘掉，否则算出来的规范串与原签名不符。
        clean = {k: v for k, v in entry.items() if k != "_delivery"}
        ok, _reason = verify_envelope(clean, root, allow_unsigned=allow_unsigned)
        if not ok or trusted_fingerprint(home, entry.get("from")) != (x.get("sig") or {}).get("key"):
            continue
        exp = parse_iso(x.get("expires_at"))
        if exp and now() > exp:
            d["status"], d["note"] = "expired", "指纹核对前已过期，不得翻案"
        else:
            d["status"], d["note"] = "ok", "指纹核对后自动改判"
        d["rechecked_at"] = now_iso()
        entry["_delivery"] = d
        write_json(path, entry)
        audit(home, "recheck", msg_id=entry.get("id"), result=d["status"])
        if verbose:
            print(f"  [recheck→{d['status']:<9}] {entry.get('id')}")
        out.append((entry.get("id"), d["status"]))
    return out


def cmd_watch(args):
    home, root = Path(args.home), Path(args.root)
    load_identity(home)
    check_mode_consistency(home)
    if not args.loop:
        delivered = watch_once(home, root, allow_unsigned=args.allow_unsigned)
        print(f"本次投递 {len(delivered)} 条（watch 不调用模型）")
        return
    print("watch 常驻中（Ctrl+C 退出）；本进程永不调用模型，挂机不烧 token。")
    while True:
        try:
            watch_once(home, root, allow_unsigned=args.allow_unsigned)
        except KeyboardInterrupt:
            print("\n已退出")
            return
        except Exception as exc:  # noqa: BLE001
            print(f"[warn] watch 循环异常：{exc}")
        time.sleep(args.interval)


def _load_ticket(home, msg_id, env=None):
    """取一张可用放行票：验签名 + 未用 + 未过期 +（给了消息则）动作摘要一致。"""
    path = Path(home) / "approvals" / f"approved-{msg_id}.json"
    ticket = read_json(path)
    if not ticket:
        return None
    if ticket.get("used_at"):
        return None
    exp = parse_iso(ticket.get("expires_at"))
    if exp and now() > exp:
        return None
    key = read_json(home / "userkey.json")
    if not key or not ticket.get("sig"):
        return None
    # 票必须由 L2 人密钥签发 —— 否则 agent 自己写个文件就能"自我放行"
    body = {k: v for k, v in ticket.items() if k != "sig"}
    try:
        Ed25519PublicKey.from_public_bytes(b64d(key["pub"])).verify(
            b64d(ticket["sig"]), canonical(body))
    except Exception:  # noqa: BLE001
        return None
    if env is not None:
        want = hashlib.sha256(
            canonical((env.get("payload") or {}).get("data", ""))).hexdigest()[:16]
        if ticket.get("action_digest") != want:
            return None  # 票面动作与当前内容不符 —— 一票一动作才真正闭环
    return ticket


def cmd_inbox(args):
    home = Path(args.home)
    rows = []
    for path in sorted((home / "inbox").glob("*.json")):
        env = read_json(path)
        if not env:
            continue
        d = env.get("_delivery") or {}
        if not args.all and d.get("status") != "ok":
            continue
        rows.append((env, d))
    if not rows:
        print("收件箱为空（或全部为非 ok 状态；加 --all 查看全部）")
        return
    for env, d in rows:
        req = (env.get("x") or {}).get("requires", "none")
        rep = (env.get("x") or {}).get("reply", "answer")
        gate = "已放行" if req not in GATED or _load_ticket(home, env["id"], env) else "待人工放行"
        print(f"{env['id']}  from={env.get('from'):<8} type={env.get('type'):<5} "
              f"requires={req:<7} reply={rep:<6} [{d.get('status')}] {gate}")
        print(f"    {(env.get('payload') or {}).get('data', '')[:160]}")


def cmd_digest(args):
    """省 token 用：把所有待处理消息压成一屏，一次读完，不必逐条叫模型。"""
    home = Path(args.home)
    rows = []
    for path in sorted((home / "inbox").glob("*.json")):
        env = read_json(path)
        if not isinstance(env, dict):
            continue
        d = env.get("_delivery") or {}
        if d.get("status") != "ok" or d.get("done_at"):
            continue
        rows.append((env, d))
    if not rows:
        print("没有待处理消息。")
        return 0
    by_reply = {}
    print(f"待处理 {len(rows)} 条（一屏看完；每条只给一行摘要，避免逐条读全文）")
    print("-" * 72)
    for env, d in rows[-args.limit:]:
        x = env.get("x") or {}
        # 没标过的历史消息如实显示"未标注"，不冒充"需回答"
        rep = x.get("reply")
        if rep not in REPLY_KINDS:
            rep = "未标注"
        by_reply[rep] = by_reply.get(rep, 0) + 1
        req = x.get("requires", "none")
        first = " ".join(str((env.get("payload") or {}).get("data", "")).split())[:70]
        flag = {"answer": "←需回答", "ack": "←回执即可", "none": "←不用回",
                "未标注": "←历史消息（发时还没这个标签）"}.get(rep, "")
        print(f"[{rep:<6}] {env.get('id')}  {env.get('from')}  requires={req}  {flag}")
        print(f"         {first}")
    print("-" * 72)
    print("汇总：" + " · ".join(f"{k} {v} 条" for k, v in by_reply.items()))
    print("提示：reply=none 可整批跳过；reply=ack 回一句即可；只有 reply=answer 值得花 token 认真答。")
    return 0


def cmd_ready(args):
    """agent 取活儿用：只列真正可执行的（受 STOP / 放行票约束）。"""
    home = Path(args.home)
    if (home / "STOP").exists():
        print("STOP 生效中：一切出口动作已停，agent 不应处理任何消息。")
        return
    ready, blocked = [], []
    for path in sorted((home / "inbox").glob("*.json")):
        env = read_json(path)
        if not env:
            continue
        d = env.get("_delivery") or {}
        if d.get("status") != "ok":
            continue
        req = (env.get("x") or {}).get("requires", "none")
        if req in GATED and not _load_ticket(home, env["id"], env):
            blocked.append((env, req))
        else:
            ready.append(env)
    for env in ready:
        print(f"[可执行] {env['id']}  from={env.get('from')}  requires="
              f"{(env.get('x') or {}).get('requires')}")
        print(f"    {(env.get('payload') or {}).get('data', '')[:200]}")
    for env, req in blocked:
        print(f"[需人放行] {env['id']}  requires={req}"
              f"  ->  运行：acp.py approve {env['id']}")
    if not ready and not blocked:
        print("没有可执行消息。")


def cmd_ack(args):
    home = Path(args.home)
    path = Path(home) / "inbox" / f"{args.msg_id}.json"
    env = read_json(path)
    if not env:
        die(f"收件箱里没有 {args.msg_id}")
    req = (env.get("x") or {}).get("requires", "none")
    # 投递状态必须为 ok 才允许确认执行 —— 否则被拦下的消息（rejected / untrusted /
    # expired / loop-guard / unverified）只要绕过 ready 直接 ack 就能"洗白"。
    # 这是蓝莓在 2026-10-05 联调中指出来的缺口。
    status = (env.get("_delivery") or {}).get("status")
    if status != "ok":
        die(f"这条消息的投递状态是 {status}，不是 ok，拒绝确认执行。\n"
            f"      rejected / untrusted / expired / loop-guard / unverified 都不得被当成可执行任务。")
    # STOP 是刹车，不留例外（别让人猜哪些动作"够轻"可以放行）
    if (home / "STOP").exists():
        die("STOP 生效中：拒绝一切处理动作（解除后重试）")
    ticket = None
    if req in GATED:
        ticket = _load_ticket(home, args.msg_id, env)
        if not ticket:
            die(f"requires={req} 属出口动作，但放行票无效："
                f"可能未签发 / 已用 / 已过期 / 内容与票面不符 / 签名不可信。\n"
                f"      请重新运行：acp.py approve {args.msg_id}")
    if ticket:
        ticket["used_at"] = now_iso()
        write_json(Path(home) / "approvals" / f"approved-{args.msg_id}.json", ticket)
    env["_delivery"]["status"] = "done"
    env["_delivery"]["done_at"] = now_iso()
    write_json(path, env)
    audit(home, "ack", msg_id=args.msg_id, requires=req, ticket=bool(ticket))
    print(f"已确认处理 {args.msg_id}（放行票{'已作废' if ticket else '未使用'}）")


def _derive_key(passphrase, salt):
    return hashlib.scrypt(passphrase.encode("utf-8"), salt=salt, n=2 ** 14, r=8, p=1, dklen=32)


def _get_passphrase(args):
    text = getattr(args, "passphrase", None) or os.environ.get("ACP_USERKEY_PASSPHRASE")
    if text:
        return text
    import getpass
    return getpass.getpass("请输入用户口令（L2 人密钥，只有你知道）：")


def cmd_userkey(args):
    home = Path(args.home)
    if not HAVE_CRYPTO:
        die("需要 cryptography 才能创建 L2 人密钥")
    if (home / "userkey.json").exists() and not args.force:
        die("L2 人密钥已存在（重建请加 --force）")
    passphrase = _get_passphrase(args)
    if len(passphrase) < 8:
        die("口令太短（至少 8 位）")
    priv = Ed25519PrivateKey.generate()
    priv_raw = priv.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw,
                                  serialization.NoEncryption())
    pub_raw = priv.public_key().public_bytes(serialization.Encoding.Raw,
                                             serialization.PublicFormat.Raw)
    salt, nonce = secrets.token_bytes(16), secrets.token_bytes(12)
    ct = AESGCM(_derive_key(passphrase, salt)).encrypt(nonce, priv_raw, b"acp-l2")
    write_json(home / "userkey.json", {
        "alg": "ed25519+aesgcm+scrypt", "salt": b64e(salt), "nonce": b64e(nonce),
        "ct": b64e(ct), "pub": b64e(pub_raw), "fingerprint": fingerprint(pub_raw),
        "created_at": now_iso(),
    })
    audit(home, "userkey-created", fingerprint=fingerprint(pub_raw))
    print("L2 人密钥已创建。私钥以口令加密后存放在本机私有目录，不会进共享目录。")
    print("口令只有你知道 —— agent 拿不到口令，就无法自签放行票。")


def cmd_approve(args):
    home = Path(args.home)
    if not HAVE_CRYPTO:
        die("需要 cryptography 才能签发放行票")
    key = read_json(home / "userkey.json")
    if not key:
        die("尚未创建 L2 人密钥：先运行 acp.py userkey")
    path = Path(home) / "inbox" / f"{args.msg_id}.json"
    env = read_json(path)
    if not env:
        die(f"收件箱里没有 {args.msg_id}")
    req = (env.get("x") or {}).get("requires", "none")
    priv_raw = AESGCM(_derive_key(_get_passphrase(args), b64d(key["salt"]))).decrypt(
        b64d(key["nonce"]), b64d(key["ct"]), b"acp-l2")
    priv = Ed25519PrivateKey.from_private_bytes(priv_raw)
    ticket = {
        "ticket_id": f"tk-{secrets.token_hex(4)}",
        "msg_id": args.msg_id,
        "requires": req,
        "action_digest": hashlib.sha256(
            canonical((env.get("payload") or {}).get("data", ""))).hexdigest()[:16],
        "issued_at": now_iso(),
        "expires_at": (now() + datetime.timedelta(seconds=args.ttl)).isoformat(timespec="seconds"),
        "issuer": f"human@{os.environ.get('COMPUTERNAME') or _nodename()}",
        "l2_key": key["fingerprint"],
        "used_at": None,
    }
    ticket["sig"] = b64e(priv.sign(canonical(ticket)))
    pub = Ed25519PublicKey.from_public_bytes(b64d(key["pub"]))
    pub.verify(b64d(ticket["sig"]), canonical({k: v for k, v in ticket.items() if k != "sig"}))
    write_json(home / "approvals" / f"approved-{args.msg_id}.json", ticket)
    audit(home, "approve", msg_id=args.msg_id, requires=req, ticket=ticket["ticket_id"])
    print(f"已签发放行票 {ticket['ticket_id']} -> {args.msg_id}"
          f"（requires={req}，有效期 {args.ttl}s，用一次即作废）")


def cmd_stop(args):
    home = Path(args.home)
    if args.off:
        (home / "STOP").unlink(missing_ok=True)
        audit(home, "stop-off")
        print("刹车已解除。")
    else:
        home.mkdir(parents=True, exist_ok=True)
        (home / "STOP").write_text(f"stopped at {now_iso()}\n", encoding="utf-8")
        audit(home, "stop-on")
        print("刹车已拉起：一切出口动作停止（收信仍继续，不受影响）。")


def cmd_audit(args):
    path = Path(args.home) / "audit.jsonl"
    if not path.exists():
        print("（暂无审计记录）")
        return
    lines = [ln for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    prev = "genesis"
    bad = 0
    for line in lines:
        rec = json.loads(line)
        body = {k: v for k, v in rec.items() if k != "hash"}
        expect = hashlib.sha256(prev.encode("utf-8") + canonical(body)).hexdigest()[:32]
        if rec.get("hash") != expect or rec.get("prev") != prev:
            bad += 1
        prev = rec.get("hash", prev)
    print(f"审计链共 {len(lines)} 条，校验{'通过 ✅' if not bad else f'失败 ❌（{bad} 处断裂）'}")
    for line in lines[-args.tail:]:
        rec = json.loads(line)
        print(f"  #{rec.get('seq')} {rec.get('ts')} {rec.get('event')} "
              f"{ {k: v for k, v in rec.items() if k not in ('seq', 'ts', 'event', 'prev', 'hash')} }")


# ---------------------------------------------------------------- CLI

def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            pass
    parser = argparse.ArgumentParser(
        prog="acp", description=f"{NAME} {VERSION}（跨主机邮局，最小实现）")
    parser.add_argument("--home", default=str(Path.home() / ".acp-personal"),
                        help="本机私有目录（含私钥，切勿同步）")
    parser.add_argument("--root", default=None,
                        help="跨机共享目录（Syncthing 同步这个；默认 <home>/shared）")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("init", help="生成身份与名片")
    p.add_argument("--agent", required=True, help="本机 agent 名（如 codex）")
    p.add_argument("--display", help="显示名（如 Codex@台式机）")
    p.add_argument("--force", action="store_true")
    p.set_defaults(func=cmd_init)

    sub.add_parser("status", help="查看身份/信任/收件箱/刹车状态").set_defaults(func=cmd_status)

    p = sub.add_parser("trust", help="带外核对并信任对方指纹")
    p.add_argument("--agent", required=True)
    p.add_argument("--fingerprint", required=True)
    p.add_argument("--force", action="store_true",
                   help="指纹与已记录不符、或对方为无签名模式时，仍强制更新")
    p.set_defaults(func=cmd_trust)

    p = sub.add_parser("send", help="投递一条消息到对方 outbox")
    p.add_argument("--to", required=True, help="收件 agent 名；用 * 表示广播给房间里所有人")
    p.add_argument("--text", required=True)
    p.add_argument("--action", default="infer", choices=("infer", "exec"))
    p.add_argument("--requires", default="none", choices=REQUIRES,
                   help="出口动作类型；write/send/pay/delete 需人工放行票")
    p.add_argument("--ttl", type=int, default=DEFAULT_TTL, help="有效期（秒）")
    p.add_argument("--timeout", type=int, default=1800)
    p.add_argument("--reply-to", default=None, help="回复某条消息（自动 hops+1）")
    p.add_argument("--max-hops", type=int, default=MAX_HOPS,
                   help=f"本消息允许的最大跳数（默认 {MAX_HOPS}；设 1 = 严格'只回一封'）")
    p.add_argument("--reply", default="auto", choices=("auto",) + REPLY_KINDS,
                   help="省 token 标签：none=不用回 / ack=回执即可 / answer=需要回答。"
                        "auto（默认）=回信自动 none、新任务自动 answer —— 手工回的信不该再要求对方回信")
    p.add_argument("--hops", type=int, default=0, help=argparse.SUPPRESS)
    p.add_argument("--code", default=None,
                   help="（v0.7 待定项）机器可读状态码，回信建议用：ok / fail / need-info / partial")
    p.set_defaults(func=cmd_send)

    p = sub.add_parser("watch", help="投递循环（永不调用模型）")
    p.add_argument("--loop", action="store_true")
    p.add_argument("--interval", type=float, default=3.0)
    p.add_argument("--allow-unsigned", action="store_true",
                   help="本机缺 cryptography 时，收下无签名消息但标记 unverified"
                        "（默认拒收；unverified 永不进入 ready）")
    p.set_defaults(func=cmd_watch)

    p = sub.add_parser("inbox", help="列出收件箱")
    p.add_argument("--all", action="store_true")
    p.set_defaults(func=cmd_inbox)

    sub.add_parser("ready", help="列出真正可执行的消息（受 STOP/放行票约束）").set_defaults(func=cmd_ready)
    pd = sub.add_parser("digest", help="把待处理消息压成一屏，一次读完（省 token）")
    pd.add_argument("--limit", type=int, default=30)
    pd.set_defaults(func=cmd_digest)

    p = sub.add_parser("ack", help="确认已处理某条消息（消耗放行票）")
    p.add_argument("msg_id")
    p.set_defaults(func=cmd_ack)

    p = sub.add_parser("userkey", help="创建 L2 人密钥（口令加密，存本机）")
    p.add_argument("--force", action="store_true")
    p.add_argument("--passphrase", default=None, help=argparse.SUPPRESS)
    p.set_defaults(func=cmd_userkey)

    p = sub.add_parser("approve", help="人工签发放行票（需口令）")
    p.add_argument("msg_id")
    p.add_argument("--ttl", type=int, default=3600)
    p.add_argument("--passphrase", default=None, help=argparse.SUPPRESS)
    p.set_defaults(func=cmd_approve)

    p = sub.add_parser("stop", help="拉刹车（默认开；--off 解除）")
    p.add_argument("--off", action="store_true")
    p.set_defaults(func=cmd_stop)

    p = sub.add_parser("audit", help="校验并查看哈希链审计")
    p.add_argument("--tail", type=int, default=10)
    p.set_defaults(func=cmd_audit)

    args = parser.parse_args(argv)
    if not args.root:
        args.root = str(Path(args.home) / "shared")
    Path(args.root).mkdir(parents=True, exist_ok=True)
    if args.cmd == "init" and not HAVE_CRYPTO:
        print(UNSIGNED_WARN)
    args.func(args)


if __name__ == "__main__":
    main()
