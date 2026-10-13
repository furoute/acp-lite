# ACP-lite (Agent Connect Personal)

**English** | [简体中文](README.md)

A **minimal implementation** of cross-host agent interconnect: one "post office" per machine, while agents keep reading and writing only local files.

![ACP-lite six-agent fleet topology](assets/acp-lite-topology-en.svg)

> Naming: **ACP-lite = Agent Connect Personal**. The final P is, **we hope, eventually read as Peace**.
> The goal is modest — let agents on two ordinary NAT-ed computers talk to each other, without going through any vendor.
> The diagram shows an example fleet of two hosts with two agents each; substitute your own names.
> By the way: the three nicknames in the diagram — **Blueberry (Hermes)**, **Cake (OpenClaw)** and **Rongmao (Muse)** — were **picked by my daughter**. 😄
>
> **Non-affiliation notice**: this project has **no relationship whatsoever** with Zed's *Agent Client Protocol*,
> OpenAI+Stripe's *Agentic Commerce Protocol*, or IBM's archived *Agent Communication Protocol*.
> When citing it, please use the full name "ACP-lite (Agent Connect Personal)".

---

## 1. What problem it solves

Today the agents **on the same machine** can already talk to each other (an on-host file channel), but **the gap between two machines** remains.

This program does exactly one thing: **make the mailboxes on two machines become "the same mailbox"** — everything else stays as it was.
Protocol version = program version = **0.6.2** (the two currently share a single `VERSION` constant in `acp.py`;
splitting them is planned for v0.7; the envelope format is defined by `ENVELOPE-FORMAT.md`).
The envelope adds an `x` section on top of the original 0.3 — older bridges that don't know it are unaffected.

## 2. Dependency & attribution notice

This project is **not** a communication protocol we invented.

ACP-lite's cross-host communication is **built on top of [Syncthing](https://github.com/syncthing/syncthing)** —
an **open-source continuous file synchronization tool** created by **Jakob Borg** and community
contributors (started in 2013 by the Swedish developer Jakob Borg; now maintained by the community
together with the Syncthing Foundation, a registered Swedish non-profit).

The synchronization layer is **not ours**, and we claim **no originality** over it.
What we did is add a thin scripting layer **on top of** Syncthing's existing file-sync mechanism.

- each host runs Syncthing and the agents share a single synced folder;
- two hosts become connected by **mutually adding each other's Device ID**;
- from then on, files written into that folder appear on the other host automatically.

Multi-agent collaboration here therefore **borrows Syncthing's existing mechanism**; it is not our invention.
Our thanks go to the Syncthing project and its maintainers.

ACP-lite itself is released under the **MIT License** (see `LICENSE`).

> The English text of this section also appears in [`ATTRIBUTION-EN.md`](ATTRIBUTION-EN.md).

## 3. The five iron rules

1. **On-host behaviour is unchanged** — the original ACP-lite file channel stays as it is; this program neither reads nor writes `mailbox/`.
2. **Cross-host shares exactly one directory** — Syncthing / Tailscale / cloud drive / a USB stick can all serve as the transport.
3. **Private keys never enter the shared directory** — `--home` is host-private; the shared directory holds only name cards and outboxes.
4. **Receiving never calls a model** — `watch` only writes to disk and appends to the audit log; idling costs no tokens. Whether to spend tokens is decided by a human or a scheduled job.
5. **Missing dependency means refuse-to-receive (fail-closed)** — without `cryptography` on the host, cross-host messages are **rejected by default**.
   To receive anyway you must pass `--allow-unsigned` explicitly (self-test scenarios only); such messages are marked `unverified` and **never enter `ready`**.
   (The first version accepted everything here, which amounted to a silent trust bypass; three reviews **unanimously** asked for it to be fixed.)

## 4. Quick start (do this once on each of two machines)

