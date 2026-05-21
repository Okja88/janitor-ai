# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.2.0] - 2026-05-21

### Fixed
- **Background Worker Sequence:** Resolved an immediate initialization `NameError` runtime crash inside the `/repair-agent/run` background service loop by ensuring operational data variables are properly populated prior to collection processing.
- **Stranded Log Remediation:** Added explicit `error_type="author_case"` mapping within the database pre-commit event listener to prevent author anomalies from defaulting to a generic category and getting stranded permanently in a `Pending` state.
- **Audit Logging Trails:** Converted log string concats (`+=`) inside the automated formatting repair engine to clean, distinct text overrides to preserve professional data modification logs.

### Changed
- **Technical Documentation:** Overhauled internal module docstrings (`get_session`, `compliance_monitor`, `run_intelligent_check`, and administrative dashboard metrics) into thorough, multi-paragraph structural technical specifications.
- **Documentation Standards:** Scrubbed conversational informal pronouns ("you", "your") from all codebase comments and docstrings to enforce clean-room enterprise engineering compliance.

## [1.1.0] - 2026-05-12

### Added
- **Multi-Tier Dashboard Views:** Integrated a management KPI tracking panel separating human task queues, automated fix rates, and pending batch review tallies.
- **Janitor AI Engine:** Implemented automated background processing rules to handle basic string standardizations and lowercase formatting patterns.

## [1.0.0] - 2025-05-12

### Added
- **Core Ingestion Framework:** Established the foundational FastAPI web layer coupled with an asynchronous database pipeline driven by SQLModel.
- **Pre-Commit Engine Guardrails:** Configured foundational low-level database event listeners to track duplicate entries and log page verification counts.