# ACP-lite (Agent Connect Personal)

[简体中文](README.md) | **English**

**Hand this repository's link to your coding agent and let it install from this README.** This is not a
one-click SaaS, and there is **no** one-click installer either -- "humans bring the idea, the AI does the
building": what we worked out and debugged the hard way is written down here as steps an agent can just follow.
Once your agent has read this document, it can set the same thing up again on your own two machines.

> A **minimal implementation** of cross-host agent interconnect: one "post office" per machine, while agents
> still only read and write local files.
> Two ordinary computers behind NAT -- no public IP, no server.

![ACP-lite seven-agent collaboration topology](assets/acp-lite-topology-en.svg)

> Naming: **ACP-lite = Agent Connect Personal**. The final P is, **we hope, eventually read as Peace**.
> The diagram is an example collaboration group (two hosts, two agents each) -- substitute your own names; the three
> nicknames in it, **Blueberry (Hermes)**, **Cake (OpenClaw)** and **Rongmao (Muse)**, were **picked by
> my daughter**. 😄
>
> **Non-affiliation notice**: this project has **no relationship whatsoever** with Zed's *Agent Client Protocol*,
> OpenAI+Stripe's *Agentic Commerce Protocol*, or IBM's archived *Agent Communication Protocol*.
> When citing it, please use the full name "ACP-lite (Agent Connect Personal)".

**How to read this**: the **primary reader of this document is an AI agent** -- the body is organised as
"what to do -> the command to copy -> the pass check", so every step can be executed and verified on the spot.
A human only needs to hand the repository link to the agent. When something breaks, look at **FAQ "1. Common questions"**
first (how to connect, how to log in, which pitfalls we hit); for "why is it designed this way" see
**"2. Appendices"** -- skip them entirely if you just want to use it.
Placeholders: `<home-dir>` this host's **private** directory | `<shared-dir>` the directory the two machines
**sync** | `<agent>` / `<peer-agent>` agent names.
Program version = protocol version = **0.7.0**; the envelope format is defined by `ENVELOPE-FORMAT.md`.

---

## Step 1: Python dependencies (once on each machine)

```bash
pip install cryptography
```

It starts without it, but **cross-host messages are then rejected outright** (fail-closed, see Appendix A,
iron rule 5) -- so treat it as **required**.

## Step 2: Get the two machines exchanging files (the transport layer)

```powershell
winget install Syncthing.Syncthing          # Windows; on Linux/macOS use your package manager or the official download
python acp-deviceid.py --config <syncthing-home>/config.xml   # print this host's Device ID (does not need the Syncthing executable)
```

`<syncthing-home>` = Syncthing's config directory (the one holding `config.xml`): on Windows e.g.
`%USERPROFILE%\acp-home\syncthing`, on Linux/macOS e.g. `~/.config/syncthing`.
**Start Syncthing once first** (so it generates this host's identity -- `cert.pem` / `config.xml` show up in that
directory) before running the command above; **do not copy the bare command without `--config`** -- it only looks
in a few fixed default paths, and when the config directory is not in one of them (as in this project) it prints
"no cert.pem found".

The essentials (just follow them):

1. **Add each other's Device ID, in both directions**: A gives its ID to B and B adds A -- after which **A must add B back as well**. The classic symptom of adding only one side is a permanent `Hello EOF`.
2. **Pick any synced directory** (called `<shared-dir>` below); each machine points at its own local path. With two machines it is worth giving the **Folder ID the same name** on both, to make troubleshooting easier.
3. **Add the folder first, then place `.stignore`** (the order matters): in Syncthing, add `<shared-dir>` as a Folder **first**, and only then copy the repo's `.stignore` into the root of `<shared-dir>` -- it keeps out `~syncthing~*` / `*.tmp` as well as conflict copies `*.sync-conflict-*` (those also end in `.json`, and without the rule they get scanned as if they were letters). In the reverse order Syncthing may sync `.stignore` out as an ordinary file first and **the ignore rules never take effect**; once it is in place, **confirm in the Syncthing UI that this folder's "ignore patterns" have picked the rules up** -- only then are they really in effect.
4. **Keep big files out of the shared directory**: give large files a directory of their own; the mailbox holds small messages only.

## Step 3: Create the identity + verify fingerprints out-of-band

```bash
# Create the identity. --home is this host's private directory (it holds the private key and must NEVER go
# into the synced directory); --root is the directory Syncthing syncs
python acp.py --home <home-dir> --root <shared-dir> init --agent <agent> --display "Codex@desktop"

# Print this host's fingerprint
python acp.py --home <home-dir> --root <shared-dir> status

# Verify the peer's fingerprint out-of-band (in person / by voice -- never over the network), then trust it
python acp.py --home <home-dir> --root <shared-dir> trust --agent <peer-agent> --fingerprint xxxx-xxxx-xxxx-xxxx
```

Replace the placeholders per platform: on Windows, e.g. `--home %USERPROFILE%\acp-home --root %USERPROFILE%\acp-shared`;
on Linux / macOS, e.g. `--home ~/acp-home --root ~/acp-shared`.

