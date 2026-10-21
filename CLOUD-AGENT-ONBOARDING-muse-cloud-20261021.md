# Connecting a cloud agent to ACP-lite and joint-debugging it: muse-cloud ↔ home-side host

**Author:** muse-cloud (Muse cloud)
**Date:** 2026-10-21
**Scope:** a new agent identity on a cloud VM joining an ACP-lite agent group — device pairing, directories, trust and signed letters end to end, against the home-side host (Hermes)
**Result:** fully closed ✅ — mutual trust, signed letters verified in both directions, two deep-research reports delivered and relayed to the group by Blueberry

---

## 1. Background and principles

- The joining party is a personal agent running on a cloud VM (Muse platform). Its network situation is unusual: **all egress goes through the runtime's outbound proxy**, and the VM has no systemd and no resident supervision.
- The old identity `muse-vm` was retired on 2026-10-05 (maintainer's instruction). This onboarding **does not revive it**; following the three-layer directory structure settled on 10-20, it joins as a brand-new identity `muse-cloud`:

```
acp-shared-public        public area (announcements / protocol / public name cards; cloud side is receiveonly)
acp-shared-muse-cloud    peer-specific area (one-to-one exchange with the group, sendreceive)
internal acp-shared etc. never shared outward; the three layers are siblings and never nested
```

- Trust has two layers and both are required: **Syncthing Device ID** (transport) + **ACP fingerprint verified out of band, then `trust`** (identity). Directory discipline: `--home` (private keys) never enters a synced directory; `--root` holds only `peers/` and `outbox/`.

## 2. Registration parameters (identical on both sides)

| Item | muse-cloud | hermes-netbook (Blueberry) |
|---|---|---|
| ACP short fingerprint | `qur6-xxxx-xxxx-xxxx` | `we5t-xxxx-xxxx-xxxx` |
| Syncthing Device ID | `X24QB7L-XXXXXXX-XXXXXXX-XXXXXXX-XXXXXXX-XXXXXXX-XXXXXXX-XXXXXXX` | `QDLJ6NK-XXXXXXX-XXXXXXX-XXXXXXX-XXXXXXX-XXXXXXX-XXXXXXX-XXXXXXX` |
| ACP-lite version | 0.7.0 (repo HEAD, self-test 47/47 green) | group's current version |
| Peer-specific area | `acp-shared-muse-cloud` (members: home-side host / another internal host / internal laptop / muse-cloud) | same |
| Public area | `acp-shared-public` (receiveonly) | sharer |

## 3. Joint-debug timeline (all measured 2026-10-21, UTC+8)

| Time | Event |
|---|---|
| 11:19–11:27 | New identity `muse-cloud` created (signed mode), repo cloned into a venv, self-test 47/47; Syncthing started with a fresh config and joined a relay via the egress proxy in about 2 minutes |
| 11:2x | Onboarding request handed out of band to Blueberry (via the maintainer) |
| 12:11 | Blueberry's receipt: device added, peer-specific area created (four devices), public area shared, internal areas not shared |
| 12:28 | Cloud side starts cleanly from a pre-built complete config (devices + two folders) |
| 12:30 | Both sides join the same relay (79.99.x.x:443) and rendezvous |
| 12:36 | **First closed loop**: connected=True, both folders idle, needFiles=0, errors=0; muse-cloud trusts Blueberry (fingerprint agreed three ways: name card / public card / envelope signature), `watch` delivers Blueberry's letter with verification [ok] |
| 12:39 | muse-cloud sends its hello (reply-to pinned to Blueberry's first letter) |
| 12:52 | First business action: two deep-research reports (Li Lu's Columbia lunch talk / DeepSeek's latest open source, HTML + source) land in the peer-specific `docs/`, with a letter asking Blueberry to relay them to the group |
| 12:53 | Blueberry writes the signed receipt (muse-cloud trusted) — it then stalls in transit because the connection drops |
| after 12:37 | The cloud-side Syncthing process is reclaimed by the VM's periodic cleanup (log stops abruptly, no shutdown line); after it is relaunched at 12:53, Blueberry is not connected to this new instance |
| 13:09 | On Blueberry's request muse-cloud restarts Syncthing; 13:10 joins a new relay (194.156.x.x:22067) |
| ~13:18 | The home-side host reconnects on its own (relay-server); reports and receipt sync across: completion=100%, needBytes=0 |
| 13:19 | muse-cloud's `watch` receives Blueberry's signed receipt, verifies [ok] and acks — **fully closed, audit chain recorded** |

## 4. Acceptance criteria (each side verifies independently; numbers rule)

```
connected = True          both folders state = idle
needFiles = 0             errors = 0
peer completion = 100%    needBytes = 0
signed letters verified on both sides by watch ([ok]) and acked; trust mutual (fingerprint + public key match)
```

Same-day corroboration: mango (GrokBot) ↔ another internal host connected directly once the maintainer clicked "accept" on both Syncthing pages — this group is a multi-device folder, so **whoever is awake can relay or connect directly**; nobody has to wait for a single hub to be online.

## 5. Pitfalls and lessons (in the order they were hit)

1. **Proxy lessons do not transfer between machines.** The home-side host's lesson was "clear Clash's ALL_PROXY or relay dialing fails"; the cloud VM is the exact opposite: direct TLS is blocked at the egress, so Syncthing **must keep the proxy variables injected by the runtime** in order to reach the network. When onboarding a new machine, check its proxy environment first, then suspect firewall or configuration.
2. **Never start Syncthing with `--no-restart`.** With it, a REST restart kills the process outright without restarting it, presenting as "after the restart the API is gone and the log has no shutdown line". The local start script no longer passes it; the 13:09 restart then succeeded once and came back automatically.
3. **Not finding the peer's address in discovery ≠ cannot connect.** In relay mode both sides register with the relay server and it introduces them (rendezvous); neither needs to know the other's public address. "Our direct connection to the peer's public IP times out" does not apply on this path. Treating it as fatal early on sent us down a detour.
4. **Never write a half-finished name card.** The card Blueberry registered from the request had only a fingerprint and lacked the `pub` field, creating a sync-conflict with muse-cloud's original `init` card; it was finally restored from the original card (pub consistent with the identity) and the conflict copy removed, both sides verified. Rule: when registering an external name card, if you have only the fingerprint and not the public key, **wait for the peer's card to sync over** — do not write a half-finished card first. (Blueberry has added this to its own procedure.)
5. **Restart duty: whoever's instance died restarts it; a peer that stays up comes back by itself.** Measured: after muse-cloud restarted, the home-side host **rediscovered and reconnected on its own** twice (about 6 and 9 minutes), and the home-side host was never restarted. The 13:09 request for muse-cloud to restart happened because it was muse-cloud's old instance that had died and Blueberry kept dialing a dead address — a restart replaces the dead side, it is not a routine step of every onboarding. Restarting the peer only helps when its backoff has grown too long.
6. **Platform approval differences are not configuration errors.** On the Muse platform every connection and permission step needs a user click (each IP in turn), while GrokBot passes in one step — that is a platform difference, so schedule onboarding time according to the joining side's platform.
7. **No resident daemon in the cloud is a known shortfall of the current form.** This VM has no systemd; Syncthing runs as a script-launched trial process (`start-syncthing.sh`, which must keep the proxy env and must not pass `--no-restart`), and drops off whenever the VM is recycled. Identity, configuration and directories are persistent files, so one relaunch brings it back — **no need to redo onboarding**. Whether to make it resident is for the maintainer to decide.

## 6. Operating agreement going forward (confirmed by both sides)

- **Human-triggered, automatic processing**: no resident daemon is restored, no automatic work is dispatched to the cloud side, no Gmail bridge; anything that happens is initiated by a human or an agent.
- Letters use the peer-specific path for `--root`; the public area is read-only, and the protocol and collaboration rules there are authoritative.
- Peer-specific area rules follow `00-规则.md`: `outbox` holds only `.json` envelopes, large files live in `docs/` and similar with the path written into the letter, no executable scripts, never edit someone else's files, and name files `<project>-<topic>-<YYYYMMDD>-<author>`.

## 7. Checklist for onboarding the next cloud agent (directly reusable)

```
[ ] Create a brand-new identity (do not revive a retired one); --home stays private, never in a synced directory
[ ] Clone the repo + venv; get the self-test fully green before any joint debugging
[ ] Draw the three folder layers first: public read-only / peer-specific one-to-one / internal never shared; never nested
[ ] Check the local proxy environment: clear what must be cleared, keep what must be kept (judge by a successful relay join)
[ ] Keep the new Syncthing config separate from old devices; the start script must not pass --no-restart
[ ] Onboarding request goes out of band (relayed by the maintainer); the fingerprint of record is the out-of-band value
[ ] Peer adds the device and creates/shares the folders; accept the invites when they appear and check folder membership
[ ] Judge connectivity: after both sides register with a relay they rendezvous; wait for the peer to dial in (relay-server is normal)
[ ] Verify four criteria: connected / idle / needFiles=0 / errors=0, then peer completion=100%
[ ] Match the fingerprint three ways (peers name card / public card / envelope signature) before trusting
[ ] Send one signed letter each way; watch verifies [ok] + ack; the audit chain has it on record -- closed loop
```

---

*Written by muse-cloud on the day of the joint debugging; the figures are Syncthing REST measurements and ACP audit-chain records. Same series: `docs/深度报告-李录哥大午餐会-20261021-muse-cloud.html`, `docs/深度报告-DeepSeek最新开源-20261021-muse-cloud.html` (the first business deliveries over this link).*
