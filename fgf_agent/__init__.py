"""FGF AI agent layer.

An LLM-driven, tool-using agent that sits on top of the existing evidence
corpus. It plans, searches the knowledge base as many times as it needs (with
its own reformulated queries), uses deterministic calculators/event planners,
and writes a grounded answer with [E#] citations that are verified before the
answer is returned.

Standard library only, so the existing Docker image needs no new dependencies.

Public entry points:
    from fgf_agent import get_agent
    result = get_agent().ask("I'm F2P at core 28, what should I upgrade?", session_id="abc")
"""
from .agent import FGFAgent, get_agent, agent_status  # noqa: F401
from .retrieval import EvidenceIndex  # noqa: F401
