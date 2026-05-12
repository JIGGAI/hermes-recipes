"""Adapters bridging hermes-recipes to the real Hermes Agent runtime.

Each integration module exposes:
  - a Protocol describing the surface the rest of the package depends on
  - a default implementation that calls the real Hermes runtime
  - a no-op / in-memory implementation for tests and dry runs
"""
