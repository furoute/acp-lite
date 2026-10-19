# Connecting a Cloud Agent to ACP-lite: mango@GrokBot's First Cross-Network Setup

> Date: 2026-10-19 (Asia/Shanghai)  
> Participants: Mango (`mango` / Mango@GrokBot) and Blueberry (`hermes-netbook` / Hermes@Netbook)  
> Scenario: A conversational bot on an Alibaba Cloud public VM joins a home multi-agent mailbox for the first time using ACP-lite 0.7.0 and Syncthing  
> Result: Both trust layers worked, and bidirectional delivery plus receipts completed end to end in about two hours.

---

## 0. Executive Summary

Mango runs on a public cloud host; Blueberry runs on a home network. Mango joined through a **two-layer trust** model in which **Syncthing moves files and ACP-lite signs and verifies envelopes**. The final state was `needFiles = 0`, `state = idle`, and `connected = True`, with messages and receipts delivered in both directions.

The unusual part was not the public address but the agent's execution model: Mango is a conversational bot with no CLI. It can read and write the shared mailbox, send and receive messages, and process tasks, but unlike Codex or DSH it cannot be woken automatically over SSH. A person must still relay the request through the bot on the other side. **This is a boundary of the execution model, not a missing configuration item.**

When onboarding other cloud agents such as WorkBuddy or Muse, this two-layer trust model, directory isolation, sync scanning, and troubleshooting process can be reused. Their programmatic wake-up support must be verified separately.

---

## 1. Why This Case Is Worth Recording

- The existing three machines were all on local networks. This was the first time an agent on a public cloud VM joined the group.
- It validated both machine-level Syncthing device trust and identity-level ACP fingerprint trust.
- It exposed real-world limits involving stale directories, missing rescans, stalled `.tmp` files, and the lack of CLI wake-up.
- Mango and Blueberry supplied independent accounts. Combining them gives a more complete picture than either one alone.

---

## 2. Architecture: Two Trust Layers, Both Required

| Layer | Responsibility | Basis for trust | Failure symptom |
|---|---|---|---|
| Syncthing | Sync files under `acp-shared/` | Exchange Device IDs and approve the folder | Files do not arrive, `needFiles > 0`, or the connection drops |
| ACP-lite | Create, sign, and verify envelopes | Trust the agent's short fingerprint with `trust` | Files arrive, but messages are untrusted or cannot be exchanged |

A Syncthing Device ID is a **machine identity**; an ACP fingerprint is an **agent identity**. Device trust only means that the hosts can sync files. ACP `trust` establishes which agent sent a particular envelope. Neither layer can replace the other.

---

## 3. Environment and Key Identifiers

| Item | Blueberry (netbook) | Mango (GrokBot VM) |
|---|---|---|
| Network location | Home network | Alibaba Cloud public network, `8.141.x.x` |
| ACP home | `~/acp-home-hermes` | `/home/box/acp-home` |
| Shared root | `~/acp-shared` | `/home/box/acp-shared` |
| Syncthing folders | `acp-shared` + `shared-files` | `acp-shared` only |
| CLI / SSH wake-up | Available | Not available |
| Connection path | --- | `relay-client` (public relay) |

Mango Device ID: `KLTAVRZ-XXXXXXX-XXXXXXX-XXXXXXX-XXXXXXX-XXXXXXX-XXXXXXX-XXXXXXX`  
Blueberry Device ID: `QDLJ6NK-XXXXXXX-XXXXXXX-XXXXXXX-XXXXXXX-XXXXXXX-XXXXXXX-XXXXXXX`

| Trusted ACP identity | Short fingerprint |
|---|---|
| Mango (`mango`) | `eokv-xxxx-xxxx-xxxx` |
| Blueberry (`hermes-netbook` / `hermes`) | `we5t-xxxx-xxxx-xxxx` |
| Cake (`openclaw`) | `xv2w-xxxx-xxxx-xxxx` |

### Directory isolation is the most important difference

Blueberry has two synced folders; Mango has only `acp-shared`, not `shared-files`. Mango can therefore read material in `acp-shared/docs/`, but cannot see internal documents in `shared-files/01-ACP-lite-文档/`. This is deliberate, not an oversight. A public cloud agent may exchange messages and read name cards, but it cannot read internal production documents, reach the home network, or be woken over SSH. Do not share `shared-files` with Mango without an explicit new authorization decision.

---

## 4. Onboarding Steps

### 4.1 Install the ACP-lite identity first

Mango cloned the repository, created a virtual environment, installed dependencies, and got `47 passed` from the self-test. With the home and root fixed, it initialized the agent identity:

```bash
cd /workspace/acp-lite
.venv/bin/python acp.py --home /home/box/acp-home --root /home/box/acp-shared init \
  --agent mango --display-name "Mango@GrokBot"
```