**What `trust` requires (do not jump the order)**: `trust --agent <peer-agent>` reads
`<shared-dir>/peers/<peer-agent>.json` (**the peer's name card**). So the peer **must have run `init` first**, and
the name card **must have synced across** -- in other words, wait until **"both sides added each other's Device
ID" has succeeded and the shared directory is really syncing** before you `trust`.
Once the name card is there, a mismatched fingerprint is rejected outright; **while it is not there yet, `trust`
will not check it for you** (it just records whatever fingerprint you report), so the fingerprint **must come
from an out-of-band channel** (in person / by voice) -- never guess, never copy it from the network.
After `trust`, **run `status` once more** and check that the fingerprint on the "trusted peer" line **is exactly
the string you verified out-of-band** -- only then is the trust real. **A `trust` exit code of 0 does not mean the
check was right**: with no name card around it silently accepts any fingerprint you type, so this link in the
chain rests entirely on out-of-band verification.

Three rules you must keep:

- **Never omit `--root`**: without it the default is `<home>/shared` -- **exit code 0, and it looks like it worked**, while the letter actually lands in this host's private directory (see FAQ Q5).
- **Agent names must be unique across machines**: the two machines cannot both be called `codex` (they would overwrite each other's name card and crowd into the same outbox).
- **The private key never enters the shared directory**: under `--root` there should be nothing but `peers/`, `outbox/` and `.stignore`.

## Step 4: Send and receive (get this path working first)

```bash
python acp.py --home <home-dir> --root <shared-dir> send --to <peer-agent> --text "first test message" --reply answer
python acp.py --home <home-dir> --root <shared-dir> inbox      # on the peer
python acp.py --home <home-dir> --root <shared-dir> digest     # see everything pending in one screen (the token-saving way to receive)
python acp.py --home <home-dir> --root <shared-dir> ack <msg_id>
```

**The criterion**: the message was really sent only when **a file really shows up** in `<shared-dir>/outbox/<peer-agent>/`; do not judge by the exit code alone.

Command cheat sheet (every command takes `--home <home-dir> --root <shared-dir>`, omitted in the table):

| Command | What it does |
|---|---|
| `acp.py ... status` | identity / trust / inbox / brake status; prints this host's fingerprint |
| `acp.py ... send --to <peer-agent> --text "..."` | deliver one message; `--to '*'` = broadcast; `--reply none` = no reply needed (default `auto`) |
| `acp.py ... send --reply-to <msg_id> ...` | reply (auto `hops+1`) |
| `acp.py ... inbox` | list the inbox (add `--all` to include non-ok states) |
| `acp.py ... ready` | list only what is **genuinely executable** (subject to STOP and release tickets) |
| `acp.py ... send`'s `--reply` | `none` / `ack` / `answer` -- **just a token-saving envelope label** (the receiver can filter without reading the body); **it does not send a receipt by itself** -- a receipt still has to be sent by the other side |
| `acp.py ... digest` | condense the pending messages into one screen -- **the token-saving way to receive** (shows the last **30** by default; `--limit` adjusts it) |
| `acp.py ... ack <msg_id>` | confirm it is handled = **close the case**: delivery state becomes `done`, **the release ticket is voided**, and it disappears from `digest`; **only valid for the `ok` state** -- `untrusted` / `expired` and friends are all refused |
| `acp.py ... watch --loop --interval 3` | resident delivery (moves files only, never calls a model; idling burns no tokens); it records the messages it has seen in `<home>/state/seen.json` |
| `acp.py ... audit` | verify and inspect the hash-chained audit log |
| `python selftest.py` | run the entire offline self-test (gate / brake / forged release ticket / bad-message isolation); no network needed |
| `python acp_net.py --syncthing-home <syncthing-home> status` | show the network mode + whether the path used is direct or a relay |

## Step 5: Resident delivery (idling costs zero tokens)

```bash
python acp.py --home <home-dir> --root <shared-dir> watch --loop --interval 3
```

- **Autostart**: on Windows, Task Scheduler (triggered at logon); on Linux, `systemd --user` (or `crontab @reboot`); on macOS, `launchd`.
- Writing message files / Syncthing sync / `watch` writing received mail to disk **all cost no tokens** (the `watch` process makes **zero network connections** -- there is no HTTP client anywhere in the source); the **only thing that costs is "automatically calling a model", and this program does not offer that action**.

Two more things to know: **`watch` writes `<home>/state/seen.json`** (which messages it has seen; entries **expire after 7 days**) -- duplicate suppression relies on it, and **deleting `state/` makes old letters be delivered all over again**.
If you want autostart on Linux and have no unit file handy, here is a `systemd --user` template to follow (**this repository ships no ready-made unit -- drop your own into `~/.config/systemd/user/acp-watch.service` and adjust the paths**):

```ini
[Unit]
Description=ACP-lite watch (deliver only, never calls a model)
After=network-online.target

[Service]
Type=simple
ExecStart=/usr/bin/python3 %h/acp-lite/acp.py --home %h/acp-home --root %h/acp-shared watch --loop --interval 3
Restart=always
RestartSec=5

[Install]
WantedBy=default.target
```

Enable it with `systemctl --user daemon-reload && systemctl --user enable --now acp-watch`; to keep it resident **without anybody logging in**, add `loginctl enable-linger <your-username>`.

## Step 6 (optional): cross-host SSH wake-up

This project **ships no** wake-up channel of its own (`watch` never calls a model), but **a direct SSH wake-up has been verified working** (2026-10-14 / 10-15; 5 closed loops, all passed) --
**in our setup, and in these 5 runs**; another environment is not guaranteed to go as smoothly (for the DSH caveat see FAQ Q9).

**The goal is just one thing:** let machine A (say an always-on laptop) hand a task over `ssh` to a headless CLI (`dsh` / `codex`) on machine B
(say a desktop), with the result coming back to A over ACP. **Getting that to work is enough.**

**On permissions, plainly:** both machines sit on **your own LAN**, so giving `danger-full-access` at wake-up time is a deliberate
choice, not an oversight. Therefore:

- open port 22 **to the local subnet only** (the firewall rule below does exactly that) -- no port forwarding, no exposure to the internet;
- if the machine to be woken is **on the public internet**, add real authentication (key pair + jump host / VPN) instead of copying this level;
- file edits and deletions are **destructive** -- still ask the human first. An open permission does not mean acting without asking.
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

Before waking anything, run `python acp.py --home <acp-home> --root <shared-dir> ready`; **if `STOP` exists, do not wake** -- the brake outranks the task.

Wake-up commands (the prompt goes **through a file + stdin**, so neither Chinese text nor special characters get mangled by the shell):

```cmd
rem Wake Codex (the sandbox level must make the target directories writable -- see FAQ Q1)
if not exist "%TEMP%\codex-wake" mkdir "%TEMP%\codex-wake"
codex exec -s workspace-write --skip-git-repo-check -C "%TEMP%\codex-wake" ^
  --add-dir "<shared-docs>" --add-dir "<shared-dir>" --add-dir "<acp-home>" ^
  - < prompt.txt
```

Save the following as `wake-dsh.cmd` next to `prompt.txt`, then run the script itself:

```cmd
@echo off
setlocal
set "DSH_PERMISSION_MODE=danger-full-access"
set "PROMPT_FILE=%~dp0prompt.txt"
if not exist "%PROMPT_FILE%" (echo [FAIL] prompt.txt not found & exit /b 2)
if not exist "%TEMP%\dsh-wake" mkdir "%TEMP%\dsh-wake"
cd /d "%TEMP%\dsh-wake"
rem the bin.js path follows `npm root -g`; on Windows it defaults to %APPDATA%\npm\node_modules
node "%APPDATA%\npm\node_modules\@deepseek-ai\dsh\lib\bin.js" --profile headless - < "%PROMPT_FILE%"
```

**One wake-up = one fresh session (do not reuse a session)**

Do not pass `--session-id` to continue one long conversation. Each task is independent, and reusing a session makes the context
accumulate round after round: every wake-up re-reads the whole history, so **each call costs more than the last**, and "what was
actually said this time" stops being answerable.

The price is one leftover session entry per wake-up. That entry **is the audit trail**, not litter -- clean them up in batches later.

**Leave a receipt after every wake-up (audit / billing / traceability)**

```text
one wake-up -> one ACP message (msg_id, signed)
            -> one CLI session   (session id, replayable)
            -> one receipt       (the six lines below)
```

Write it under a shared directory (e.g. `<shared-docs>/wake-log/2026-10-20-1420-<task>.md`). Six lines are enough:

```text
msg_id   : hermes-<host>-<date>-<time>-<hash>
time     : 2026-10-20 14:20 +08:00
task     : <one line>
by       : <agent>@<host> (CLI: dsh|codex / session id)
result   : ok | fail | partial -- <one line>
receipt  : outbox/<agent>/<msg_id>.json (signature verifiable)
```

**Why bother**: ACP carries only the *request*, and the CLI only *executes once*. **ACP messages alone never show what was done;
sessions alone never show whose bill it is on.** Joining them by `msg_id` gives both the audit trail and the billing anchor.

Fine to skip when it is just you; **hand the project to anyone else and these six lines are mandatory** -- without them nobody
can audit it, nobody can bill it, and nobody dares use it.

**One character off in the environment variable and the whole chain breaks**

```cmd
WRONG: set "DSH_PERMISSION_MODE=danger-full-access "    <- trailing space inside the quotes
RIGHT: set "DSH_PERMISSION_MODE=danger-full-access"      <- exact value
```

What happens (measured symptom): `dsh` validates the level literally -> modules do not activate -> the `pwsh` tool stays pending -> startup fails with `0xC0000142`.
Pass check: `echo [%DSH_PERMISSION_MODE%]` must print `[danger-full-access]` -- a space before `]` means it is wrong.

**Five pitfalls: symptom -> root cause -> do this -> pass check**

| # | What you see | Root cause | Do this | Pass check |
|---|---|---|---|---|
| 1 | `pwsh` is missing, or is 5.1 | DSH's pwsh tool needs PowerShell 7; Windows ships 5.1 | Install PowerShell 7 and put `pwsh` on PATH | `pwsh -v` prints `7.x` |
| 2 | Startup fails with `0xC0000142`; pwsh tool pending | The level value has a trailing space, so the schema's literal check fails | Use the exact value from the WRONG / RIGHT pair above | `echo [%DSH_PERMISSION_MODE%]` prints `[danger-full-access]` |
| 3 | prompt.txt exists, yet "file not found" | The script `cd`s first, then `< prompt.txt` is a stale relative path | Resolve the prompt to an absolute path with `%~dp0` **before** `cd` | `if not exist "%PROMPT_FILE%" exit /b 2` never fires |
| 4 | The variable is set but dsh cannot see it (silent no-op) | The variable is not in the same process as dsh: `cmd /c "set X=Y && dsh"` chaining, or a `dsh.cmd` wrapper in between | In one `.cmd`, `set` then call `node ...\bin.js` directly, bypassing `dsh.cmd` | Have the prompt print `$env:DSH_PERMISSION_MODE`; it must echo `danger-full-access` |
| 5 | The same `dsh` behaves / configures differently than expected | PATH holds two `dsh.cmd` files -- the desktop build (runs `.exe`) and the npm global one (runs `bin.js`) -- each with its own config dir | `where dsh` and read the first hit; for determinism hard-code `node ...\bin.js` in the template | The config dir / version in the startup banner matches what you expect; the two coexist without conflict, and only `resume` can lose the write race |

```bash
# Two agents on the same host can also call each other over CLI, in both directions
# (substitute your own CLIs -- the same holds)
openclaw agent --message "reply with just one word: received"   # Blueberry (Hermes) → Cake (OpenClaw)
hermes -z "reply with just one word: received"                  # Cake → Blueberry (the reverse holds too)
```

A wake-up carries only a "**pointer**" (the absolute path of the received letter, which is where `msg_id` lives); the body is still read by the other side from its own mailbox --
**ACP is the ledger, the CLI is the doorbell; a doorbell cannot replace a ledger**.

**Acceptance: all three must hold, and the exit code is not one of them.**

1. **Artifact on disk**: `dir <artifact>` lists a file, size > 0, timestamp later than this wake-up.
2. **Audit chain grows**: `python acp.py --home <acp-home> --root <shared-dir> audit` gains one entry, and the newest hash matches.
3. **Signed receipt**: a reply appears under `outbox/<your-agent>/` and `verify` passes.

`exit 0` may merely mean "it said something": no artifact, no ledger entry, no reply = it did not do the work.

**When the machine is off (out-of-band power-on)**

SSH needs the OS running, so it cannot wake a powered-off machine. For a real "boot it from anywhere", use a **smart plug plus the motherboard's AC power-loss restore** (plug costs about USD 8):

```text
1. BIOS: Advanced -> APM Configuration -> Restore AC Power Loss = Power On
2. Windows: turn OFF Fast Startup, otherwise a "shutdown" is really a hibernate
   and the machine will not boot on power restore
   Control Panel -> Power Options -> Choose what the power buttons do -> untick
   "Turn on fast startup"
3. In the plug's app, set "power-loss behaviour" to ON (the middle option)
   x Do NOT pick "remember": it relies on the plug's own guess at its last state,
     which measured unreliable
   x Do NOT pick "off": the plug then outputs nothing and the board never sees
     AC power return
4. Wall socket -> smart plug -> PC power supply
5. To boot: cut power in the app, wait 30 s, restore power -> the PC starts itself
6. Day to day: leave the plug powered and use the case button -- it is just a socket
```

Measured note (2026-10-19; three consecutive clean runs on this configuration): cutting power for 30 s and restoring it booted the host by itself. Let the power LED go fully dark before cutting power -- cutting too early logs `Kernel-Power ID 41` (unexpected loss) and the next power-on may not start. **Do not toggle the plug often** -- use it only when you actually need a remote boot.

**A wake-up must be followed by a report (a collaboration discipline, not an implementation detail of one machine)**

- **The woken side** (Codex / DSH): stay visibly "processing" while working (do not exit the session early); when done you **must send a signed ACP reply + a broadcast** -- going quiet leaves the waker unable to tell whether you never got it, are still working, or already finished.
- **The waker** (Blueberry and friends): **watch until the receipt arrives**; report completion -- or timeout -- to the human **proactively**, and never make them ask.
- **Why**: the human **does not watch the screen and cannot see background windows**. "Fire and forget" leaves them **unable to tell whether the task is running, stuck, or already finished** -- the experience degrades.
- One-line principle: **"Either you can see it working, or the completion must come back with a reply -- one of the two is mandatory."**

### Connecting a cloud personal agent (overview)

Everything above is about **another machine of your own** -- you can SSH into it, set a sandbox, wake it at will.
**A cloud personal agent is a different thing**: it runs on someone else's public cloud, and you have neither root nor a CLI.

This section covers the general mechanism. **The two concrete cases are FAQ Q16 (Grok Bot) and Q17 (Meta Muse).**

#### Common ground: both kinds go through the same ledger

```
ACP letter (ledger) -> Syncthing sync (transport) -> peer processes -> reply (ledger)
```

**Only the doorbell differs:**
```
Your own machine : SSH knocks, you can wake it any time
Cloud agent      : no doorbell -- it acts only when it or its owner triggers it
```

#### Two layers of trust, both required

| Layer | Job | Basis | Failure mode |
|---|---|---|---|
| **Syncthing** | file sync | Device ID pairing + folder approval | files never arrive, `need > 0` |
| **ACP-lite** | signed envelopes | out-of-band fingerprint check, then `trust` | files arrive but messages are rejected |

- A Device ID is a **machine-level** identity; an ACP fingerprint is an **agent-level** identity.
- Device only, no `trust` -> sync works, envelopes still rejected.
- `trust` only, no device -> envelopes are written, the peer never receives them.

#### Split directories into three layers (see Q15)

```
public announcements   it can read
peer-specific area     it reads and writes
internal areas         it cannot see
```

#### The three typical reasons it will not connect

**1. Your own relay is dead** (most common)
```
the log shows consecutive "TLS handshake i/o timeout"
-> everything inside the LAN is fine, every cloud peer goes dark
-> fix: restart your own Syncthing and let it re-pick a relay
```

**2. Discovery cannot find the peer's address -- that is not a fault**
```
in relay mode both sides register with the relay, which introduces them
neither needs to know the other's public IP
```

**3. The peer is offline**
```
there is no resident daemon in the cloud; going offline is normal
it reconnects automatically when it returns (measured 6-9 minutes)
```

#### The boundary: what it can and cannot do

```
Can:    read/write its own exchange area, send and receive signed envelopes,
        process tasks automatically once triggered
Cannot: be woken over CLI / SSH; it will not start up and poll on its own
```

**=> Dispatching work must be designed around "human-triggered".**
**This is a form-factor difference, not a configuration gap.** Cloud personal agents such as WorkBuddy will most likely land in the same place.

---

## 1. Common questions (FAQ: 2 definitions + 4 how-to-connect + 9 pitfalls + 2 cloud onboarding)

⚠️ **The boundary first**: every answer below comes from **this one particular setup of ours** --
**an Ubuntu netbook + a Win11 desktop + Syncthing + Clash (on the Windows side)**, with the agents
`codex-desktop` / `dsh-desktop` / `hermes-netbook` / `openclaw`. **Another environment need not behave the
same**, so weigh the answer against your own machines; do not treat this as "universal plug-and-play".

### Definitions (Q0 → Q0b)

**Q0: What is ACP-lite?**
A: ACP-lite (Agent Connect Personal) is a **minimal implementation** of cross-host agent interconnect: one "post office" per machine, while agents still only read and write local files; two ordinary computers behind NAT are enough -- no public IP, no server.

**Q0b: Is it a one-click install / one-click uninstall SaaS?**
A: **No.** There is no store, no installer, **no uninstall button** -- **we built this bit by bit**: humans bring the idea, the AI does the building.
There is exactly one correct way to use it: **hand the repository link to your coding agent and let it work through this document** -- you need not read every word yourself, and neither does the agent.

### How to connect (Q1 → Q4)

**Q1: How does Codex connect?**
A: Two layers. **Receiving**: share the same `<shared-dir>` with Syncthing; `acp.py` only reads and writes files, so no resident service is needed.
**Waking up**: over SSH across hosts, the command must use **`-s workspace-write`** and add **every** target directory with `--add-dir` --
`<shared-docs>` (documents), `<shared-dir>` (the mailbox), and **`<acp-home>` (the easiest one to miss: without write access you get "the letter was sent, the ledger was not written")**.
The startup banner prints the effective writable roots and can be used as hard evidence. **The full wake-up command is in step 6** (if this host is Windows, log in per Q3 first).

**Q2: How does DSH connect?**
A: **DSH has no `--add-dir`**: its writable roots are hard-wired to "the workspace + `/tmp` + the system temp directory", with no extension hook, so you must **hand over the whole machine**: at wake-up time set `DSH_PERMISSION_MODE=danger-full-access` **in the same process**, and **switch to a clean working directory**
(e.g. `%TEMP%\dsh-wake`; do not share a sandbox directory with another agent). Both are required -- without the level it cannot write anything, and with a dirty directory the command fails to start already in the sandbox preparation stage.
**The copyable template, the WRONG / RIGHT variable pair, and the five pitfalls with pass checks are in step 6** (that is the single source of truth; this question only states the principle -- if this host is Windows, log in per Q3 first).

**Q3: How do I log in over SSH?**
A: **Add the device → install the server → punch through → log in**, four small steps:

```powershell
# 1) This host is Windows (the side being connected to): install the OpenSSH server and open port 22 to the local subnet only
Add-WindowsCapability -Online -Name OpenSSH.Server~~~~0.0.1.0
Set-Service sshd -StartupType Automatic; Start-Service sshd
New-NetFirewallRule -Name OpenSSH-Server-In-TCP-LAN -DisplayName 'OpenSSH Server (LAN only)' `
  -Enabled True -Direction Inbound -Protocol TCP -Action Allow -LocalPort 22 -RemoteAddress 192.168.0.0/24
```

```bash
# 2) The peer is Linux (the initiating side): install the client (usually already there)
sudo apt install openssh-client

# 3) Exchange public keys for passwordless login (run on the initiating side; press Enter throughout)
ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519 -N ""
ssh-copy-id <peer-username>@<peer-LAN-IP>

# 4) Verify: log in + run one harmless command
ssh <peer-username>@<peer-LAN-IP> "hostname && date"
```

**Get the direction straight first**: the scenario in step 6 is **Linux (initiator) → Windows (the side being woken, Win11)**, and the `ssh-copy-id` above is the **Linux / macOS** spelling.
**Windows' native OpenSSH has no `ssh-copy-id`** -- when Windows initiates, use the equivalent commands in `cmd`:

```cmd
ssh-keygen -t ed25519 -f %USERPROFILE%\.ssh\id_ed25519 -N ""
type %USERPROFILE%\.ssh\id_ed25519.pub | ssh <peer-username>@<peer-LAN-IP> "cat >> .ssh/authorized_keys"
```

- **Do not mix up the two kinds of identity**: Syncthing's Device ID is **per machine** (one per host; `python acp-deviceid.py` computes it), while an ACP agent fingerprint is **per identity** (one per agent).
- Once you are logged in and want to **wake a particular machine**, the command is in **step 6**; SSH only "knocks on the door" -- the ledger still belongs to ACP.
- Two known inconsistencies, do not trip over them: **receiving** only needs the firewall to let port 22 through **and** the peer's `sshd` to be running (`Get-Service sshd`);
  **waking up** additionally needs the target directories to be **writable** -- a successful device pairing does not mean wake-up can do work.

**Q4: How does a cross-host "wake-up" actually work?**
A: **SSH only carries a pointer** -- it sends one message whose content is "go read the letter at `<absolute path>`"; the woken CLI then reads the body from its own mailbox.
So the chain is **ACP sends the request + SSH sends the signal**, and a dropped SSH does not lose the letter (it sits in the shared directory).
The cost: a foreground SSH connection **dies with the session**, so long jobs have to move to a scheduled task (see Q7).

### Pitfalls (Q5 → Q13)

**Q5: Can `acp.py --root` be omitted?**
A: **No.** When omitted it defaults to `<home>/shared` (not the shared group directory), with **exit code 0 and no error at all** -- but the letter lands in
this host's private directory and nobody in the group ever sees it. Always write `--root <shared-dir>` explicitly when sending or replying; the criterion is that a file really shows up in `outbox/<recipient-agent>/`.
**`--home` has a default too** (`~/.acp-personal`), and the two defaults together are the worst trap -- omit `--home` and `--root` follows it down to
`~/.acp-personal/shared`, and the letter is off on its own again. So **write both explicitly**.

**Q6: How do I pass Chinese bodies / Chinese prompts?**
A: **Not through command-line arguments** (`cmd` / PowerShell read UTF-8 as GBK and you receive garbage like `鎶婅繖鍙ヨ瘽…`;
non-interactive SSH even re-tokenizes). **Use a file + stdin**: write the body to a UTF-8 file first and hand it to the woken
CLI as `- < prompt.txt`; when sending Chinese mail, also read the file and call `acp.main([...])` **inside the same Python
process** -- never let Chinese text pass through the shell.

**Q7: Should a wake-up use `schtasks` or a foreground SSH session?**
A: **Short jobs: foreground SSH; long jobs: a scheduled task.** `schtasks` pops a console window but **survives the SSH
disconnect**; foreground SSH pops nothing but **dies with the session**. Background jobs started with `start /b` get
reaped by the SSH session -- don't use them.

**Q8: How do I pass environment variables to the woken CLI?**
A: **Only with a single-process `set`**: `set "DSH_PERMISSION_MODE=danger-full-access"` immediately followed by `dsh …`
(the same `.cmd`, the same process). **Do not chain it as `cmd /c "set X=Y && dsh"`** -- the level does not get through, and
the symptom is **silent zero output** (no error, nothing on disk).

**Q9: After a wake-up, DSH is "hog-tied" and reports `SetNamedSecurityInfoW failed Win32 5`?**
A: Setting `DSH_PERMISSION_MODE=danger-full-access` **alone is not enough** -- it also needs a **clean working directory**:
a dirty directory cannot have its ACL granted (`grantWrite(<dir>)` is refused, Win32 5 = access denied), and the command
**fails to start already in the sandbox preparation stage**. Wake it again from a clean directory (give DSH its own
clean cwd such as `%TEMP%\dsh-wake`; do not share it with another agent). This one **does not reproduce reliably** -- don't advertise it as "always breaks".

**Q10: Does having the desktop app open interfere with CLI wake-ups?**
A: **No** (measured): the desktop app and the CLI wake-up are **independent sessions** with no write conflict (with 5 DSH
desktop processes running, a CLI wake-up still finished in 18 seconds and wrote outside the workspace). The only exception
is "taking over an existing session": while the Codex desktop client holds the write lock, `resume` fails
(`already has an active writer`).

**Q11: Same Wi-Fi, yet Syncthing says "relay"?**
A: LAN discovery is being blocked -- check **TUN / proxy** first. The criterion is the "connection type" in the Syncthing
UI: **TCP LAN = direct**, **relay = the normal state across networks**, **relay while on the same Wi-Fi = abnormal**.
After a network change, don't sit and wait for slowness -- measured, waiting passively takes about **4 min 50 s**, while an
active `python acp_net.py --syncthing-home <syncthing-home> kick` takes about **2 s**.

**Q12: All the Syncthing settings on Windows are correct, and it still never connects?**
A: Nine times out of ten it is **`ALL_PROXY`**. Syncthing v2.x goes through `proxy.FromEnvironment()`, **and recognizes
only `ALL_PROXY` / `all_proxy`** -- **it does not read `NO_PROXY`** -- so every dial-out is picked up. The log tells you:
normal is **`Dialer logging disabled, as no proxy was detected`**; intercepted is `Proxy settings detected` + `error: EOF`.
The fix is to clear them all before starting Syncthing (**`ALL_PROXY` is the easiest one to miss**):

```cmd
set ALL_PROXY=
set all_proxy=
set HTTP_PROXY=
set HTTPS_PROXY=
set http_proxy=
set https_proxy=
set NO_PROXY=*
```

> Windows environment variable names are **case-insensitive**: `ALL_PROXY` and `all_proxy` are **the same variable** --
> setting `ALL_PROXY=…` and then `all_proxy=''` just deletes it, and the experiment contradicts itself. **The correct
> spelling: clear the other variables first, and set `ALL_PROXY` last.**
> With the same Clash, the Linux side is unaffected by default (no process proxy variables, no TUN, no proxy).

**Q13: What other pitfalls "look fine but are actually broken"?**
A: Four, all measured:

- **`--root` omitted**: exit code 0, the letter lands in the private directory (see Q5).
- **`state=idle` does not mean syncing is healthy**: a single failing file **blocks the whole folder**; read the `pull:` errors in the log instead of trusting the state alone.
- **Deleting the source file breaks the peer's pull**: the file the peer is pulling gets deleted → `pull: no such file` → the whole folder stalls and retries. Confirm the peer is not pulling before you delete.
- **`git push` crashes / pops a dialog on Windows**: under a non-interactive account schannel reports `SEC_E_NO_CREDENTIALS`, and with a credential manager in the chain you get a dialog that needs a human click.
  The unattended spelling is **switch to the openssl backend + clear `credential.helper` + put the token in the URL** (the repo's `push-acp.cmd` is exactly this):

```bash
git -c http.sslBackend=openssl -c http.proxy=http://127.0.0.1:7897 -c credential.helper= \
  push https://x-access-token:<GH_TOKEN>@github.com/furoute/acp-lite.git main
```


### Connecting a cloud personal agent (Q14)

**Q14: Can a cloud personal agent be connected?**
A: **Yes. The general mechanism and its boundary are in the "Connecting a cloud personal agent (overview)" section at the end of Step 6.**

Only the two concrete cases are listed here:
- **Q16** -- [mango@GrokBot (Grok Bot)](#case-one-mangogrokbot-grok-bot-q16)
- **Q17** -- [muse-cloud (Meta Muse)](#case-two-muse-cloudmeta-muse-q17)

---

### How to split directories for an external agent (Q15)

**Q15: Once an external agent is on board, how should the shared directories be laid out?**
A: **Three layers, each its own folder. Never let an external agent share a directory with internal files.**

Measured on 2026-10-20: an external agent could read every internal file (including a personal resume) because it shared `shared-files`.
The fix is three Syncthing folders that do not nest:

| folder | Holds | Visible to |
|---|---|---|
| `acp-shared-public` | announcements, protocol notes, collaboration rules, runbooks, templates, public name cards | internal + **every external (read-only)** |
| `acp-shared-<peer>` | the exchange area for one external peer | internal + **that peer** (other externals cannot see it) |
| `acp-shared` / `shared-files` | mailbox and runtime facilities / internal files | **internal only** |

**Four hard constraints** (each one was learned the hard way):

1. **The three folders must be independent** -- Syncthing authorises per folder x device, not per subdirectory; once the parent is shared, permissions on a child mean nothing.
2. **The public area is not a mailbox** -- whichever directory `--root` points at, its `outbox` is visible to everyone on that root. Keep announcements and message traffic in different roots.
3. **`outbox/<agent>/` holds only `.json`** (`cli_calls.jsonl` is a log exception); large files live in the file area and the message carries only a path.
4. **The public area accepts a fixed extension whitelist only** -- `.md .txt .json .pdf .png`; `.cmd .ps1 .exe .py .bat .sh` never. Wake-up scripts especially must stay out: if an external party can edit one, the next wake-up runs arbitrary code.

**Two things that are easy to miss:**

- **Removing a share is not a recall.** The other side already has a local copy; moving the folder out only stops updates, it does not delete theirs. The design prevents the next leak, it cannot undo the last one.
- **Changing `--root` is not the same as changing visibility.** `to` decides *who handles it*; `root` decides *who can see it*.

### Case one: mango@GrokBot (Grok Bot) (Q16)

**Q16: Which cloud agent was connected first, and how?**
A: **2026-10-19, `mango@GrokBot` (an Alibaba Cloud VM, public egress), working in about two hours.**

It is someone else's conversational bot — not on any of our machines, and we did not install it.

**Steps:**
```
1. Create a peer-specific directory / folder, shared only with it + the internal hosts
2. Pair the Syncthing Device IDs
3. Verify the ACP fingerprint out of band, then trust
4. hello -> receipt -> closed loop
```

**Four pitfalls hit at the time:**
- A leftover `__pycache__` made a directory undeletable on the remote side, retrying every 60 s and dragging the whole folder down
- Writing a file did not trigger a rescan -> the peer never saw it
- An envelope stuck at `.tmp` -> half-written content got read
- The connection did not self-heal after a reboot; pausing and resuming the device forced a reconnect

**Note: it drops the connection periodically -- that is normal**

GrokBot's VM is **reclaimed / put to sleep by the platform** when idle, and the Syncthing process stops with it -> the connection drops (`connected=false`).
**Once the VM is woken, it reconnects by itself; onboarding does not need to be redone.**

```
symptom:  connected=false, need stays at 0, the peer still has addresses in discovery
cause:    the cloud VM was reclaimed -- not a misconfiguration, not broken sync
fix:      wake the VM and wait for it to reconnect (within minutes)
```

**=> Collaboration design must account for this: work dispatched to a cloud agent has to be "human-triggered"; never assume it is always online.**
**This is one of the reasons we define it as "human-triggered, automatic processing".**

**Full record:** → **[Connecting a cloud agent to ACP-lite: mango@GrokBot, first cross-internet onboarding](CLOUD-AGENT-ONBOARDING-mango-20261019.md)**

### Case two: muse-cloud (Meta Muse) (Q17)

**Q17: How was the second cloud agent different from the first?**
A: **Same three-layer structure, completely different failure modes — mostly relay and platform permissions.**

`muse-cloud` (Meta's cloud personal agent) was connected on 2026-10-21. The structure followed Q15, but these problems were new:

**1. Relay nodes go down**
```
The local relay 101.132.x.x timed out on 10 consecutive TLS handshakes
-> symptom: everything inside the LAN worked, every cloud peer went dark
-> fix: restart the local Syncthing, which re-picked a relay (171.213.x.x)
-> result: everything back within 60 seconds
```
**Lesson**: LAN fine, cloud all down — suspect your own relay first, not the peer.

**2. Never write a half-finished name card**
When registering a peer, if you only have its fingerprint and not its public key, **do not write a card that lacks `pub`** — the peer will read a broken card. Wait for the card generated by its own `init` to sync over.

**3. Platform permissions: step-by-step confirmation**
On the Muse side every connection and every folder needs a human click, unlike GrokBot where one step does it. **That is platform mechanics, not a configuration error.**

**4. No resident daemon in the cloud; going offline is normal**
While the peer is offline, `connected=false` and `need` stays at 0; it reconnects automatically when it comes back (measured 6-9 minutes).

**5. The proxy is not an obstacle**
The peer can only reach the internet through a proxy and cannot connect to direct ports — but **relay mode never uses direct connections**, so the worry was unfounded.

**Full record:** → **[Connecting and joint-debugging a cloud agent: muse-cloud](CLOUD-AGENT-ONBOARDING-muse-cloud-20261021.md)**

---

## 2. Appendices (for people: why it is designed this way; skip them if you just want to use it)

### A. The five iron rules

1. **On-host behaviour is unchanged** -- the original file channel stays as it is; this program neither reads nor writes `mailbox/`.
2. **Cross-host shares directories, never a whole machine** -- Syncthing / Tailscale / a cloud drive / a USB stick can all serve as the transport.
   With a single in-group peer one directory is enough; once an external agent joins, split by the **three layers in Q15** (public / peer-specific / internal), each its own folder.
3. **Private keys never enter the shared directory** -- `--home` is host-private; the shared directory holds only name cards and outboxes.
4. **Receiving never calls a model** -- `watch` only writes to disk and appends to the audit log; idling burns no tokens.
5. **Missing dependency means refuse-to-receive (fail-closed)** -- without `cryptography` on the host, cross-host messages are **rejected by default**;
   to receive anyway for a self-test you must pass `--allow-unsigned` explicitly, and such messages are marked `unverified` and **never enter `ready`**.

### B. The outbound gate (the heart of the security model)

| Action `--requires` | Who may do it |
|---|---|
| `none` / `read` | automatic |
| `write` / `send` / `pay` / `delete` | **requires a one-shot release ticket signed by a human** |

**Hard constraint**: `--requires write/send/pay/delete` **must be paired with `--action exec`**. When `--requires` is not
`none` and `--action` is still the default `infer`, `send` **refuses it outright as a "semantic contradiction"**
(`infer` is only for understanding and answering -- it cannot pay / send / delete).

```bash
python acp.py ... userkey                 # create the L2 human key (passphrase-encrypted, host-local, only you know the passphrase)
python acp.py ... approve <msg_id>        # human release: prompts for the passphrase
python acp.py ... stop                    # brake: every outbound action stops at once (receiving is unaffected)
python acp.py ... stop --off              # release the brake
```

- **The agent cannot obtain the passphrase ⇒ it cannot sign its own release ticket.** This is how "an injected agent must not issue itself a permission slip" is grounded.
  A ticket **must be signed by the L2 human key** and is verified at `ack` time; it is bound to "message ID + action digest + validity window" -- change it and it is void, use it once and it is spent, replaying it does nothing. An agent writing its own `approved-*.json` file does not work.
- **`STOP` is a file**: as long as the filesystem is there, the brake works -- no model, no network needed. **While the brake is on, `ack` is refused across the board.**

### C. The cross-host envelope

The semantics of `to` are like **@-mentioning someone in a group chat**: a message in the shared directory is visible to every member of the room (the file simply sits there; there is no confidentiality whatsoever), and `to` only decides **"who is called out, and who should act"**:

| Value of `to` | Meaning | Other members |
|---|---|---|
| `dsh-desktop` | point-to-point: **only DSH is asked to act** | they can see it, but their `watch` neither delivers nor executes it (bystanders) |
| `*` | broadcast: **everyone is asked to act/respond** | delivered normally, each decides for itself |

So "point-to-point" in this project means **addressed but not encrypted**. Do not put anything in here that others should not see.

| Rule | Field | Effect |
|---|---|---|
| Single writer | directory `outbox/<self>/` | nobody ever steps on anyone else's files; no Syncthing conflicts |
| Idempotence | `idem` | duplicates are dropped at the delivery layer (mail re-sends / sync jitter are safe) |
| Loop protection | `hops` / `max_hops` | over the cap it is blocked, so the two sides cannot auto-ignite each other |
| Expiry means refusal | `expires_at` | a task from three days ago will not suddenly auto-execute when you boot up |

> `hops` guards against **endless loops**, not against "multi-round exchanges": the default `max_hops=4` allows 4 round trips; for a strict "reply only once", add `--max-hops 1`.
> **One bad message does not take down the others in the same round** (it is marked `rejected/malformed` and skipped).

The field-level specification is in `ENVELOPE-FORMAT.md`. **A hand-written envelope has no signature → it is always rejected**; don't hand-write, use `send`.

### D. Positioning: compared with MCP / A2A / message middleware

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

### E. Network mode and the token-saving ledger

```bash
python acp_net.py --syncthing-home <syncthing-home> status      # show the mode + which path is actually used
python acp_net.py --syncthing-home <syncthing-home> mode auto   # default mode (formerly called wan)
python acp_net.py --syncthing-home <syncthing-home> mode strict # strict mode (formerly called lan)
python acp_net.py --syncthing-home <syncthing-home> kick       # reconnect immediately after a network change
# <syncthing-home> = Syncthing's config directory (contains config.xml):
#   Windows example: %USERPROFILE%\acp-home\syncthing | Linux/macOS example: ~/.config/syncthing
```

- In the default `auto` mode the measured path is a direct LAN connection (`<peer LAN address>:22000 isLocal=True`); the relay merely sits on standby as `Joined relay` -- **public servers are the spare tyre, not the main road**. `strict` registers no address at all, and the price is that you cannot find the peer across networks.
- Saving tokens: `--reply none` needs no reply, `--reply answer` needs an answer, and `digest` reads it all at once. **`watch` never calls a model.**

### F. Deployment notes


| Item | Notes |
|---|---|
| **Keep clocks in sync (NTP)** | if the two machines drift too far, `expires_at` is misjudged (a fresh message is treated as expired) |
| **Shared folders must be siblings, never nested** | nesting makes the same file exist twice |
| **Deleting propagates** | under two-way sync "delete here = delete there"; to keep one side intact set it to `send-only` |
| **Re-trust after rebuilding the identity** | `init --force` replaces the key ⇒ the peer immediately sees `untrusted` and you must verify the fingerprint out-of-band again |
| **Watch out when the fingerprint changes** | `trust` blocks "new fingerprint ≠ recorded fingerprint"; only after you confirm does `--force` update it (anti-man-in-the-middle) |
| **Anyone can write `peers/`** | name cards live in the shared directory and any syncing party can overwrite them (low risk). TOFU (trust-on-first-use: lock the fingerprint on first sight, warn when it changes) is a possible future step |
| **A device in `config.xml` ≠ the peer is online** | to judge "are we connected", look for real evidence: **receiving a letter from the peer** > the peer's completion > a config entry |
| **Don't use `ACP_USERKEY_PASSPHRASE` in production** | that environment variable is for self-tests; in production use interactive passphrase entry so the passphrase is not inherited by child processes |
| **Audit / self-test** | `acp.py audit` verifies the hash chain; `python selftest.py` runs the whole flow using two temporary "machines" (**the item count is whatever the program prints**) |

### G. Dependencies and attribution

- **The communication layer is not something we invented**: cross-host communication is **built on top of [Syncthing](https://github.com/syncthing/syncthing)**
  (Syncthing is an open-source continuous file-sync tool created by Jakob Borg and community contributors, now maintained by the
  Swedish non-profit Syncthing Foundation together with the community). **We did not write the sync layer and we claim no originality
  over it** -- our thanks go to the Syncthing project and its maintainers. All we added is a thin layer of **signed envelopes + hash-chained audit**.
- **Runtime dependencies**: Python 3.9+, `cryptography`, Syncthing (plus OpenSSH if you want cross-host wake-ups, see step 6).
- This project is released under **MIT** (see `LICENSE`); attribution notice: **the Chinese notice is above**, the English one is in [`ATTRIBUTION-EN.md`](ATTRIBUTION-EN.md).

### H. Boundaries and disclaimers (stated honestly)

- ⚠️ **The body is plaintext on disk**: Syncthing's **transport** is end-to-end encrypted (a relay only ever sees ciphertext), but the message
  **as a file in the shared directory is plaintext**. Until body encryption (X25519 + AES-GCM) lands, **do not send sensitive content over this channel**.
- Metadata about the synced directory is visible to Syncthing relays; for confidential content, turn off public relays and use a LAN or a Tailscale network instead.
- **The audit chain guards against "changing the record afterwards", not against "failing to record"**: having an audit does not mean having accountability.
- This program **calls no model** and does not decide "whether to execute" for you; the agents themselves are not addressable -- **what is addressable is the machine**, and identity is held by the post office on its behalf.
- **It guarantees "delivery", not "waking up"**: this project **ships no wake-up channel of its own, but a wake-up has been verified working** (same-host CLI calls / cross-host SSH wake-up,
  commands in step 6), and **it is not part of ACP-lite itself**; if the peer is off, or has no `watch` running, your letter just queues in its mailbox.

### I. Pushing to GitHub over SSH (recommended)

On Windows, pushing over HTTPS can crash in `git-remote-https` or block on a `schannel`
credential prompt (`SEC_E_NO_CREDENTIALS`). SSH push bypasses that component, works for
unattended pushes after a one-time setup, and keeps the private key on the local machine.

1. **Generate a key**: use a separate key for each machine and each agent; never share a
   private key. Replace `<name>` and `<host>` with your own identifiers:

   ```bash
   ssh-keygen -t ed25519 -C "<name>@<host>" -f ~/.ssh/id_ed25519_<name> -N ""
   ```

2. **Add the public key**: inspect the generated `.pub` file, then add it to GitHub under
   **Settings → SSH and GPG keys → New SSH key**. Only the repository owner can do this;
   an agent cannot add a key to the GitHub account. Use `<name>@<host>` as the Title so
   the key can be identified and revoked independently later.

3. **Verify authentication** with the new private key:

   ```bash
   ssh -i ~/.ssh/id_ed25519_<name> -o IdentitiesOnly=yes -T git@github.com
   ```

   Success reports `Hi <user>! You've successfully authenticated...`. Exit code 1 is
   expected for this check.

4. **Switch the remote to SSH**:

   ```bash
   git remote set-url origin git@github.com:<owner>/<repo>.git
   ```

Cautions:

- Never share or commit a private key. Give only the `.pub` public key to the repository
  owner.
- When several machines maintain the same branch, run `git fetch` before pushing and
  compare with the remote. If Git reports `! [rejected] ... (fetch first)`, run
  `git pull --rebase` and push again.
- A restricted environment may block outbound SSH to GitHub. As a special case, route
  through a local proxy to `ssh.github.com:443`; configure that command for the
  environment and never put proxy credentials in the repository.