```bash
# 0. Install the dependency on both machines: pip install cryptography
#    It runs without it, but falls into "unsigned mode" — cross-host messages are rejected outright
#    (i.e. cross-host is unusable; see iron rule 5)
#
# 1. Install Syncthing (open source, no account, no central cloud) and add each other's Device ID
#    The synced directory can be anywhere; below we use the placeholders <shared-dir> / <home-dir>
#    Put the repo's .stignore into that directory (it blocks *.tmp and conflict copies)

# 2. Initialize identity (--home is host-private; --root is the directory Syncthing syncs)
python acp.py --home <home-dir> --root <shared-dir> init --agent codex --display "Codex@desktop"

# 3. Verify fingerprints out-of-band (this step must NOT go over the network)
python acp.py --home <home-dir> --root <shared-dir> status      # prints this host's fingerprint
python acp.py --home <home-dir> --root <shared-dir> trust --agent dsh --fingerprint xxxx-xxxx-xxxx-xxxx

# 4. Run the resident delivery loop (never calls a model; idling is free)
python acp.py --home <home-dir> --root <shared-dir> watch --loop --interval 3

# 5. Send one message / read the inbox
python acp.py --home <home-dir> --root <shared-dir> send --to dsh --text "hello"
python acp.py --home <home-dir> --root <shared-dir> inbox
```

Replace the placeholders per platform: on Windows, e.g. `--home D:\acp-home --root D:\acp-shared`;
on Linux / macOS, e.g. `--home ~/acp-home --root ~/acp-shared`.

> **Note (repo vs. Windows one-click scripts)**: this repository ships only the **cross-platform core program and the bare command chain**.
> The commands above work as-is on Windows / Linux / macOS.
> Internally we also have a set of **Windows double-click scripts** (`0-init.cmd` → `1-syncthing.cmd` → `2-watch.cmd` → `9-selftest.cmd`,
> plus `9-autostart.cmd` for autostart). They merely wrap the steps above and are **not part of this repository**;
> if you want the convenience, write your own `.cmd` around the commands above — behaviour is identical.

Before taking work, an agent asks "what am I allowed to do":

```bash
python acp.py ... ready      # lists only what is genuinely executable (subject to STOP and release tickets)
python acp.py ... ack <id>   # confirm it is done (consumes the release ticket)
```

## 5. The outbound gate (the heart of the security model)

| Action `--requires` | Who may do it |
|---|---|
| `none` / `read` | automatic |
| `write` / `send` / `pay` / `delete` | **requires a one-shot release ticket signed by a human** |

```bash
python acp.py ... userkey                 # create the L2 human key (passphrase-encrypted, host-local, only you know it)
python acp.py ... approve <msg_id>        # human release: prompts for the passphrase
python acp.py ... stop                    # brake: all outbound actions stop immediately (receiving is unaffected)
python acp.py ... stop --off              # release the brake
```

- **The agent cannot obtain the passphrase → it cannot sign its own release ticket.** This is how "an injected agent must not issue itself a permission slip" is enforced.
- A release ticket **must be signed by the L2 human key**; `ack` verifies it. An agent writing its own `approved-*.json` file is useless.
- A ticket is **bound to the message ID + action digest + validity window**: if the content changes the ticket is invalid, it is single-use, and replays fail.
- Semantically, "an inference action paying money" is disallowed: when `requires` is not `none`, `action` must be `exec`, otherwise `send` errors out immediately.
- `STOP` is just a file: as long as the filesystem works, the brake works — no model, no network needed.
  **While the brake is on, `ack` is refused across the board** — there is no "lightweight actions are exempt" exception.

## 6. What a cross-host envelope looks like

### First, the semantics of `to`: like @-mentioning someone in a group chat

Messages in the shared directory **are visible to every member of the room** (the files simply sit there; there is no confidentiality whatsoever).
`to` does not decide "who can see it" — it decides **"who is called out, and who should act"**:

| Value of `to` | Meaning | Other members |
|---|---|---|
| `dsh-desktop` | point-to-point: **only DSH is asked to act** | they can see it, but their `watch` neither delivers nor executes it (bystanders) |
| `*` | broadcast: **everyone is asked to act/respond** | delivered normally, each decides for itself |

