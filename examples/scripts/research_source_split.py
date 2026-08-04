"""Stub referenced by research-publishing.yaml's `source_split` node.

A real implementation would pick which literature databases and preprint
servers to sweep for a given topic and write the `sources` list state field.
graphspec never executes this file — `E-KIND` only checks that declared
`impl:` paths exist next to the YAML.
"""


def source_split(topic_id: str) -> list[str]:
    raise NotImplementedError("example stub — replace with your own source selection logic")
