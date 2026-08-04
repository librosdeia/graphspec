"""Stub referenced by support-triage.yaml's `draft_review` node.

A real implementation compares the bot's and the knowledge-base's candidate
answers (whichever arrived first under `join: first`), scores confidence,
and writes `final_response` plus the `auto_resolvable` routing flag.
graphspec never executes this file — `E-KIND` only checks that declared
`impl:` paths exist next to the YAML.
"""


def score_confidence(candidate_answer: str, candidate_confidence: float) -> tuple[str, bool]:
    raise NotImplementedError("example stub — replace with your own scoring logic")
