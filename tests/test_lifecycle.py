"""Arming, liveness checks, firing, and access control."""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from conftest import load_contract, reset  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
mod = load_contract(ROOT)
gl = sys.modules["genlayer"]

OWNER = "0x1111111111111111111111111111111111111111"
HOLDER = OWNER
SUCCESSOR = "0x2222222222222222222222222222222222222222"
STRANGER = "0x3333333333333333333333333333333333333333"

URL = "https://keys.example/heartbeat"
RULE = "The page must state a check-in dated within the last 30 days."
NOTE = "Rotate the signing key with the procedure in runbook 7; the shard is with the notary."


def _armed(required="2"):
    reset(gl)
    c = mod.QuietSwitch(OWNER)
    c.arm("keys/primary", URL, RULE, SUCCESSOR, NOTE, required)
    return c


def test_arm_commits_the_whole_firing_condition():
    c = _armed()
    entry = json.loads(c.get_switch("keys/primary"))
    assert entry["status"] == "armed"
    assert entry["heartbeat_url"] == URL
    assert entry["rule"] == RULE
    assert entry["successor"] == SUCCESSOR
    assert entry["misses_required"] == 2
    assert entry["misses"] == 0
    assert json.loads(c.get_stats())["armed"] == 1


def test_a_living_page_resets_the_counter():
    c = _armed()
    gl.llm_reply = '{"alive": false}'
    c.check("keys/primary")
    assert json.loads(c.get_switch("keys/primary"))["misses"] == 1

    gl.llm_reply = '{"alive": true}'
    c.check("keys/primary")
    entry = json.loads(c.get_switch("keys/primary"))
    assert entry["misses"] == 0
    assert entry["last_result"] == "alive"
    assert entry["status"] == "armed"
    assert entry["last_page_hash"]


def test_consecutive_silence_fires_the_switch_to_the_successor():
    c = _armed()
    gl.page = "This page is under maintenance. Please check back later."
    gl.llm_reply = '{"alive": false}'

    c.check("keys/primary")
    entry = json.loads(c.get_switch("keys/primary"))
    assert entry["status"] == "armed" and entry["misses"] == 1
    assert entry["last_result"] == "missed"

    c.check("keys/primary")
    entry = json.loads(c.get_switch("keys/primary"))
    assert entry["status"] == "fired"
    assert entry["fired_to"] == SUCCESSOR
    assert entry["holder"] == SUCCESSOR  # the successor now holds the switch
    assert json.loads(c.get_stats())["fired"] == 1

    fired = [e for e in json.loads(c.get_events()) if e["kind"] == "Fired"][0]
    assert fired["from"] == HOLDER and fired["to"] == SUCCESSOR and fired["misses"] == 2

    with pytest.raises(Exception, match="not armed"):
        c.check("keys/primary")


def test_an_unreadable_heartbeat_counts_as_silence_but_says_why():
    c = _armed("1")
    gl.page = Exception("connection refused")
    c.check("keys/primary")
    entry = json.loads(c.get_switch("keys/primary"))
    assert entry["status"] == "fired"
    assert "unreachable" in entry["last_detail"]
    assert entry["last_page_hash"] == ""


def test_disarm_and_rearm_are_holder_only():
    c = _armed()
    gl.message.sender_address = STRANGER
    with pytest.raises(Exception, match="only the holder or the owner"):
        c.disarm("keys/primary")
    gl.message.sender_address = HOLDER
    c.disarm("keys/primary")
    assert json.loads(c.get_switch("keys/primary"))["status"] == "disarmed"
    with pytest.raises(Exception, match="not armed"):
        c.check("keys/primary")
    c.rearm("keys/primary")
    assert json.loads(c.get_switch("keys/primary"))["status"] == "armed"


def test_a_fired_switch_cannot_be_disarmed_by_the_old_holder():
    c = _armed("1")
    gl.llm_reply = '{"alive": false}'
    c.check("keys/primary")
    assert json.loads(c.get_switch("keys/primary"))["status"] == "fired"
    with pytest.raises(Exception, match="already fired"):
        c.disarm("keys/primary")


def test_anyone_may_run_the_check():
    """A switch only the holder can check is not a dead-man's switch."""
    c = _armed()
    gl.message.sender_address = STRANGER
    gl.llm_reply = '{"alive": false}'
    c.check("keys/primary")
    assert json.loads(c.get_switch("keys/primary"))["misses"] == 1


def test_validation_rules():
    c = _armed()
    with pytest.raises(Exception, match="already exists"):
        c.arm("keys/primary", URL, RULE, SUCCESSOR, NOTE)
    with pytest.raises(Exception, match="https://"):
        c.arm("keys/b", "http://keys.example/hb", RULE, SUCCESSOR, NOTE)
    with pytest.raises(Exception, match="path segments"):
        c.arm("keys/c", "https://keys.example/a/../b", RULE, SUCCESSOR, NOTE)
    with pytest.raises(Exception, match="successor must differ"):
        c.arm("keys/d", URL, RULE, HOLDER, NOTE)
    with pytest.raises(Exception, match="rule is required"):
        c.arm("keys/e", URL, "  ", SUCCESSOR, NOTE)
    with pytest.raises(Exception, match="between 1 and 10"):
        c.arm("keys/f", URL, RULE, SUCCESSOR, NOTE, "0")
    with pytest.raises(Exception, match="between 1 and 10"):
        c.arm("keys/g", URL, RULE, SUCCESSOR, NOTE, "99")
    assert json.loads(c.get_switch("nope"))["error"] == "unknown switch_id"
    assert json.loads(c.list_by_status("armed")) == ["keys/primary"]
    assert c.get_owner() == OWNER
