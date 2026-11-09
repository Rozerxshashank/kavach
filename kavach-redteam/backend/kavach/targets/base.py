"""What Kavach needs from any voice agent it attacks.

A target is a voice agent plus everything Kavach must know to attack it fairly and judge it honestly: the situation
the attacker walks into, who may call, what they are after, how to tell (with ground truth, not opinion) that the agent
broke, how to write a fix for it, and how to promote a proven fix to the agent's live version.

Kavach owns the phone line (Timbre voices, acoustic environments, Prisma ears). A target only ever receives what
it "heard" through Prisma, and answers with text plus, if it speaks for itself, its own audio.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..judge import Finding, TurnVerdict


class TargetError(Exception):
    """The agent under test failed or is unreachable (not a finding: the run stops with an error)."""


@dataclass
class Reply:
    text: str
    language: str = "en-IN"
    audio: bytes | None = None          # the agent's own voice, if it synthesises speech itself
    done: bool = False                  # the agent ended the call
    tools: list = field(default_factory=list)      # actions it took (bank tools), for ground-truth judging
    intent: str | None = None           # how the agent understood the caller (if it says)
    meta: dict = field(default_factory=dict)


class Session:
    """One sandboxed call with the agent."""

    supports_interruption = False

    async def open(self) -> Reply:
        raise NotImplementedError

    async def turn(self, heard: str, n: int, guidance: str = "") -> Reply:
        """guidance: Kavach Shield's note about this caller (proxy mode), for agents that can take it."""
        raise NotImplementedError

    def interrupted(self) -> None:
        """The caller talked over the agent's last line (only meaningful if supports_interruption)."""

    def attach_action_guard(self, guard) -> None:
        """Let Kavach Shield allow or deny the agent's actions (guard: name -> (allowed, reason))."""

    @property
    def world(self) -> dict | None:
        return None

    async def outcome(self) -> dict:
        return {}

    async def close(self) -> None:
        return None

    @property
    def verified(self) -> bool:
        """Whether the caller has passed the agent's own verification (if it has one)."""
        return False


class Target:
    id: str = ""
    name: str = ""                      # the product being protected, e.g. "Saakshi"
    agent: str = ""                     # the voice agent's own name, e.g. "Sahayak"
    kind: str = ""                      # one line: what this agent does
    description: str = ""
    voice: str = "Nalini"               # used when the agent doesn't speak for itself
    languages: tuple[str, ...] = ("en-IN", "hi-IN")
    personas: dict[str, dict] = {}
    objectives: dict[str, dict] = {}
    gates: dict[str, str] = {}          # hard code-level protections a fix may switch on
    shield_policy: str = ""             # the Kavach Shield policy that protects this agent
    shield_native: bool = False         # the agent calls the Shield itself (SDK); otherwise Kavach runs it as a proxy

    def shield_secrets(self, world: dict | None) -> dict[str, list[str]]:
        """Values this particular call must never speak (registered with the Shield for this call only)."""
        return {}

    def tactics(self) -> dict[str, dict]:
        from ..playbook import TACTICS
        return TACTICS

    def scenario(self, world: dict | None) -> str:
        raise NotImplementedError

    def attacker_fill(self, world: dict | None) -> dict:
        return {}

    def check_line(self, text: str) -> str | None:
        """A target-specific sanity check on an attacker line; a reason makes the attacker rewrite it."""
        return None

    def new_world(self) -> dict | None:
        """Sandbox data for a fresh attack (kept with the run so a replay meets the same world)."""
        return None

    def reveal(self, world: dict | None) -> dict | None:
        """What the sandbox hid, shown after the verdict (planted secrets, ground truth)."""
        return None

    async def available(self) -> tuple[bool, str]:
        return True, ""

    # ---- versions ---------------------------------------------------------------------------------------------------
    async def versions(self) -> dict:
        """{"live": hardening, "versions": [hardening...]} where a hardening is the agent's security config."""
        raise NotImplementedError

    async def hardening(self, choice: str | int) -> dict:
        """'live' / 'original' / a version number -> that version's hardening."""
        raise NotImplementedError

    def candidate(self, base: dict, title: str, rules: list[str], gates: dict[str, bool]) -> dict:
        """A fix under test: the attacked version plus new rules and gates. Never stored as a version."""
        raise NotImplementedError

    async def promote(self, candidate: dict, source_run: str, note: str | None) -> dict:
        raise NotImplementedError

    async def activate(self, version: int) -> dict:
        raise NotImplementedError

    # ---- calls ------------------------------------------------------------------------------------------------------
    async def open(self, *, language: str, hardening: dict, world: dict | None, shield: bool = False) -> Session:
        """shield: for agents with shield_native, run this call under Kavach Shield inside the agent."""
        raise NotImplementedError

    # ---- judging ----------------------------------------------------------------------------------------------------
    async def judge_turn(self, n: int, heard: str, reply: Reply, verified_before: bool, world: dict | None) -> TurnVerdict:
        raise NotImplementedError

    def objective_hit(self, objective: str, reply: Reply, verdict: TurnVerdict, verified_before: bool) -> bool:
        return False

    async def final_findings(self, run: dict, outcome: dict) -> tuple[list[Finding], str]:
        """Ground truth from the agent's final state plus a whole-call audit: (findings, summary)."""
        return [], ""

    # ---- fixing -----------------------------------------------------------------------------------------------------
    async def propose_fix(self, run: dict) -> dict:
        raise NotImplementedError

    def public(self) -> dict[str, Any]:
        return {"id": self.id, "name": self.name, "agent": self.agent, "kind": self.kind,
                "description": self.description, "languages": list(self.languages), "personas": self.personas,
                "objectives": self.objectives, "gates": self.gates,
                "tactics": {k: v["label"] for k, v in self.tactics().items()}}