So "point-to-point" in this project means **addressed but not encrypted**. Do not put anything in here that others should not see —
if you need confidentiality, that belongs to "body encryption" (not implemented yet; see the open-issues list in CHANGELOG).

Two things prevent flooding: `hops` (default 4-round cap, preventing endless relay chains) and **good manners** (whoever is addressed replying is enough;
not everyone needs to pile in). A broadcast is not "everyone must reply".

On top of the original v0.3 fields, an `x` section is added (older bridges that don't know it are unaffected):

```json
{
  "version": "0.6.2",
  "id": "codex-20261005-193000-a1b2",
  "from": "codex", "to": "dsh", "type": "task",
  "payload": { "action": "infer", "data": "body text", "timeout": 1800 },
  "created_at": "2026-10-05T19:30:00+08:00",
  "x": {
    "hops": 0, "max_hops": 4,
    "expires_at": "2026-10-06T19:30:00+08:00",
    "idem": "codex-20261005-193000-a1b2",
    "requires": "none",
    "sig": { "alg": "ed25519", "key": "xxxx-xxxx-xxxx-xxxx", "value": "base64..." }
  }
}
```

Four cross-host rules, all carried in that section:

| Rule | Field | Effect |
|---|---|---|
| Single writer | directory `outbox/<self>/` | nobody ever steps on anyone else's files; no Syncthing conflicts |
| Idempotence | `idem` | duplicates are dropped at the delivery layer (mail re-sends / sync jitter are safe) |
| Loop protection | `hops` / `max_hops` | over the cap it is blocked, so the two sides cannot auto-ignite each other |
| Expiry means refusal | `expires_at` | a task from three days ago will not suddenly auto-execute when you boot up |

> ⚠️ **On "reply only once" — be precise**: `hops/max_hops` guards against **endless loops**, not against "multi-round exchanges".
> The default `max_hops=4` means up to 4 round trips are allowed (normal discussion needs that).
> For a strict "reply only once", add `--max-hops 1` when sending.
> Also: **one malformed message does not take down the rest of the batch** — a message with a broken format is marked `rejected/malformed` individually and skipped.

## 7. Day-to-day operations

### Network mode: `auto` by default — don't switch it by hand

**Whether you are on the same LAN or across networks is decided by the transport itself** — no human needs to worry about it:

| Mode | Global discovery | Relay | Notes |
|---|---|---|---|
| **`auto` (default, recommended)** | on | on | on the same network it connects over the LAN; only if direct fails does it consult the "phone book" and fall back to a relay. **On ≠ actually going out to the internet** |
| `strict` | off | off | never registers its address with public servers; the price is **you cannot find the peer across networks**. Use only when you explicitly require "not one byte may leave the network" |

```bash
python acp_net.py --syncthing-home <syncthing-home> status      # show the mode + which path is actually used
python acp_net.py --syncthing-home <syncthing-home> mode auto   # default mode (formerly called wan)
python acp_net.py --syncthing-home <syncthing-home> mode strict # strict mode (formerly called lan)
python acp_net.py --syncthing-home <syncthing-home> kick       # reconnect immediately after a network change
# <syncthing-home>  =  Syncthing's config directory (contains config.xml)
#   Windows example: %USERPROFILE%\acp-home\syncthing
#   Linux/macOS example: ~/.config/syncthing
```

#### Slow after switching networks? First see where the slowness is (measured)

| Scenario | Measured time |
|---|---|
| **Passively waiting** for it to reconnect after a network switch | **about 4 min 50 s** |
| Actively poking it with `kick` | **about 2 s** |

The root cause is not "retries are too slow" but that **the carrier-side network mapping has not been established yet** — the log at the time showed seven consecutive
`Failed to exchange Hello messages … EOF`, meaning "the TCP connection succeeded but the peer did not answer".
Once the path really works, the reconnect itself is a matter of seconds.

Hence two improvements:
1. **Retry interval lowered from the default 20 s to 5 s** (the `mode` command sets this automatically) — so the moment the path opens it is caught;
2. **After switching networks, give it a `kick`** — restart the transport, forcing rediscovery and redialing (measured: 2 s).

> For "connect instantly on a network switch, completely seamless", only an always-on connection can deliver that (a private tunnel such as Tailscale).
> Public discovery + relay inherently has to wait for "re-register + find the peer again", so anywhere from seconds to minutes is normal.

Measured (in `auto` mode): global discovery and relaying are both on, and **the actual connection is still `<peer LAN address>:22000 tcp-server isLocal=True`**
— a direct LAN connection, no detour. The relay merely sits on standby as `Joined relay` and carries no data.

> In one line: **public servers are the spare tyre, not the main road. The main road is always the shortest path between the two machines.**
> There is exactly one case worth going `strict`: you explicitly require "not even address registration may happen".
> To get **cross-network traffic that still never touches a public server**, you need a private virtual network (Tailscale and friends) — that is a third mode, not a binary choice.

### The token ledger (know where the money goes first)

| Stage | Costs tokens? | How to verify |
|---|---|---|
| Writing a message file / Syncthing sync | no | open-source software, pure file moving |
| `watch` receiving and writing to disk | **no** | the process makes **zero network connections**, and the source contains no HTTP client at all |
| Automatically calling a model | **yes — and it is the only cost** | this program **does not** provide automatic processing; `watch` never calls a model |

So the precondition for free idling is: **do not enable automatic processing**. When you want work done, a human says so — or a scheduled job runs.

Two token-saving conventions:

```bash
# ① Mark "does this need a reply" when sending (default answer, safe-first)
python acp.py ... send --to dsh --text "just an FYI" --reply none     # no reply needed
python acp.py ... send --to dsh --text "please respond" --reply answer # an answer is needed

# ② The receiver uses digest to see everything at once, instead of reading one by one
python acp.py ... digest
```

A `digest` line looks like this, so a single call tells you which ones can be skipped wholesale:

```
[none  ] hermes-netbook-...   hermes-netbook  requires=none  ←不用回
[answer] dsh-desktop-...      dsh-desktop     requires=none  ←需回答
汇总：none 1 条 · answer 1 条
```

> The program's output labels are currently **in Chinese**, so the sample above is quoted verbatim
> (`←不用回` = no reply needed, `←需回答` = answer needed, `汇总` = summary).
> If you want English output, change the program — not the documentation.

- **Autostart**: run `watch --loop`. It **only moves files**, never calls a model, sits at a few tens of MB of RAM, and incurs no inference cost.
  - Windows: Task Scheduler, triggered at logon.
  - Linux: a `systemd --user` service (or `crontab @reboot`) launching the same command; macOS can use `launchd`.
- **Audit**: every delivery / release / confirmation goes into the `audit.jsonl` hash chain; the `audit` command verifies whether the whole chain has been tampered with.
- **Self-test**: `python selftest.py` runs the whole flow using two temporary "machines" (covering the gate, the brake,
  forged release tickets, content swapping, unsigned fallback, malformed-message isolation, temporary-file naming) — no network needed.
  **The item count is whatever the program prints** — all green means it passed; the documentation no longer hard-codes a number.
- **Synced directory**: put the repo's `.stignore` at the root of the Syncthing folder. It blocks two kinds of things:
  temporary files (`~syncthing~*` / `*.tmp`) and **conflict copies** (`*.sync-conflict-*` — those also end in
  `.json`, and without the rule they get scanned as if they were letters).

## 8. Deployment notes (all learned the hard way, or reasoned out)

| Item | Notes |
|---|---|
| **Install cryptography on both machines** | otherwise they fall into unsigned mode and cross-host messages are rejected by default (fail-closed) |
| **Keep clocks in sync (NTP)** | if the two machines drift too far, `expires_at` is misjudged (fresh messages treated as expired) |
| **Re-trust after rebuilding identity** | `init --force` replaces the key ⇒ the peer immediately sees `untrusted` and you must verify fingerprints out-of-band again |
| **Watch out when a fingerprint changes** | `trust` blocks "new fingerprint ≠ recorded fingerprint"; only after you confirm does `--force` update it (anti-man-in-the-middle) |
| **Agent names must be unique across machines** | two machines cannot both be called `codex` (they would overwrite name cards and crowd into one outbox); use qualified names like `codex@desktop` |
| **Anyone can write `peers/`** | name cards live in the shared directory and any syncing party can overwrite them (low risk). TOFU (trust-on-first-use) is a possible future step |
| **Don't use `ACP_USERKEY_PASSPHRASE` in production** | that environment variable is for self-tests; in production use interactive passphrase entry so the passphrase is not inherited by child processes |

## 9. Boundaries (stated honestly)

- ⚠️ **The message body is plaintext on disk**: Syncthing's **transport** is end-to-end encrypted (a relay only ever sees ciphertext),
  but the message **as a file in the shared directory is plaintext**. Until body encryption (X25519 + AES-GCM) lands,
  **do not send sensitive content over this channel** — "there is end-to-end encryption" does not mean "the disk is safe".
- This program **calls no model**, and it does not decide "whether to execute" for you — it only delivers messages safely and guards the gate.
- Agents themselves are not addressable (true of every vendor); **what is addressable is the machine**; identity is held by the post office on its behalf.
- Metadata about the synced directory (who syncs with whom, file sizes) is visible to Syncthing relays; for confidential content, turn off public relays and use a LAN or Tailscale, or a mail / object-storage backend.
- Dependencies: **Python 3.9+ and `cryptography`**. The latter is nominally "optional" (the program starts fine without it and single-host self-tests run),
  but **without it you are fail-closed: all cross-host messages are rejected**, i.e. cross-host is unusable — so **treat it as required for any real deployment** (see iron rule 5).

---

## 10. What it can and cannot do (the one-line boundary)

> This section is for someone seeing the project for the first time: **do not mistake a "shared folder" for "remote execution"**. Three points.

- ✅ **It can: share files across hosts.**
  Sync the same directory (`acp-shared`) to several machines with Syncthing, and an agent writes a signed letter into `outbox/<self>/`.
  The peer receives it, verifies the signature and appends to its audit chain by itself — this part **costs no model tokens at all**.

- ❌ **It cannot: call the peer's agent directly over CLI across hosts.**
  This project contains **no** cross-host wake-up channel (no SSH, no private tunnel, no web service).
  Across hosts you can only rely on "shared directory + a resident `watch` on the peer":
  if the peer is off, or has no `watch` running, your letter simply queues in the mailbox — **nobody will go and wake it up for you**.
  To get "send it and someone starts working", you need an extra wake-up channel (SSH / Tailscale and the like), **which is out of scope for this project**.

- ✅ **Same host: two agents on one machine can wake each other over CLI (both directions).**
  One line on each side does it (the pair below is the measured phrasing for a resident two-agent host; the same applies to your own CLIs):

  ```bash
  openclaw agent --message "reply with just one word: received"   # Blueberry (Hermes) → Cake (OpenClaw)
  hermes -z "reply with just one word: received"                  # Cake → Blueberry (the reverse holds too)
  ```

  The proper form passes a "pointer" (the body still travels through the mailbox — never pass the body over CLI):

  ```bash
  dsh --profile headless "read <absolute path of the received file> and act on it"      # Codex → DSH
  ```

  The rule: **a wake-up passes only a "pointer" (the absolute path of the received file, which is where the msg_id lives); the body is still read by the other side from the mailbox** —
  **ACP is the ledger, CLI is the doorbell; a doorbell cannot replace a ledger** (signature verification, audit chain, deduplication/idempotence, cross-host uniformity — CLI handles none of these).

  > **Two details you must know**: ① before waking the DSH side, set `DSH_PERMISSION_MODE=danger-full-access` (Windows PowerShell: `$env:DSH_PERMISSION_MODE='danger-full-access'`) — without it the headless session will not start;
  > ② the reverse direction (DSH waking Codex) works the same way: `codex exec --skip-git-repo-check --ephemeral "read <absolute path of the received file> and act on it"`.

- ⚠️ In one line: **this project solves "how a message arrives reliably"; it does not solve "how the other side gets woken up".**
