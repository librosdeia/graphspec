"""Stub referenced by research-publishing.yaml's `notify_authors` node.

A real implementation would post the final decision to the authors' channel;
it must be idempotent under its declared `idempotency_key`. graphspec never
executes this file — `E-KIND` only checks that declared `impl:` paths exist
next to the YAML.
"""


def notify(topic_id: str, final_decision: str) -> None:
    raise NotImplementedError("example stub — replace with your own notification logic")
