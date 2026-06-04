"""Database diagnostic tools for the SP-Traffic dbt project.

Provides diagnostic helpers for inspecting PostgreSQL state during dbt
development: row counts of dbt-managed tables, source freshness, active
queries, and lock contention. Used to debug hangs and stale-state
issues in dbt runs.
"""
