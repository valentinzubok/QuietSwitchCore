# QuietSwitch v3 — Studio Dev (chain 61997) deploy record

| | |
|---|---|
| **Network** | GenLayer Studio Dev / Studio Next — chain `61997`, GenVM `v0.3.0` |
| **Contract** | [`0x32732ab3C6F1a5cA92d9ab96746F1D17b6B95F7F`](https://explorer-studio-dev.genlayer.com/address/0x32732ab3C6F1a5cA92d9ab96746F1D17b6B95F7F) |
| **Source** | [`contracts/QuietSwitch.py`](contracts/QuietSwitch.py) — runner `py-genlayer:5jycge4q8k23462jtb0b9fyey1s9qz928sz2nbrd9mg4sxqg2qng` |
| **Source sha256** | `2d1e35bc81eaf90d8152361c0a543971cbcd5eb98c5d477a8baa7983535f4075` |
| **Console** | https://valentinzubok.github.io/QuietSwitch/ · [QuietSwitch](https://github.com/valentinzubok/QuietSwitch) |
| **Deployer** | `0x4130dC892bD57009Ba795d746354072465b84412` — a separate test account, used below to show it has no power |
| **Holder in the demo** | `0xBA989D240AAB780d3d2eD2201f5F677098901408` (test account) |
| **Successor in the demo** | `0x94E6105336fD2d3Eb3E1c1a4f39e5e1d52d8B2D3` |
| **Owner / admin** | none — the contract has no privileged address; `get_admin()` returns `""` |

Superseded: v2 `0x7ACfde1B…` (calendar windows, owner override) and v1.

## Verify that the deployed code equals this source

```bash
curl -s -X POST https://studio-dev.genlayer.com/api -H 'content-type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"gen_getContractCode","params":["0x32732ab3C6F1a5cA92d9ab96746F1D17b6B95F7F"]}' \
  | python3 -c "import sys,json,base64,hashlib; print(hashlib.sha256(base64.b64decode(json.load(sys.stdin)['result'])).hexdigest())"
shasum -a 256 contracts/QuietSwitch.py
# both print 2d1e35bc81eaf90d8152361c0a543971cbcd5eb98c5d477a8baa7983535f4075
```

`scripts/verify_deployment.py` does the same check and runs in CI.

## The two guarantees of v3

**The handover cannot be accelerated.** Each switch stores `observation_interval` (fixed at
`arm()`) and `cadence_anchor`: the transaction datetime of the last accepted check, or of
arm/rearm. `check()` reverts unless `now >= cadence_anchor + observation_interval`, and it does so
before the page is fetched and before any model runs. The separation is elapsed time between
accepted checks. v2 used calendar windows (`now // interval`), which let a call at the end of one
window and a call at the start of the next count two seconds apart; in v3 there is no boundary to
straddle. The anchor starts at arm time, so firing takes at least
`misses_required × observation_interval` from arming.

**The handover cannot be suppressed.** v2 let the contract owner disarm or rearm any switch. v3 has
no owner at all: no `owner` field, no constructor argument, no `transfer_ownership`. `disarm` and
`rearm` accept exactly one caller, the current `holder` of that switch.

`get_cadence(switch_id)` is a free view (`open_now`, `next_check_at`, `seconds_until_open`), so
nobody pays a fee for a call that is going to revert.

## On-chain lifecycle

The heartbeat page is a file in the console repository:
[`web/public/fixtures/stale.html`](https://github.com/valentinzubok/QuietSwitch/blob/main/web/public/fixtures/stale.html) — up, maintained-looking, last
check-in dated 2019.

| # | Caller | Step | Result | Tx |
|---|--------|------|--------|----|
| 0 | deployer | deploy (v3, no constructor arguments) | contract created | `0xb0752418e46e2ce72202820814cf9dc24f8885db8255ad19d49ce4b838d150b5` |
| 1 | holder | `arm("keys/demo", fixtures/stale.html, "check-in dated no earlier than September 2026", successor, note, misses_required=2, observation_interval=180)` | armed at `1791099906`; `cadence_anchor` = arm time | `0x3f229f129aa0c1a83783f79de50346b623c4e4dcbf991e41537acb83eeeb4ef4` |
| 2 | holder | `check("keys/demo")` immediately | **reverted** — `the observation interval has not elapsed; the next check is accepted at 1791100086 (interval 180s)`. Even the first observation waits a full interval. | `0x9423de16326e96b07994ff09ac44af517de4395f88fc05d94399bdaad8adba4e` (ERROR) |
| 3 | **deployer** | `disarm("keys/demo")` | **reverted** — `only the current holder of this switch may do that`. The deployer cannot suppress the handover. | `0x0b56f86641bd2386b1efacd09716b46e3aa6bac20b69208050e80fadfa9d6efb` (ERROR) |
| 4 | holder | `check("keys/demo")` once the interval had elapsed | **missed (1 of 2)** at `1791100101`, 195 s after arming; observation 1. `cadence_anchor` moves to this transaction's time. | `0xc7e5cd3b556294e93c4ca1c977cd4ade54a3f6c5c38bef6469a7e12c4bf452d6` |
| 5 | holder | `check("keys/demo")` again, immediately | **reverted** — `…the next check is accepted at 1791100281 (interval 180s)`: exactly 180 s after step 4, not at the next multiple of 180. Nothing fetched, no model run. | `0x212a0fee5ee5bdae7f34b0b7965707829f943b986179960db1ba5f6019727fd9` (ERROR) |
| 6 | **deployer** | `rearm("keys/demo")` | **reverted** — `only the current holder of this switch may do that`. The deployer cannot wipe the miss or restart the clock. | `0xce34d46f5ed43fd9ec0ace02fca87387daf7849cc4f5346d4d16fbe6983565bd` (ERROR) |
| 7 | holder | `check("keys/demo")` once the interval had elapsed again | **fired** at `1791100291`, 190 s after step 4; observation 2. `holder` became the successor. | `0xab1a6855e695aa11e4113658404c5d6f961f32477653a5d6ca73799bff669748` |

State (`get_stats`): `{"switches":1,"armed":0,"fired":1,"disarmed":0,"pending_misses":0,"checks":2}`.
Seven calls after the deploy, two accepted observations 190 s apart with a 180 s interval, and four
refusals made by the contract itself: two early checks and two attempts by the deployer.

`get_events` on chain:

```json
[{"kind":"Armed","id":"keys/demo","misses_required":2,"observation_interval":180,"at":1791099906},
 {"kind":"Missed","id":"keys/demo","misses":1,"observation":1,"at":1791100101,"unchanged_page":false},
 {"kind":"Fired","id":"keys/demo","misses":2,"observation":2,"at":1791100291}]
```

(addresses, hashes and detail strings trimmed here; the view returns them in full.)

The interval is 180 s here so the flow is reproducible in minutes; a real switch would use hours or
days (the console defaults to 86 400 s, and the contract accepts 60 s – 30 days).

### A note on the page renderer's cache

Studio Dev's page renderer serves a cached copy of a URL for several minutes, so a `check` right
after a commit to a heartbeat page can legitimately see the previous text. The contract judges
whatever text the validators actually agreed on, which is the property that makes the verdict
auditable. The demo above uses a page that did not change during the run.

## What changed in v3

| Steward request | Change |
|---|---|
| Enforce at least the configured observation interval between accepted checks | `check()` reverts unless `now >= cadence_anchor + observation_interval`. `cadence_anchor` is written by every accepted check and by `arm`/`rearm`, so two accepted checks are always at least one interval apart and the first one waits a full interval after arming. Calendar windows are gone. |
| Remove the contract owner's ability to disarm or rearm switches held by other users | The owner is removed entirely: no `owner` storage, no constructor argument, no `transfer_ownership`, no `get_owner`. `_only_holder` compares the caller with the switch's `holder` and nothing else. Steps 3 and 6 above show the deploying account being refused on chain. |
| Tests for calls across an adjacent window boundary | `test_two_calls_straddling_a_window_boundary_are_still_one_observation` arms so the first check lands one second before an exact multiple of the interval, then calls at the boundary, one second after it and almost a full window later, from four accounts: all revert, no page is fetched, the miss count stays 1, and the handover fires exactly one interval after the accepted check. `test_every_pair_of_accepted_checks_is_at_least_one_interval_apart` hammers every 7 s across six boundaries. Also: the first check waits a full interval; a 3-miss daily switch cannot fire in under three days; rearm restarts the cadence. |
| Tests for owner interference | `test_the_deployer_cannot_disarm_or_rearm_a_switch_held_by_someone_else` (the miss and the cadence are untouched and the handover still fires), `test_the_deployer_cannot_rearm_a_switch_the_holder_disarmed`, `test_the_contract_exposes_no_owner_admin_or_ownership_transfer`, `test_only_the_holder_can_stand_down_their_own_switch`, `test_after_firing_the_previous_holder_and_the_deployer_have_no_say`. The tests deploy from one account and arm from another, so "the deployer" is a real, distinct caller. |
| Matching submitted and deployed source | Redeployed at `0x32732ab3C6F1a5cA92d9ab96746F1D17b6B95F7F`; on-chain sha256 == `contracts/QuietSwitch.py` == `2d1e35bc…`, re-checked by `scripts/verify_deployment.py` in CI. |

50 tests in total (`python3 -m pytest -q`). The clock is the transaction datetime, which GenVM pins
so every validator re-executing a `check` reads the same value; the test double wires
`datetime.now()` to a controllable number for the same reason, so the interval is tested without
sleeping.

Carried over from v2 and v1: the first unreachable observation is `outage_noted`, not counted;
`check()` takes no URL and no rule; the model answer must be a literal JSON boolean; page and rule
are quoted as untrusted data; and a malformed answer, a model error or a consensus failure reverts
without recording a miss.