This created `peers/mango.json` (about 506 bytes) on the shared side; Blueberry later confirmed that the name card was readable. Pass both `--home` and `--root` to every later command so no command falls back to a host-local default.

### 4.2 Install and start Syncthing

The `apt` package did not install successfully, so Mango switched to the GitHub Release binary, **v2.1.6**:

- Binary: `/home/box/syncthing/syncthing`; config directory: `/home/box/acp-home/syncthing`; local GUI / REST endpoint: `http://127.0.0.1:8384`

```bash
/home/box/syncthing/syncthing serve --home=/home/box/acp-home/syncthing \
  --no-browser --no-upgrade
```

The API key is stored only as `<apikey>` in `config.xml`; this document never records the real value. Use a temporary environment variable when testing the REST API:

```bash
export SYNCTHING_API_KEY='<SYNCTHING_API_KEY>'
curl -s -H "X-API-Key: $SYNCTHING_API_KEY" 'http://127.0.0.1:8384/rest/db/status?folder=acp-shared'
```

Never put a real key in documentation, command history, or chat logs.

### 4.3 Create the shared folder and add both devices

The folder ID is `acp-shared`, and its local path is `/home/box/acp-shared`. The standard layout contains `outbox/`, `peers/`, `state/`, `docs/`, `broadcast/`, `skills/`, `scripts/`, `wiki/`, `archive/`, `shared/`, `.stfolder`, `.stignore`, and `00-目录说明.md`.

`outbox/`, `peers/`, `state/`, `.stfolder`, and `.stignore` are protocol directories and must not be moved arbitrarily. Mango added Blueberry's Device ID; Blueberry added Mango's; each approved the other on the shared folder. They eventually connected through a relay, and the status showed `relay-client` rather than a direct LAN link.

### 4.4 Establish ACP fingerprint trust after device trust

A configured device does not mean the agents already trust one another. Each side checked the other's name card out of band and ran ACP `trust`. Mango recorded Blueberry and its alias, plus the agreed Cake fingerprint, in `trusted.json` under the ACP home.

Fingerprints must be verified through an out-of-band channel. Do not treat Syncthing connectivity, or "the file is reachable", as proof that the message identity is trusted.

---

## 5. Timeline

| Time | Event |
|---|---|
| 11:49:11 | `peers/mango.json` reached Blueberry; Mango's name card became readable (506 bytes) |
| 11:51-11:55 | Blueberry's first attempt to edit `config.xml` failed; adding the device through the REST API succeeded |
| 11:57-12:02 | Mango created a pending device request, Blueberry approved it, and `acp-shared` began syncing |
| 12:02-12:25 | First pull brought in about 800+ files; after removing stale `__pycache__`, errors and needed files reached zero |
| 12:11-12:29 | Mango sent two hello broadcasts; Blueberry did not see them at first, then they appeared under `outbox/mango/` |
| 12:33:04 | Blueberry sent a welcome message: `hermes-netbook-20261019-123304-f131` |
| 12:38:27 | Mango replied and confirmed the `#agree` convention: `mango-20261019-123827-6961` |
| 12:40-12:41 | Blueberry asked how Mango was woken; Mango explained that it had no CLI: `124008-8f74` / `124105-e049` |
| 12:45:30 | Mango sent a connectivity test: `mango-20261019-124530-ed44` |
| 12:45:43 | Mango corrected it 13 seconds later to "find the newest envelope": `mango-20261019-124543-25d7` |
| 12:48:58 | Blueberry reported the test result: `hermes-netbook-20261019-124858-6dbc` |
| 12:55:11 | Mango confirmed with a receipt: `mango-20261019-125511-ec25`; the loop closed in both directions |
| 13:01:15 | The netbook was patched and rebooted; Mango's connection then had to be restored manually |
| 13:18-13:21 | Mango broadcast an update and wrote a 11,284-byte onboarding record, visible after sync on Blueberry |

---

## 6. Four Real Mistakes on Blueberry

| Mistake | What happened | Correct approach |
|---|---|---|
| Editing config to add a device | Added a `<device>` entry to a running `config.xml`; Syncthing overwrote the file, so it had no effect | Use REST API `POST /rest/config/devices` and confirm the device is in the active runtime config |
| Concluding Mango had not sent the messages | Outbound records did not appear, so Blueberry assumed Mango had not written them; Mango had written them, but sync and indexing were incomplete | Check `rest/db/completion`, `needFiles`, and the actual outbox before deciding which side is at fault |
| Not rescanning after sending | The welcome message was written, but local Syncthing did not scan it promptly, so it never entered the global index and Mango did not receive it | Run the rescan command below after every send and make that step part of the routine |
| Forgetting to reconnect Mango after reboot | After the netbook rebooted, `mango connected=False` and no system prompt appeared | Pause and resume Mango's device to force a reconnect; this time relay connectivity returned after about 90 seconds, and the check should be added to the runbook |

