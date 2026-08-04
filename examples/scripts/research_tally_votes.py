"""Stub referenced by research-publishing.yaml's `panel_verdict` node.

A real implementation would tally the peer reviewers' individual verdicts
into a single majority `review_verdict` state field. graphspec never
executes this file — `E-KIND` only checks that declared `impl:` paths exist
next to the YAML.
"""


def tally_votes(reviewers: list[str]) -> str:
    raise NotImplementedError("example stub — replace with your own majority-tally logic")
