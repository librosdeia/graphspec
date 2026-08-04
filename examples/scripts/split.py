"""Stub referenced by the example graphs' `fanout` nodes.

A real implementation reads the issue, decides how to partition the work and
writes the `branches` list state field. graphspec never executes this file —
`E-KIND` only checks that declared `impl:` paths exist next to the YAML.
"""


def split(issue_id: str) -> list[str]:
    raise NotImplementedError("example stub — replace with your own partitioning logic")
