"""The TruTrace workbench: Prompt Lab + Experiment Runner.

Built around the existing pipeline, not instead of it. Prompts become
immutable files on disk (prompt_store), experiments run through the
existing verification engine and persist everything (runner), and a
small local server (server.py) puts the two on screens. Correctness
still comes from one place: app/verification + evals/metrics.
"""
