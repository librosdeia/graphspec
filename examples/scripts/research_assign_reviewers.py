"""Stub referenced by research-publishing.yaml's `assign_reviewers` node.

A real implementation would pick a panel of qualified peer reviewers for the
draft and write the `reviewers` list state field. graphspec never executes
this file — `E-KIND` only checks that declared `impl:` paths exist next to
the YAML.
"""


def assign_reviewers(draft_doc: str) -> list[str]:
    raise NotImplementedError("example stub — replace with your own reviewer assignment logic")
