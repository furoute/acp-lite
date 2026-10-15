# ACP-lite (Agent Connect Personal)

**English** | [简体中文](README.md)

A **minimal implementation** of cross-host agent interconnect: one "post office" per machine, while agents still only read and write local files.
Two ordinary computers behind NAT — no public IP, no server.

![ACP-lite six-agent fleet topology](assets/acp-lite-topology-en.svg)

> Naming: **ACP-lite = Agent Connect Personal**. The final P is, **we hope, eventually read as Peace**.
> The diagram is an example fleet (two hosts, two agents each) — substitute your own names; the three
> nicknames in it, **Blueberry (Hermes)**, **Cake (OpenClaw)** and **Rongmao (Muse)**, were **picked by my daughter**. 😄
>
> **Non-affiliation notice**: this project has **no relationship whatsoever** with Zed's *Agent Client Protocol*,
> OpenAI+Stripe's *Agentic Commerce Protocol*, or IBM's archived *Agent Communication Protocol*.
> When citing it, please use the full name "ACP-lite (Agent Connect Personal)".

**How to read this**: it is an operating manual — the commands are meant to be copied as they are; `<home-dir>` / `<shared-dir>` / `<agent>` / `<peer-agent>` are placeholders.
Setup is §1, the command cheat sheet is §2, and **when something breaks, look at §4 first (those 8 FAQs are pitfalls we really hit)**.
The design rationale / comparison table / attribution / boundaries are §6 – §10 (for people who want to know *why*; skip them if you just want to use it).
Program version = protocol version = **0.7.0**; the envelope format is defined by `ENVELOPE-FORMAT.md`.

## 1. Install and initialize (do this once on each machine)

```bash
# 1. Python dependency. It starts without it, but cross-host messages are then rejected
#    outright (fail-closed, see iron rule 5) → treat it as required for any real deployment
pip install cryptography

# 2. Install Syncthing (open source, no account, no central cloud): the two machines add
#    each other's Device ID. Pick any synced directory (called <shared-dir> below) and put
#    the repo's .stignore at its root

# 3. Initialize the identity. --home is this host's private directory (it holds the private
#    key and must NEVER go into the synced directory); --root is the directory Syncthing syncs
python acp.py --home <home-dir> --root <shared-dir> init --agent <agent> --display "Codex@desktop"

# 4. Verify the fingerprint out-of-band (it MUST be out-of-band: in person or by voice, never over the network)
python acp.py --home <home-dir> --root <shared-dir> status     # prints this host's fingerprint
python acp.py --home <home-dir> --root <shared-dir> trust --agent <peer-agent> --fingerprint xxxx-xxxx-xxxx-xxxx

# 5. Resident delivery (moves files only, never calls a model; idling burns no tokens)
python acp.py --home <home-dir> --root <shared-dir> watch --loop --interval 3
```

Replace the placeholders per platform: on Windows, e.g. `--home D:\acp-home --root D:\acp-shared`;
on Linux / macOS, e.g. `--home ~/acp-home --root ~/acp-shared`. Three rules you must keep:

