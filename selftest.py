#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ACP-lite (Agent Connect Personal) 端到端自测：用两个临时"机器"模拟跨主机场景。

覆盖：身份/指纹、带外信任、投递、幂等去重、回信与跳数、过期即拒、
未信任拒收、出口闸门（放行票）、STOP 刹车。

运行： python selftest.py
"""

import json
import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ACP = HERE / "acp.py"
PASS, FAIL = [], []


def run(*args, home, root, expect_ok=True):
    env = dict(os.environ, ACP_USERKEY_PASSPHRASE="test-passphrase-123",
               PYTHONIOENCODING="utf-8")
    cmd = [sys.executable, str(ACP), "--home", str(home), "--root", str(root), *args]
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", env=env)
    if expect_ok and proc.returncode != 0:
        raise AssertionError(f"命令失败：{' '.join(args)}\n{proc.stdout}\n{proc.stderr}")
    return (proc.stdout or "") + (proc.stderr or "")


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  {'✅' if cond else '❌'} {name}" + (f"  — {detail}" if detail and not cond else ""))


def card_fp(root, agent):
    data = json.loads((Path(root) / "peers" / f"{agent}.json").read_text(encoding="utf-8"))
    return data["fingerprint"]


def inbox_count(home):
    return len(list((Path(home) / "inbox").glob("*.json")))


def delivery(home, msg_id):
    data = json.loads((Path(home) / "inbox" / f"{msg_id}.json").read_text(encoding="utf-8"))
    return data.get("_delivery", {})


def last_msg_id(text):
    for line in text.splitlines():
        if line.startswith("已投递 "):
            return line.split()[1]
    raise AssertionError(f"未找到投递回执：\n{text}")


def load_acp_module():
    """把 acp.py 当模块加载，用于构造"带有效签名但字段异常"的消息。"""
    spec = importlib.util.spec_from_file_location("acpm_selftest", ACP)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


NO_CRYPTO_RUNNER = '''\
import runpy, sys

class BlockCrypto:
    def find_spec(self, name, path=None, target=None):
        if name.split(".")[0] == "cryptography":
            raise ImportError("blocked by selftest")
        return None

sys.meta_path.insert(0, BlockCrypto())
sys.argv = ["acp"] + sys.argv[1:]
runpy.run_path(ACP_PATH, run_name="__main__")
'''


def run_without_crypto(tmp, home, root, *args, expect_ok=True):
    """在"没有 cryptography"的子进程里跑一条命令（验证 fail-closed）。"""
    runner = Path(tmp) / "_no_crypto_runner.py"
    if not runner.exists():
        runner.write_text(
            NO_CRYPTO_RUNNER.replace("ACP_PATH", repr(str(ACP))), encoding="utf-8")
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    cmd = [sys.executable, str(runner), "--home", str(home), "--root", str(root), *args]
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", env=env)
    if expect_ok and proc.returncode != 0:
        raise AssertionError(f"命令失败：{' '.join(args)}\n{proc.stdout}\n{proc.stderr}")
    return (proc.stdout or "") + (proc.stderr or "")


def main():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            pass
    tmp = Path(tempfile.mkdtemp(prefix="acp-selftest-"))
    root = tmp / "shared"          # <- 现实中这一步由 Syncthing 同步
    home_a, home_b, home_c = tmp / "A", tmp / "B", tmp / "C"
    print(f"沙箱：{tmp}\n")
    try:
        print("1) 初始化两台机器 + 一个未信任的第三方")
        run("init", "--agent", "codex", "--display", "Codex@台式机", home=home_a, root=root)
        run("init", "--agent", "dsh", "--display", "DSH@台式机", home=home_b, root=root)
        run("init", "--agent", "cake", "--display", "OpenClaw@上网本", home=home_c, root=root)
        fp_a, fp_b = card_fp(root, "codex"), card_fp(root, "dsh")
        check("身份生成 + 名片落入共享目录", len(fp_a) == 19 and fp_a != fp_b, f"{fp_a} / {fp_b}")

        print("2) 带外核对指纹（双向）")
        run("trust", "--agent", "dsh", "--fingerprint", fp_b, home=home_a, root=root)
        run("trust", "--agent", "codex", "--fingerprint", fp_a, home=home_b, root=root)
        out = run("status", home=home_a, root=root)
        check("A 侧已记录对 B 的信任", "dsh=" + fp_b in out)
        bad = run("trust", "--agent", "dsh", "--fingerprint", "dead-beef-cafe-0000",
                  home=home_a, root=root, expect_ok=False)
        check("指纹不符时拒绝信任", "指纹不符" in bad)

        print("3) A → B 投递（跨机只靠共享目录）")
        out = run("send", "--to", "dsh", "--text", "第一条跨机消息", home=home_a, root=root)
        m1 = last_msg_id(out)
        run("watch", home=home_b, root=root)
        check("B 收到 1 条且状态 ok", inbox_count(home_b) == 1 and delivery(home_b, m1)["status"] == "ok",
              str(delivery(home_b, m1)))

        print("4) 幂等去重：再跑一次 watch 不应重复投递")
        run("watch", home=home_b, root=root)
        check("重复投递被丢弃", inbox_count(home_b) == 1, f"inbox={inbox_count(home_b)}")

        print("5) B 回信 → A 收到（hops=1）")
        run("send", "--to", "codex", "--text", "收到，这是回信", "--reply-to", m1,
            home=home_b, root=root)
        run("watch", home=home_a, root=root)
        replies = [json.loads(p.read_text(encoding="utf-8"))
                   for p in (home_a / "inbox").glob("*.json")]
        hops = [r["x"]["hops"] for r in replies if r.get("type") == "reply"]
        check("A 收到回信且 hops=1", hops == [1], str(hops))

        print("6) 过期即拒（不得自动执行）")
        out = run("send", "--to", "dsh", "--text", "三天前的旧任务", "--ttl", "-10",
                  home=home_a, root=root)
        m_exp = last_msg_id(out)
        run("watch", home=home_b, root=root)
        check("过期消息标记 expired", delivery(home_b, m_exp)["status"] == "expired",
              str(delivery(home_b, m_exp)))
        ready = run("ready", home=home_b, root=root)
        check("过期任务不出现在可执行列表", m_exp not in ready)
        denied = run("ack", m_exp, home=home_b, root=root, expect_ok=False)
        check("过期任务也不能靠直接 ack 绕过（蓝莓联调指出）", "拒绝确认执行" in denied)

        print("7) 回环保护：hops 超上限直接拦下")
        out = run("send", "--to", "dsh", "--text", "疑似回环", "--hops", "9",
                  home=home_a, root=root)
        m_loop = last_msg_id(out)
        run("watch", home=home_b, root=root)
        check("超跳数被判定 loop-guard", delivery(home_b, m_loop)["status"] == "loop-guard",
              str(delivery(home_b, m_loop)))

        print("8) 未核对指纹的第三方消息被拒收")
        out8 = run("send", "--to", "dsh", "--text", "我是冒充的", home=home_c, root=root)
        m_cake = last_msg_id(out8)
        run("watch", home=home_b, root=root)
        untrusted = [json.loads(p.read_text(encoding="utf-8")) for p in (home_b / "inbox").glob("*.json")]
        got = [u for u in untrusted if u.get("from") == "cake"]
        check("来自未信任方的消息被标记 untrusted",
              bool(got) and got[0]["_delivery"]["status"] == "untrusted",
              str(got[0]["_delivery"]) if got else "未收到")

        print("9) 出口闸门：requires=send 必须由人签发放行票")
        run("userkey", home=home_b, root=root)
        out = run("send", "--to", "dsh", "--text", "请帮我发一封邮件", "--action", "exec",
                  "--requires", "send", home=home_a, root=root)
        m_gate = last_msg_id(out)
        run("watch", home=home_b, root=root)
        ready = run("ready", home=home_b, root=root)
        check("未放行时被拦在出口闸门外", f"[需人放行] {m_gate}" in ready)
        denied = run("ack", m_gate, home=home_b, root=root, expect_ok=False)
        check("无票时 ack 被拒绝", "放行票" in denied)
        run("approve", m_gate, home=home_b, root=root)
        ready = run("ready", home=home_b, root=root)
        check("人放行后进入可执行列表", f"[可执行] {m_gate}" in ready)
        run("ack", m_gate, home=home_b, root=root)
        check("放行票用一次即作废",
              (json.loads((home_b / "approvals" / f"approved-{m_gate}.json")
                          .read_text(encoding="utf-8")) or {}).get("used_at") is not None)

        print("10) STOP 刹车")
        out10 = run("send", "--to", "dsh", "--text", "刹车期间的请求", "--action", "exec",
                    "--requires", "write", home=home_a, root=root)
        m_stop = last_msg_id(out10)
        run("watch", home=home_b, root=root)
        run("stop", home=home_b, root=root)
        ready = run("ready", home=home_b, root=root)
        check("STOP 生效后无可执行任务", "STOP 生效中" in ready)
        blocked = run("ack", m_stop, home=home_b, root=root, expect_ok=False)
        check("STOP 期间拒绝出口动作", "STOP 生效中" in blocked, blocked[:120])
        run("stop", "--off", home=home_b, root=root)

        print("11) 审计哈希链校验")
        out = run("audit", "--tail", "3", home=home_b, root=root)
        check("审计链校验通过", "校验通过" in out)

        print("12) P1-2 语义矛盾组合被拒（infer 不可能是「付款」）")
        bad = run("send", "--to", "dsh", "--text", "顺手付个款", "--action", "infer",
                  "--requires", "pay", home=home_a, root=root, expect_ok=False)
        check("--action infer --requires pay 被拒", "语义矛盾" in bad)

        print("13) P1-1/P1-7 放行票：伪造票与「动作被调包」都要挡住")
        out = run("send", "--to", "dsh", "--text", "帮我改一个本机文件", "--action", "exec",
                  "--requires", "write", home=home_a, root=root)
        m_w = last_msg_id(out)
        run("watch", home=home_b, root=root)
        # 13a 伪造票：agent 自己写一个文件冒充人工放行
        (home_b / "approvals" / f"approved-{m_w}.json").write_text(json.dumps({
            "ticket_id": "tk-forged", "msg_id": m_w, "requires": "write",
            "action_digest": "0000000000000000",
            "expires_at": "2099-01-01T00:00:00+08:00", "sig": "Zm9yZ2Vk"}),
            encoding="utf-8")
        denied = run("ack", m_w, home=home_b, root=root, expect_ok=False)
        check("伪造的放行票被拒（签名不可信）", "放行票无效" in denied)
        # 13b 正常放行后把内容调包，票必须失效
        run("approve", m_w, home=home_b, root=root)
        p_in = home_b / "inbox" / f"{m_w}.json"
        env_in = json.loads(p_in.read_text(encoding="utf-8"))
        env_in["payload"]["data"] = "把文件改成另一个内容（调包）"
        p_in.write_text(json.dumps(env_in, ensure_ascii=False, indent=2), encoding="utf-8")
        denied = run("ack", m_w, home=home_b, root=root, expect_ok=False)
        check("内容与票面不符时放行票失效", "放行票无效" in denied)

        print("14) P1-5 STOP 期间连「轻量」消息也不放行")
        out = run("send", "--to", "dsh", "--text", "纯推理请求", home=home_a, root=root)
        m_soft = last_msg_id(out)
        run("watch", home=home_b, root=root)
        run("stop", home=home_b, root=root)
        denied = run("ack", m_soft, home=home_b, root=root, expect_ok=False)
        check("STOP 期间 requires=none 也被拒", "STOP 生效中" in denied)
        run("stop", "--off", home=home_b, root=root)

        print("15) ENH-6 单条坏消息不得连坐同轮其它消息")
        acpm = load_acp_module()
        ident_a = json.loads((home_a / "identity.json").read_text(encoding="utf-8"))

        def craft(name, text, mutate):
            env = acpm.make_envelope("codex", "dsh", "task", text, "infer", "none",
                                     3600, 0, None, 1800)
            env["id"] = env["x"]["msg_id"] = env["x"]["idem"] = f"codex-{name}"
            mutate(env)
            acpm.sign_envelope(env, ident_a)
            acpm.write_json(root / "outbox" / "codex" / f"{env['id']}.json", env)
            return env["id"]

        # 用"未来 1 天、不带时区"的时间戳：既保住"无时区"这个测试点，
        # 又不会因为日期过期而变成 expired（原实现写死 2026-10-06，到期后本项必红）。
        import datetime as _dt
        _naive_future = (_dt.datetime.now() + _dt.timedelta(days=1)).replace(
            microsecond=0).isoformat()          # 注意：故意不带时区
        m_naive = craft("naive-0001", "时间戳不带时区的消息",
                        lambda e: e["x"].update(expires_at=_naive_future))
        m_broken = craft("broken-0002", "字段类型坏掉的消息",
                         lambda e: e["x"].update(hops="abc"))
        m_ok = craft("after-0003", "排在坏消息后面的正常消息", lambda e: None)
        run("watch", home=home_b, root=root)
        check("无时区时间戳不再导致崩溃（按本机时区补全）",
              delivery(home_b, m_naive)["status"] == "ok", str(delivery(home_b, m_naive)))
        d_broken = delivery(home_b, m_broken)
        check("坏字段被单独隔离为 malformed",
              d_broken["status"] == "rejected" and "malformed" in d_broken.get("reason", ""),
              str(d_broken))
        check("同轮中后面的正常消息仍被投递",
              delivery(home_b, m_ok)["status"] == "ok", str(delivery(home_b, m_ok)))

        print("16) P0 无签名降级模式必须 fail-closed")
        home_e, home_f = tmp / "E", tmp / "F"
        run_without_crypto(tmp, home_e, root, "init", "--agent", "nog")
        run_without_crypto(tmp, home_f, root, "init", "--agent", "nogpeer")
        run_without_crypto(tmp, home_e, root, "send", "--to", "nogpeer",
                           "--text", "无签名的伪造指令")
        run_without_crypto(tmp, home_f, root, "watch")
        env_n = json.loads(sorted((home_f / "inbox").glob("*.json"))[0].read_text(encoding="utf-8"))
        check("默认拒收无签名消息（不再是静默 ok）",
              env_n["_delivery"]["status"] == "rejected"
              and env_n["_delivery"].get("reason") == "unsigned", str(env_n["_delivery"]))
        # 显式打开开关：可以看，但绝不自动执行
        for f in (home_f / "inbox").glob("*.json"):
            f.unlink()
        (home_f / "state" / "seen.json").unlink(missing_ok=True)
        run_without_crypto(tmp, home_f, root, "watch", "--allow-unsigned")
        env_n = json.loads(sorted((home_f / "inbox").glob("*.json"))[0].read_text(encoding="utf-8"))
        check("--allow-unsigned 时标记 unverified",
              env_n["_delivery"]["status"] == "unverified", str(env_n["_delivery"]))
        ready_e = run_without_crypto(tmp, home_f, root, "ready")
        check("unverified 永不进入 ready（不会自动执行）",
              f"[可执行] {env_n['id']}" not in ready_e)

        print("17) P1-4 跨机重名会被拒绝")
        home_d = tmp / "D"
        bad = run("init", "--agent", "codex", "--display", "冒名的 codex",
                  home=home_d, root=root, expect_ok=False)
        check("同名名片冲突时拒绝初始化", "已有同名名片" in bad)

        print("17b) 0.5.2：--home 指到「已经有别的东西」的目录要拦住（DSH 踩过）")
        home_x = tmp / "X"
        home_x.mkdir(parents=True, exist_ok=True)
        (home_x / "我的文档.txt").write_text("这不是 ACP 的目录", encoding="utf-8")
        bad = run("init", "--agent", "oops", home=home_x, root=root, expect_ok=False)
        check("home 传错时拒绝初始化", "通常说明 --home 传错了" in bad, bad[:120])
        ok = run("init", "--agent", "oops", "--force", home=home_x, root=root)
        check("确认后可用 --force 强制初始化", "已初始化" in ok)

        print("18) P1-3 对方换机（指纹变更）要求确认")
        run("init", "--agent", "codex", "--force", home=home_a, root=root)
        fp_new = card_fp(root, "codex")
        bad = run("trust", "--agent", "codex", "--fingerprint", fp_new,
                  home=home_b, root=root, expect_ok=False)
        check("指纹变更被拦下并要求确认", "指纹变了" in bad)
        ok = run("trust", "--agent", "codex", "--fingerprint", fp_new, "--force",
                 home=home_b, root=root)
        check("带外确认后可 --force 更新", "已信任" in ok)

        print("19) ENH-1 临时文件必须落在 Syncthing 的忽略命名空间里")
        acpm2 = load_acp_module()
        probe = root / "probe.json"
        probe.mkdir()  # 用目录占位，逼 os.replace 失败，从而留住临时文件供检查
        try:
            acpm2.write_json(probe, {"x": 1})
        except OSError:
            pass
        leftovers = [p.name for p in root.iterdir() if p.name.endswith(".tmp")]
        check("临时文件带 ~syncthing~ 前缀（会被 Syncthing 排除同步）",
              bool(leftovers) and all(n.startswith("~syncthing~") for n in leftovers),
              f"leftovers={leftovers}")
        for name in leftovers:
            (root / name).unlink()
        probe.rmdir()
        check("正常路径下不残留 .tmp", not list(root.rglob("*.tmp")))

        print("20) v0.6：支持 to='*' 广播（群聊房间）")
        run("init", "--agent", "codex", "--force", home=home_a, root=root)
        fp_a3 = card_fp(root, "codex")
        run("trust", "--agent", "codex", "--fingerprint", fp_a3, "--force",
            home=home_b, root=root)
        out = run("send", "--to", "*", "--text", "群发报到：大家好", home=home_a, root=root)
        m_cast = last_msg_id(out)
        run("watch", home=home_b, root=root)
        check("广播消息能投递到已信任的成员",
              delivery(home_b, m_cast)["status"] == "ok", str(delivery(home_b, m_cast)))
        env_c = None
        run("watch", home=home_c, root=root)
        for p in (home_c / "inbox").glob(f"{m_cast}.json"):
            env_c = json.loads(p.read_text(encoding="utf-8"))
        check("未核对指纹的成员收到广播仍是 untrusted",
              env_c is not None and env_c["_delivery"]["status"] == "untrusted",
              str(env_c["_delivery"]) if env_c else "未收到")
        ready_b = run("ready", home=home_b, root=root)
        check("广播消息进入可执行列表（受 ready 约束）", f"[可执行] {m_cast}" in ready_b)

        print("21) v0.6.1：补 trust 后 watch 自动改判历史 untrusted（DSH 建议）")
        check("改判前确实是 untrusted",
              delivery(home_b, m_cake)["status"] == "untrusted", str(delivery(home_b, m_cake)))
        run("trust", "--agent", "cake", "--fingerprint", card_fp(root, "cake"),
            home=home_b, root=root)
        run("watch", home=home_b, root=root)
        check("补 trust 后自动改判为 ok（不再产出死信）",
              delivery(home_b, m_cake)["status"] == "ok", str(delivery(home_b, m_cake)))
        check("改判动作进了审计链",
              "recheck" in (home_b / "audit.jsonl").read_text(encoding="utf-8"))

        print("22) v0.6.2：省 token —— 信封带 reply 标签 + digest 一屏看完")
        out = run("send", "--to", "dsh", "--text", "这条只是通知，不用回我", "--reply", "none",
                  home=home_a, root=root)
        m_fyi = last_msg_id(out)
        out = run("send", "--to", "dsh", "--text", "这个请给我个答复", "--reply", "answer",
                  home=home_a, root=root)
        m_ans = last_msg_id(out)
        run("watch", home=home_b, root=root)
        e_fyi = json.loads((home_b / "inbox" / f"{m_fyi}.json").read_text(encoding="utf-8"))
        e_ans = json.loads((home_b / "inbox" / f"{m_ans}.json").read_text(encoding="utf-8"))
        check("reply=none 写进信封（x 段，旧端不受影响）", e_fyi["x"].get("reply") == "none",
              str(e_fyi["x"].get("reply")))
        check("reply=answer 写进信封", e_ans["x"].get("reply") == "answer")
        dg = run("digest", home=home_b, root=root)
        check("digest 一屏列出两条且标注要不要回",
              m_fyi in dg and m_ans in dg and "←不用回" in dg and "←需回答" in dg,
              dg[:200])
        check("digest 给出可跳过的汇总", "不用回" in dg and "需回答" in dg)
        # auto 默认值：回信自动 none、新任务自动 answer（避免"要求对方回信"的回环成本）
        out = run("send", "--to", "codex", "--text", "回你一句", "--reply-to", m_ans,
                  home=home_b, root=root)
        m_r = last_msg_id(out)
        run("watch", home=home_a, root=root)
        e_r = json.loads((home_a / "inbox" / f"{m_r}.json").read_text(encoding="utf-8"))
        check("回信默认 reply=none（不要求对方再回）",
              e_r["x"].get("reply") == "none", str(e_r["x"].get("reply")))
        check("type=reply 与 hops=1 仍然正确",
              e_r["type"] == "reply" and e_r["x"]["hops"] == 1, f"{e_r['type']}/{e_r['x']['hops']}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print(f"\n通过 {len(PASS)} 项，失败 {len(FAIL)} 项")
    if FAIL:
        print("失败项：" + "、".join(FAIL))
        return 1
    print("ACP 跨机最小闭环自测全部通过 ✅")
    return 0


if __name__ == "__main__":
    sys.exit(main())
