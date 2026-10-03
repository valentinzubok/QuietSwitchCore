# QuietSwitch v2 — Studio Dev (chain 61997) deploy record

| | |
|---|---|
| **Network** | GenLayer Studio Dev / Studio Next — chain `61997`, GenVM `v0.3.0` |
| **Contract** | [`0x7ACfde1Bb69023B903d599495719ad6736e5f21e`](https://explorer-studio-dev.genlayer.com/address/0x7ACfde1Bb69023B903d599495719ad6736e5f21e) |
| **Source** | [`contracts/QuietSwitch.py`](contracts/QuietSwitch.py) — runner `py-genlayer:5jycge4q8k23462jtb0b9fyey1s9qz928sz2nbrd9mg4sxqg2qng` |
| **Source sha256** | `d060459e139c134b6ab0c6b4e4bffb2a0c327de7765ed367e6be75210c512570` |
| **Console** | https://valentinzubok.github.io/QuietSwitch/ · [QuietSwitch](https://github.com/valentinzubok/QuietSwitch) |
| **Holder / owner** | `0xBA989D240AAB780d3d2eD2201f5F677098901408` (test account) |
| **Successor in the demo** | `0x94E6105336fD2d3Eb3E1c1a4f39e5e1d52d8B2D3` |

## Verify that the deployed code equals this source

```bash
curl -s -X POST https://studio-dev.genlayer.com/api -H 'content-type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"gen_getContractCode","params":["0x7ACfde1Bb69023B903d599495719ad6736e5f21e"]}' \
  | python3 -c "import sys,json,base64,hashlib; print(hashlib.sha256(base64.b64decode(json.load(sys.stdin)['result'])).hexdigest())"
shasum -a 256 contracts/QuietSwitch.py
# both print d060459e139c134b6ab0c6b4e4bffb2a0c327de7765ed367e6be75210c512570
```

`scripts/verify_deployment.py` does the same check and runs in CI.

The v1 deploy `0x9643Cc2F…` is superseded. Its miss counter had no cadence: one caller could
satisfy the threshold by calling `check()` repeatedly against the same outage or the same stale
page. See "What changed in v2" below.

## Observation windows (v2)

Each switch carries an `observation_interval`, fixed when it was armed. The transaction datetime —
which GenVM pins per transaction, so every validator re-executing sees the same value — is divided
into windows of that length, and the switch stores the last window it observed. A `check()` whose
window has already been observed **reverts before the page is fetched and before any model runs**.

Consequences, all enforced by the contract rather than by convention:

- one window yields at most one counted observation, so the same outage or the same stale page
  cannot be replayed into extra misses;
- reaching `misses_required` needs that many distinct, separated observation periods;
- a transient outage needs **two** windows before it costs anything at all: the first unreachable
  observation is recorded as `outage_noted` without counting, and a page that comes back clears it;
- `get_cadence(switch_id)` is a free view that tells an app whether a window is open and when the
  next one starts, so nobody pays a fee for a call that is going to revert.

## On-chain lifecycle

Both heartbeat pages are files in the console repository, so every check-in and every silence is a
public commit: [`web/public/fixtures/`](https://github.com/valentinzubok/QuietSwitch/tree/main/web/public/fixtures).

| # | Step | Result | Tx |
|---|------|--------|----|
| 0 | deploy (v2) | contract created | `0xb4303632028a35c84bba07697f5ca6068fbb1264ec7d3c82fa73cd36aec3282d` |
| 1 | `arm("keys/demo", fixtures/stale.html, "check-in dated no earlier than September 2026", successor, note, misses_required=2, observation_interval=300)` | armed; page, rule, successor, threshold **and cadence** fixed on chain. `get_cadence` reports `observation_interval 300`, `open_now true`. | `0x543f4523c86463dcce5e3fde0f5fc52ba9a1369aac8eef3673790266ce4e0172` |
| 2 | `check("keys/demo")` | **missed (1 of 2)** in window `5970051` — the page returns 200 and looks maintained, but its only check-in is dated 2019, so the validators agreed it is not proof of life. | `0x21470b4ea410a319777f62bc7ff5ac5b4d74203dfeb1ded5ef44d6fd76ff1d6a` |
| 3 | `check("keys/demo")` again, immediately | **reverted** — `"this observation window has already been checked; the next one opens at 1791015600 (interval 300s)"`. The page was never fetched and no model ran, so the same stale observation could not be replayed into a second miss. | `0x460217b63a8f86e841295f056d4a61180f6009279269eb08540fc23e90990b9c` (ERROR) |
| 4 | `check("keys/demo")` once the next window opened | **fired** in window `5970052` — a second, separated observation reached the threshold of 2, and the switch handed over: `holder` became the successor and the note is theirs. | `0x0f93a8aa3b3078fccac33fa185f0afe2226aa925c6b48c6eff70d5b0ccea3768` |

State (`get_stats`): `{"switches":1,"armed":0,"fired":1,"disarmed":0,"pending_misses":0,"checks":2}` —
three `check` transactions, only **two** counted observations, in two different windows.

Steps 2–4 are the whole point of v2: the firing took two observations that the contract itself
forced apart, and the attempt in between was refused by the contract rather than by politeness.

The interval is 300 s here so the flow is reproducible in minutes; a real switch would use hours or
days (the console defaults to 86 400 s, and the contract accepts 60 s – 30 days).

### A note on the page renderer's cache

Studio Dev's page renderer serves a cached copy of a URL for several minutes. Right after the commit
that removed the check-in, two `check` calls still saw the old text — the captured `total_chars` in
the transaction's equivalence output still contained "28 September 2026" — and therefore answered
**alive**, correctly, for the text they were given. The third call, once the cache had expired, saw
the migrated page and recorded the miss. Anyone reproducing the "holder goes quiet" flow should
allow for that delay; the contract judges whatever text the validators actually agreed on, which is
exactly the property that makes the verdict auditable.

## What changed in v2

| Steward request | Change |
|---|---|
| One caller must not satisfy the miss threshold through immediate repeated checks of the same outage or stale observation | `arm()` takes a required `observation_interval`; `check()` computes `window = tx_datetime // interval` and reverts when `window <= last_window`, **before** fetching the page or spending a model. Proven on chain by tx `0x460217b6…`. |
| Each counted miss must represent a distinct, enforceably separated observation period or other non-replayable event | The window id *is* the uniqueness state, and it lives in contract storage (`last_window`, `last_counted_window`, `last_check_at`). `misses_required` misses therefore need that many separated windows; each `Missed` / `Fired` event records its window and timestamp, and a repeat of identical page text is flagged `unchanged_page`. |
| An unreachable page currently counts toward irreversible handover | It no longer does on its own. The first unreachable observation is `outage_noted`: recorded, not counted. Only an outage that persists into a **different** window counts, and a page that comes back clears `outage_pending`. A transient blip can cost nothing, however many times it is polled. |
| Include the cadence or uniqueness state in the contract | Stored per switch (`observation_interval`, `armed_at`, `last_check_at`, `last_window`, `last_counted_window`, `outage_pending`) and exposed by the free `get_cadence(switch_id)` view, so an app can tell whether a window is open before paying a fee. |
| Matching submitted and deployed source | Redeployed at `0x7ACfde1Bb69023B903d599495719ad6736e5f21e`; on-chain sha256 == `contracts/QuietSwitch.py` == `d060459e…`, re-checked by `scripts/verify_deployment.py` in CI. |
| Tests | `tests/test_adversarial.py` adds: a second check in the same window reverts and fetches nothing; firing needs as many separated windows as `misses_required`; one second short of a window is not a window; a transient outage hammered by three different callers cannot fire a 1-miss switch and leaves no trace once the page returns; a stale page counts once per window and the events prove two distinct windows; `rearm` clears a pending outage. 40 tests. |

The clock is the transaction datetime, which GenVM pins per transaction, so every validator
re-executing a `check` computes the same window. The test double wires `datetime.now()` to a
controllable value for exactly that reason, so the windows are tested without sleeping.

## What the validators are actually asked

One boolean, from a bounded deterministic digest of the whole document:

- the leader returns `{"verdict": "alive" | "silent" | "invalid"}`, and `prompt_comparative` (with a
  **positional** principle — it is positional-only in GenVM v0.3) requires the field to be identical
  across validators;
- `literal_bool()` accepts only JSON `true`/`false`, so `"false"`, `0`, `"no"`, `[]` and `{}` all
  produce `invalid` and revert the transaction — recording **no miss**;
- the rule and the page text are fenced as untrusted data, inner fences neutralized, and injection
  phrasing is flagged to the model and stored on the switch;
- there is **no fallback** to another consensus strategy. Firing takes something away from the
  current holder, so a pipeline problem must never be able to look like silence.
