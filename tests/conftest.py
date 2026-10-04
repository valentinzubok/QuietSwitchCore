"""Pytest bootstrap: a fake GenVM the tests steer.

Knobs:
  gl.clock              the transaction datetime, in unix seconds (see advance())
  gl.page               text the heartbeat page returns (str, or an Exception to raise)
  gl.llm_reply          raw model output (str/dict, or an Exception to raise)
  gl.comparative_fails  when True, eq_principle.prompt_comparative raises
  gl.prompts            every prompt sent, for assertions about quoting
"""

from __future__ import annotations

import sys
import types
from pathlib import Path


def _install_fake_genlayer() -> None:
    existing = sys.modules.get("genlayer")
    if existing is not None and getattr(existing, "_quietswitch_fake", False):
        return

    gl = types.ModuleType("genlayer")
    gl._quietswitch_fake = True

    class _Public:
        @staticmethod
        def write(fn):
            return fn

        @staticmethod
        def view(fn):
            return fn

    class _EqPrinciple:
        @staticmethod
        def prompt_comparative(leader_fn, principle="", /):
            """`principle` is positional-only in GenVM v0.3; the fake enforces that so a
            keyword call fails in tests exactly as it does on chain."""
            if getattr(gl, "comparative_fails", False):
                raise Exception("comparative consensus unavailable")
            return leader_fn()

        @staticmethod
        def strict_eq(leader_fn):
            return leader_fn()

    def _render(url, mode="text"):
        page = gl.page
        if isinstance(page, Exception):
            raise page
        return page

    def _exec_prompt(prompt, response_format=None):
        gl.prompts.append(prompt)
        reply = gl.llm_reply
        if isinstance(reply, Exception):
            raise reply
        return reply

    gl.contract = types.SimpleNamespace(Contract=object)
    gl.public = _Public()
    gl.message = types.SimpleNamespace(sender_address="0x1111111111111111111111111111111111111111")
    gl.eq_principle = _EqPrinciple()
    gl.nondet = types.SimpleNamespace(
        web=types.SimpleNamespace(render=_render),
        exec_prompt=_exec_prompt,
    )

    gl.clock = 1_767_225_600  # 2026-01-01T00:00:00Z — tests move it with advance()
    gl.page = "Proof of life: this key holder checked in on 28 September 2026."
    gl.llm_reply = '{"alive": true}'
    gl.comparative_fails = False
    gl.prompts = []
    sys.modules["genlayer"] = gl


def load_contract(repo_root: Path, filename: str = "QuietSwitch.py"):
    """Load the contract, with the clock wired to gl.clock.

    On chain, `datetime.now()` returns the transaction datetime: deterministic, identical
    for every validator. The stub below reproduces that so the observation interval can be
    tested without sleeping, and so a test cannot accidentally depend on wall-clock time.
    """
    _install_fake_genlayer()
    gl = sys.modules["genlayer"]
    path = repo_root / "contracts" / filename
    mod_name = f"contract_{filename.replace('.', '_')}"
    module = types.ModuleType(mod_name)
    module.__dict__["gl"] = gl
    exec(compile(path.read_text(encoding="utf-8"), str(path), "exec"), module.__dict__)

    real_datetime = module.__dict__["datetime"]

    class _TxDatetime(real_datetime):  # type: ignore[misc, valid-type]
        @classmethod
        def now(cls, tz=None):
            return real_datetime.fromtimestamp(gl.clock, tz)

    module.__dict__["datetime"] = _TxDatetime
    sys.modules[mod_name] = module
    return module


def advance(gl, seconds: int) -> None:
    """Move the transaction clock forward, e.g. past the observation interval."""
    gl.clock += int(seconds)


def reset(gl) -> None:
    gl.clock = 1_767_225_600  # 2026-01-01T00:00:00Z — tests move it with advance()
    gl.page = "Proof of life: this key holder checked in on 28 September 2026."
    gl.llm_reply = '{"alive": true}'
    gl.comparative_fails = False
    gl.prompts = []
    gl.message.sender_address = "0x1111111111111111111111111111111111111111"
