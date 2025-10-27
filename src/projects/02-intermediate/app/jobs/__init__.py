"""Background job definitions for the intermediate application."""

from __future__ import annotations

from .reporting import generate_task_report_job

__all__ = ["generate_task_report_job"]
