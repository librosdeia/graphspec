"""Stub referenced by the example graphs' `merge` nodes.

A real implementation merges the verified branches; it must be idempotent under
its declared `idempotency_key`. graphspec never executes this file — `E-KIND`
only checks that declared `impl:` paths exist next to the YAML.
"""


def merge(issue_id: str) -> None:
    raise NotImplementedError("example stub — replace with your own merge logic")
