"""Telemetry for specific application flows.

Each module turns the milestones of one flow (a recovery turn, a GUI agent
task...) into spans, span attributes and log events, so the business code
only reports what happened.
"""
