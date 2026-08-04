"""Stub referenced by research-publishing.yaml's `publish_node` node.

A real implementation would push the accepted manuscript to the publication
target; it must be idempotent under its declared `idempotency_key`.
graphspec never executes this file — `E-KIND` only checks that declared
`impl:` paths exist next to the YAML.
"""


def publish(topic_id: str) -> None:
    raise NotImplementedError("example stub — replace with your own publishing logic")