- **Never omit `--root`**: without it the default is `<home>/shared` — **exit code 0, and it looks like it worked**, while the letter actually lands in this host's private directory (FAQ 3).
- **Agent names must be unique across machines**: the two machines cannot both be called `codex` (they would overwrite each other's name card and crowd into the same outbox).
- **Put `.stignore` at the root of the synced directory**: it keeps out `~syncthing~*` / `*.tmp` and the conflict copies `*.sync-conflict-*` (those also end in `.json`, and without the rule they get scanned as if they were letters).

### Optional: a cross-host wake-up channel (an OpenSSH server)

This project **ships no** wake-up channel of its own (`watch` never calls a model), but **a direct SSH wake-up has been verified working** (2026-10-14 / 10-15; 5 closed loops, all passed).
The machine to be woken only needs an OpenSSH server, with port 22 opened to the local subnet alone:

```powershell
# Windows (administrator required)
Add-WindowsCapability -Online -Name OpenSSH.Server~~~~0.0.1.0
Set-Service sshd -StartupType Automatic; Start-Service sshd
New-NetFirewallRule -Name OpenSSH-Server-In-TCP-LAN -DisplayName 'OpenSSH Server (LAN only)' `
  -Enabled True -Direction Inbound -Protocol TCP -Action Allow -LocalPort 22 -RemoteAddress 192.168.0.0/24
```

```bash
# Linux / macOS
sudo apt install openssh-server        # macOS ships OpenSSH
```

Wake-up commands (the prompt goes **through a file + stdin**, so neither Chinese text nor special characters get mangled by the shell):

```cmd
rem Wake Codex (the sandbox level must make the target directories writable — see FAQ 7)
codex exec -s workspace-write --skip-git-repo-check -C D:\_wake ^
  --add-dir D:\SharedFiles --add-dir D:\ACP-Shared --add-dir D:\LLM\ACP-lite\home ^
  - < prompt.txt
```

```cmd
rem Wake DSH (the level environment variable must live in the same process as dsh — see FAQ 5)
set "DSH_PERMISSION_MODE=danger-full-access"
cd /d D:\LLM\ACP-lite\_dsh-wake
dsh --profile headless - < prompt.txt
```

```bash
# Two agents on the same host can also call each other over CLI, in both directions
# (substitute your own CLIs — the same holds)
openclaw agent --message "reply with just one word: received"   # Blueberry (Hermes) → Cake (OpenClaw)
hermes -z "reply with just one word: received"                  # Cake → Blueberry (the reverse holds too)
```

A wake-up carries only a "**pointer**" (the absolute path of the received letter, which is where `msg_id` lives); the body is still read by the other side from its own mailbox —
**ACP is the ledger, the CLI is the doorbell; a doorbell cannot replace a ledger**. And **do not judge by the exit code**: `exit 0` may mean "it really did the work" or merely "it said something" — the criteria are **an artifact on disk + a longer audit chain + a signed receipt**.

## 2. Command cheat sheet

Every command below takes `--home <home-dir> --root <shared-dir>` (written as `acp.py ...` for brevity).

| Command | What it does |
|---|---|
| `acp.py ... status` | identity / trust / inbox / brake status; prints this host's fingerprint |
| `acp.py ... send --to <peer-agent> --text "..."` | deliver one message; `--to '*'` = broadcast; `--reply none` = no reply needed (default `auto`) |
| `acp.py ... send --reply-to <msg_id> ...` | reply (auto `hops+1`) |
| `acp.py ... inbox` | list the inbox |
| `acp.py ... ready` | list only what is **genuinely executable** (subject to STOP and release tickets) |
| `acp.py ... digest` | condense the pending messages into one screen — **the token-saving way to receive** |
| `acp.py ... ack <msg_id>` | confirm it is handled (consumes the release ticket) |
| `acp.py ... watch --loop --interval 3` | resident delivery (never calls a model) |
| `acp.py ... audit` | verify and inspect the hash-chained audit log |
| `python selftest.py` | run the entire offline self-test (gate / brake / forged release ticket / bad-message isolation); no network needed |

## 3. The outbound gate (the heart of the security model)

| Action `--requires` | Who may do it |
|---|---|
| `none` / `read` | automatic |
| `write` / `send` / `pay` / `delete` | **requires a one-shot release ticket signed by a human** |

```bash
python acp.py ... userkey                 # create the L2 human key (passphrase-encrypted, host-local, only you know the passphrase)
python acp.py ... approve <msg_id>        # human release: prompts for the passphrase
python acp.py ... stop                    # brake: every outbound action stops at once (receiving is unaffected)
python acp.py ... stop --off              # release the brake
```

- **The agent cannot obtain the passphrase ⇒ it cannot sign its own release ticket.** This is how "an injected agent must not issue itself a permission slip" is grounded.
  A ticket **must be signed by the L2 human key** and is verified at `ack` time; it is bound to "message ID + action digest + validity window" — change it and it is void, use it once and it is spent, replaying it does nothing. An agent writing its own `approved-*.json` file does not work.
- Semantically, "an inference action paying money" is disallowed: when `requires` is not `none`, `action` must be `exec`; otherwise `send` errors out immediately.
- **`STOP` is a file**: as long as the filesystem is there, the brake works — no model, no network needed. **While the brake is on, `ack` is refused across the board.**

## 4. FAQ (pitfalls we really hit)

**Q0: What is ACP-lite?**
A: ACP-lite (Agent Connect Personal) is a **minimal implementation** of cross-host agent interconnect: one "post office" per machine, while agents still only read and write local files; two ordinary computers behind NAT are enough — no public IP, no server.

**Q1: After a wake-up, DSH is "hog-tied" and reports `SetNamedSecurityInfoW failed Win32 5`?**
A: Setting `DSH_PERMISSION_MODE=danger-full-access` **alone is not enough** — it also needs a **clean working directory**:
a dirty directory cannot have its ACL granted (`grantWrite(<dir>)` is refused, Win32 5 = access denied), and the command
**fails to start already in the sandbox preparation stage**. Wake it again from a clean directory (we set DSH's cwd to
`D:\LLM\ACP-lite\_dsh-wake`). This one **does not reproduce reliably** — don't advertise it as "always breaks".

**Q2: Does DSH have `--add-dir`?**
A: **No.** DSH's writable roots are hard-wired to "the workspace + `/tmp` + the system temp directory", with no extension
hook, so you must either **hand over the whole machine** (`DSH_PERMISSION_MODE=danger-full-access`) or raise the cwd.
Codex does have `--add-dir`; write it as `-s workspace-write --add-dir X --add-dir Y`.

**Q3: Can `acp.py --root` be omitted?**
A: **No.** When omitted it defaults to `<home>/shared` (not the shared group directory), with **exit code 0 and no error
at all** — but the letter lands in this host's private directory and nobody in the group ever sees it. Always write
`--root <shared-dir>` explicitly when sending or replying; the criterion is that a file really shows up in `outbox/<recipient-agent>/`.

**Q4: How do I pass Chinese bodies / Chinese prompts?**
A: **Not through command-line arguments** (`cmd` / PowerShell read UTF-8 as GBK and you receive garbage like `鎶婅繖鍙ヨ瘽…`;
non-interactive SSH even re-tokenizes). **Use a file + stdin**: write the body to a UTF-8 file first and hand it to the woken
CLI as `- < prompt.txt`; when sending Chinese mail, also read the file and call `acp.main([...])` **inside the same Python
process** — never let Chinese text pass through the shell.

**Q5: How do I pass environment variables such as the level to the woken CLI?**
A: **Only with a single-process `set`**: `set "DSH_PERMISSION_MODE=danger-full-access"` immediately followed by `dsh …`
(the same `.cmd`, the same process). **Do not chain it as `cmd /c "set X=Y && dsh"`** — the level does not get through, and
the symptom is **silent zero output** (no error, nothing on disk).

**Q6: Should a wake-up use `schtasks` or a foreground SSH session?**
A: **Short jobs: foreground SSH; long jobs: a scheduled task.** `schtasks` pops a console window but **survives the SSH
disconnect**; foreground SSH pops nothing but **dies with the session**. Background jobs started with `start /b` get
reaped by the SSH session — don't use them.

**Q7: Which sandbox level should Codex use?**
A: `-s read-only` for read-only work; **anything that writes to disk or sends mail needs `-s workspace-write`, with every
target directory added via `--add-dir`** — including **the ACP home** (the easiest one to miss). Without write access there
you get "**the letter was sent, the ledger was not written**": the message went out, but the audit chain `audit.jsonl`
could not be appended. The startup banner prints the effective writable roots and can be used as hard evidence.

**Q8: Does having the desktop app open interfere with CLI wake-ups?**
A: **No** (measured): the desktop app and the CLI wake-up are **independent sessions** with no write conflict (with 5 DSH
desktop processes running, a CLI wake-up still finished in 18 seconds and wrote outside the workspace). The only exception
is "taking over an existing session": while the Codex desktop client holds the write lock, `resume` fails
(`already has an active writer`).

## 5. Operations and deployment notes

### Network mode: `auto` by default — don't switch it by hand

```bash
python acp_net.py --syncthing-home <syncthing-home> status      # show the mode + which path is actually used
python acp_net.py --syncthing-home <syncthing-home> mode auto   # default mode (formerly called wan)
python acp_net.py --syncthing-home <syncthing-home> mode strict # strict mode (formerly called lan)
python acp_net.py --syncthing-home <syncthing-home> kick       # reconnect immediately after a network change
# <syncthing-home> = Syncthing's config directory (contains config.xml):
#   Windows example: %USERPROFILE%\acp-home\syncthing | Linux/macOS example: ~/.config/syncthing
```

- In `auto` mode the measured path is a direct LAN connection (`<peer LAN address>:22000 isLocal=True`); the relay merely sits on standby as `Joined relay` — **public servers are the spare tyre, not the main road**. `strict` registers no address at all, and the price is that you cannot find the peer across networks.
- **After switching networks, don't wait — `kick`**: measured, waiting passively takes about **4 min 50 s**, an active `kick` about **2 s**.

### The token ledger

Writing message files / Syncthing sync / `watch` writing received mail to disk **cost no tokens** (the `watch` process makes **zero network connections** — there is no HTTP client anywhere in the source);
the **only thing that costs is "automatically calling a model", and this program does not offer that action** (`watch` never calls a model).

```bash
python acp.py ... send --to dsh --text "this is just an FYI" --reply none    # no reply needed
python acp.py ... send --to dsh --text "please give me an answer" --reply answer    # an answer is needed
python acp.py ... digest                                             # the receiver reads everything at once instead of one by one
```

### Resident and self-checks

- **Autostart**: run `watch --loop` (moves files only; a few tens of MB resident). On Windows, Task Scheduler triggered at logon; on Linux, `systemd --user` (or `crontab @reboot`); on macOS, `launchd`.
- **Audit / self-test**: every delivery / release / confirmation goes into the `audit.jsonl` hash chain, and `acp.py audit` verifies whether the whole chain has been tampered with; `python selftest.py` runs the whole flow using two temporary "machines" (**the item count is whatever the program prints**).

### Deployment notes

| Item | Notes |
|---|---|
| **Keep clocks in sync (NTP)** | if the two machines drift too far, `expires_at` is misjudged (a fresh message is treated as expired) |
| **Re-trust after rebuilding the identity** | `init --force` replaces the key ⇒ the peer immediately sees `untrusted` and you must verify the fingerprint out-of-band again |
| **Watch out when the fingerprint changes** | `trust` blocks "new fingerprint ≠ recorded fingerprint"; only after you confirm does `--force` update it (anti-man-in-the-middle) |
| **Anyone can write `peers/`** | name cards live in the shared directory and any syncing party can overwrite them (low risk). TOFU (trust-on-first-use: lock the fingerprint on first sight, warn when it changes) is a possible future step |
| **Don't use `ACP_USERKEY_PASSPHRASE` in production** | that environment variable is for self-tests; in production use interactive passphrase entry so the passphrase is not inherited by child processes |

---

§6 – §10 below are **for people**: read them if you want to know *why it is designed this way*; you can skip them if you just want to use it.

## 6. The five iron rules

1. **On-host behaviour is unchanged** — the original file channel stays as it is; this program neither reads nor writes `mailbox/`.
2. **Cross-host shares exactly one directory** — Syncthing / Tailscale / a cloud drive / a USB stick can all serve as the transport.
3. **Private keys never enter the shared directory** — `--home` is host-private; the shared directory holds only name cards and outboxes.
4. **Receiving never calls a model** — `watch` only writes to disk and appends to the audit log; idling burns no tokens.
5. **Missing dependency means refuse-to-receive (fail-closed)** — without `cryptography` on the host, cross-host messages are **rejected by default**;
   to receive anyway for a self-test you must pass `--allow-unsigned` explicitly, and such messages are marked `unverified` and **never enter `ready`**.

## 7. The cross-host envelope

The semantics of `to` are like **@-mentioning someone in a group chat**: a message in the shared directory is visible to every member of the room (the file simply sits there; there is no confidentiality whatsoever), and `to` only decides **"who is called out, and who should act"**:

| Value of `to` | Meaning | Other members |
|---|---|---|
| `dsh-desktop` | point-to-point: **only DSH is asked to act** | they can see it, but their `watch` neither delivers nor executes it (bystanders) |
| `*` | broadcast: **everyone is asked to act/respond** | delivered normally, each decides for itself |

So "point-to-point" in this project means **addressed but not encrypted**. Do not put anything in here that others should not see (for body encryption, see the open-issues list in the CHANGELOG).
Flooding is prevented by `hops` (a default cap of 4 rounds) and by **good manners**: a broadcast is not "everyone must reply".

| Rule | Field | Effect |
|---|---|---|
| Single writer | directory `outbox/<self>/` | nobody ever steps on anyone else's files; no Syncthing conflicts |
| Idempotence | `idem` | duplicates are dropped at the delivery layer (mail re-sends / sync jitter are safe) |
| Loop protection | `hops` / `max_hops` | over the cap it is blocked, so the two sides cannot auto-ignite each other |
| Expiry means refusal | `expires_at` | a task from three days ago will not suddenly auto-execute when you boot up |

> `hops` guards against **endless loops**, not against "multi-round exchanges": the default `max_hops=4` allows 4 round trips; for a strict "reply only once", add `--max-hops 1`.
> **One bad message does not take down the others in the same round** (it is marked `rejected/malformed` and skipped).

The field-level specification (the meaning of every field in the `x` section, the signature algorithm, `created_at`, …) is in `ENVELOPE-FORMAT.md`.
**A hand-written envelope has no signature → it is always rejected**; don't hand-write, use `send`.

## 8. Positioning: compared with MCP / A2A / message middleware

| | ACP-lite | MCP | Google A2A | NATS / Redis PubSub |
|---|---|---|---|---|
| Problem solved | cross-host agent messaging | models calling external tools | standardized agent-to-agent communication | general real-time messaging |
| Transport | Syncthing file sync | local STDIO / HTTP | HTTP + JSON-RPC | long-lived TCP connections |
| Public IP / server needed | no | no (local) | yes (a service endpoint) | yes (a broker) |
| Two computers behind NAT | works out of the box | not applicable | needs NAT traversal | needs NAT traversal |
| Message signature / audit | ed25519 + hash chain | none (roll your own) | implementation-dependent | none (roll your own) |
| Latency | seconds | real time | real time | milliseconds |
| Suitable scale | individuals / small teams | single-host agents | enterprise agent networks | engineering systems |

> Positioning sentence: **ACP-lite is the minimal communication scheme for "agents on two ordinary computers behind NAT"; for enterprise-grade standardization go to A2A, for a model calling tools go to MCP, for millisecond latency go to message middleware.**

## 9. Dependencies and attribution

- **The communication layer is not something we invented**: cross-host communication is **built on top of [Syncthing](https://github.com/syncthing/syncthing)**
  (Syncthing is an open-source continuous file-sync tool created by Jakob Borg and community contributors, now maintained by the
  Swedish non-profit Syncthing Foundation together with the community). **We did not write the sync layer and we claim no originality
  over it** — our thanks go to the Syncthing project and its maintainers. All we added is a thin layer of **signed envelopes + hash-chained audit**.
- **Runtime dependencies**: Python 3.9+, `cryptography`, Syncthing (plus OpenSSH if you want cross-host wake-ups, see §1).
- This project is released under **MIT** (see `LICENSE`); the English attribution notice is in [`ATTRIBUTION-EN.md`](ATTRIBUTION-EN.md).

## 10. Boundaries and disclaimers (stated honestly)

- ⚠️ **The body is plaintext on disk**: Syncthing's **transport** is end-to-end encrypted (a relay only ever sees ciphertext), but the message
  **as a file in the shared directory is plaintext**. Until body encryption (X25519 + AES-GCM) lands, **do not send sensitive content over this channel**.
- Metadata about the synced directory is visible to Syncthing relays; for confidential content, turn off public relays and use a LAN or a Tailscale network instead.
- This program **calls no model** and does not decide "whether to execute" for you; the agents themselves are not addressable — **what is addressable is the machine**, and identity is held by the post office on its behalf.
- **It guarantees "delivery", not "waking up"**: a wake-up is a bolt-on doorbell (same-host CLI calls / cross-host SSH wake-up, commands in §1) and
  **is not part of ACP-lite itself**; if the peer is off, or has no `watch` running, your letter just queues in its mailbox.
