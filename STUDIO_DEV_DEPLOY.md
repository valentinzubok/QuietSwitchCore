# QuietSwitch — Studio Dev (chain 61997) deploy record

| | |
|---|---|
| **Network** | GenLayer Studio Dev / Studio Next — chain `61997`, GenVM `v0.3.0` |
| **Contract** | [`0x9643Cc2Fd2ae27E2cBa77f653BBc58bcDa296f51`](https://explorer-studio-dev.genlayer.com/address/0x9643Cc2Fd2ae27E2cBa77f653BBc58bcDa296f51) |
| **Source** | [`contracts/QuietSwitch.py`](contracts/QuietSwitch.py) — runner `py-genlayer:5jycge4q8k23462jtb0b9fyey1s9qz928sz2nbrd9mg4sxqg2qng` |
| **Source sha256** | `79830d6d63f22bf0d1e03610d347ba309a0579737841a4e161cda8f78b2fd2f9` |
| **Console** | https://valentinzubok.github.io/QuietSwitch/ · [QuietSwitch](https://github.com/valentinzubok/QuietSwitch) |
| **Holder / owner** | `0xBA989D240AAB780d3d2eD2201f5F677098901408` (test account) |
| **Successor in the demo** | `0x94E6105336fD2d3Eb3E1c1a4f39e5e1d52d8B2D3` |

## Verify that the deployed code equals this source

```bash
curl -s -X POST https://studio-dev.genlayer.com/api -H 'content-type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"gen_getContractCode","params":["0x9643Cc2Fd2ae27E2cBa77f653BBc58bcDa296f51"]}' \
  | python3 -c "import sys,json,base64,hashlib; print(hashlib.sha256(base64.b64decode(json.load(sys.stdin)['result'])).hexdigest())"
shasum -a 256 contracts/QuietSwitch.py
# both print 79830d6d63f22bf0d1e03610d347ba309a0579737841a4e161cda8f78b2fd2f9
```

`scripts/verify_deployment.py` does the same check and runs in CI.

## On-chain lifecycle

Both heartbeat pages are files in the console repository, so every check-in and every silence is a
public commit: [`web/public/fixtures/`](https://github.com/valentinzubok/QuietSwitch/tree/main/web/public/fixtures).

| # | Step | Result | Tx |
|---|------|--------|----|
| 0 | deploy | contract created | `0xce5b5724f1a8ba874a7c69e8112e229d8969586fd796201be1f97562508363d8` |
| 1 | `arm("keys/primary", fixtures/heartbeat.html, "check-in dated no earlier than September 2026", successor, note, 2)` | armed; page, rule, successor and threshold fixed on chain | `0x3b377176cc628e3f748b63d3defcf4b14a67e38db9c0f596f1a8c97a11e169d6` |
| 2 | `check("keys/primary")` | **alive** — the validators agreed the page states a check-in that satisfies the rule; miss counter stays 0 | `0xb366bdede4e66677512e1448fbae97fca7efb31ce6cdd3ab844bafa6a44347bd` |
| 3 | `arm("keys/archived", fixtures/stale.html, same rule, successor, note, 1)` | armed | `0xfb22db9935fdb17122466d003f10179e395983878de138dd07b59f051166c6dc` |
| 4 | `check("keys/archived")` | **fired** — the page loads fine (HTTP 200) and looks maintained, but its only check-in is dated 3 February 2019. The validators agreed it does not satisfy the rule, the miss reached the threshold of 1, and the switch handed over: `holder` is now the successor and the handover note is theirs. | `0x53cae970dbe6f5709641ed7455463143be673481b8afa649bd90993a2b2aac14` |

State (`get_stats`): `{"switches":2,"armed":1,"fired":1,"disarmed":0,"pending_misses":0,"checks":3}`

Step 4 is the case an uptime monitor cannot see. Nothing about the page is *broken* — it is up, it
returns 200, it reads like a maintained status page. What it no longer contains is proof of life,
and that is a judgement about meaning, which is why it belongs under consensus.

### A note on the page renderer's cache

Studio Dev's page renderer serves a cached copy of a URL for several minutes. After the commit that
removed the check-in from `heartbeat.html`, a `check` still saw the old text — the captured
`total_chars` in the transaction's equivalence output still contained "28 September 2026" — and
therefore correctly answered **alive** for the text it was given. Anyone reproducing the
"holder goes quiet" flow should allow for that delay between the commit and the first miss; the
contract behaves the same either way, since it judges the text the validators actually agreed on.

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