```bash
curl -s -X POST -H "X-API-Key: $SYNCTHING_API_KEY" \
  'http://127.0.0.1:8384/rest/db/scan?folder=acp-shared'
```

---

## 7. Other Important Failures

- `acp-lite-v0.5.1` and `acp-lite-v0.6.2` could not be deleted cleanly on Blueberry. The remote copies were gone, but local `__pycache__` directories remained because `.stignore` excluded them. This caused `Failed to sync 2 items` and retries every 60 seconds; removing the stale directories fixed it.
- One message remained at `progress` in `rest/db/need`, with only a partial `.syncthing.hermes-netbook-20261019-124858-6dbc.json.tmp` file locally. Rescanning, pausing and resuming, and deleting the `.tmp` file did not fully fix it. A clean restart after killing extra Syncthing processes brought the real file in after about one to two minutes.
- When the peer could see the final file but the local host's `need` count was still 1, the final filename on the local host was the source of truth. A `.tmp` file must never be read as the message body; after the restart and catch-up, `need` went to 0.
- Mango once pointed `--reply-to` at its own message, which failed. The option may target only the **peer's** `msg_id`. A shell `for` loop also produced syntax errors around redirects; the loop structure had to be fixed before it would run.
- The first Syncthing launch showed an anonymous usage-statistics prompt. It was disabled in the UI, with the user making that choice.

---

## 8. Closed-Loop Verification and Final State

Mango asked Blueberry to find the **newest envelope** in `outbox/`, not an arbitrary file. Blueberry found the corrected message at `outbox/mango/mango-20261019-124543-25d7.json` and confirmed that `peers/mango.json` was readable.

Blueberry noted that `ed44` and `25d7` were only 13 seconds apart. Both arrived, and `25d7` corrected the wording of `ed44`; it was not a missing resend. Blueberry also suggested adding `reply=ack` or using the `task` type for future work so `watch` could identify it automatically.

Mango sent receipt `mango-20261019-125511-ec25` with `--reply-to hermes-netbook-20261019-124858-6dbc --reply none --code ok`, then ran `ack` to clear the pending item. The final health state was:

- `needFiles = 0`
- `state = idle` (or briefly `syncing` before returning to `idle`)
- `connected = True` with Blueberry, usually over `relay-client`

This confirms that both file sync from the public VM to the home network and ACP signed-envelope exchange closed successfully.

---

## 9. Checklist for the Next Cloud Agent

1. Define the sharing boundary first. Expose only `acp-shared` by default; do not expose internal `shared-files`.
2. Document the network boundary, CLI and SSH availability, and who can initiate wake-up before choosing a task-delivery method.
3. Initialize the ACP identity, always pass `--home` and `--root`, and confirm that the name card synced to the peer.
4. Install and start Syncthing, create `acp-shared`, exchange Device IDs, and approve the folder on both sides.
5. Manage a running Syncthing instance through its REST API; do not edit `config.xml` directly.
6. Verify ACP fingerprints out of band and run `trust`; device connectivity is not agent identity verification.
7. Judge health from `needFiles`, `rest/db/need`, `rest/db/completion`, and the presence of the final filename together.
8. Rescan after every send. Never treat a `.tmp` file as the message body; when stuck, clean up stale files and restart with one instance.
9. Use a falsifiable task such as "find the newest envelope" for an end-to-end test, and require an explicit receipt and `ack`.
10. If the target agent has no CLI, define it as a "human-triggered, automatically processed" collaboration node and do not promise fully automatic wake-up.

---

## 10. Open Decisions and Final Lessons

| Item | Status | Notes |
|---|---|---|
| Mango's hot/cold folder load-reduction proposal | No response yet | A proposal has been made; internal confirmation of `#agree` is pending |
| Whether Mango will keep an automated mailbox-watching routine | Undecided | Requires a decision from the user |
| Whether to share `shared-files` with Mango | Undecided | Contains internal documents; recommendation is to keep it unshared |
| Connection self-check after the netbook reboots | Recommended | Detection still depends on a person noticing `connected=False` |

Onboarding a public cloud agent with two-layer trust is not especially complex. The dangerous part is assuming that something is done: a device entry does not mean the peer is online, a written file does not mean it was rescanned, a `.tmp` file does not mean the body has landed, and message delivery does not mean the agent can be woken programmatically. Treat every "looks complete" state as a claim to verify using names, IDs, REST status, and actual send/receive results. That is what makes onboarding a real closed loop.

---

*Sources: Mango's account (`mango-record.md`) and Blueberry's timeline (`mango-blueberry-side.md`). The two accounts complement each other. Apart from the source-file line count in the task description (the file actually has 170 physical lines), no substantive factual conflicts were found.*
