Janitor_AI: Orchestrated Data Governance System
-------------------------------------------------------------------------------

-- Latest Updates (v1.1.0) --
🚀 Version History
v1.1.0 — Governance & UI Optimization (Current)
1) Standardized Agent Naming: Migrated to systematic D_Agent naming (e.g., Dup_D_Agent) to unify audit logs and reduce data entropy.

2) UI Real-Estate Optimization: Hard-coded a 120px sidebar and implemented non-wrapping table headers to maximize horizontal space for data review.

3) Display Logic: Added application-level formatters to standardize timestamps to YYYY-MM-DD HH:MM:SS, ensuring clean visibility regardless of database precision.

4) Governance Fix: Moved from dynamic column rendering to an explicit, governed column_list for consistent operational visibility.

v1.0.0 — MVP Baseline
1) Architecture Baseline: Implementation of core "Janitor" logic and event-driven compliance hooks.

2) Data Strategy: Established initial 37.5% automated rectification rate for metadata entry errors.

3) Operational Visibility: Basic real-time KPI tracking for system health and intervention backlogs.

-------------------------------------------------------------------------------

-- Project Overview --
Janitor_AI is a proactive data governance platform built with FastAPI and SQLModel. It serves as a proof-of-concept for an Automated Data Lifecycle, where database integrity is managed by a multi-tiered agent architecture. The system ensures that data is not only stored but is continuously audited and reconciled through a "Human-in-the-Loop" (HITL) workflow.


-------------------------------------------------------------------------------
-- Project Structure --
janitor-ai/
├── main1.py             # Single-file Monolith: API, Models, Agents & Logic
├── templates/           # Custom UI Dashboards
│   └── dashboard.html   # Manager KPI visualization
├── .gitignore           # Excludes database.db and local environment files
├── LICENSE              # MIT Open Source License
├── requirements.txt     # Project dependencies 
└── README.md            # Technical documentation & Architecture overview

-------------------------------------------------------------------------------
-- System Architecture --
1) The system is built on a Layered Service Architecture to ensure separation of concerns:

2) Ingestion Layer (FastAPI): Handles RESTful requests and performs initial Pydantic schema validation.

3) Intelligence Layer (SQLAlchemy Listeners): A "Pre-Commit" guard that intercepts database operations to perform real-time auditing without manual function calls.

4) Rectification Layer (Janitor_AI Agent): A service-level agent that handles state synchronization (session.flush()) and intelligent data repair.

5) Presentation Layer (SQLAdmin + Jinja2): A web-based "Command Center" that visualizes system performance and facilitates batch human approvals.

-------------------------------------------------------------------------------
-- Key Technical Features --
1) Event-Driven Compliance: Real-time scanning of all INSERT and UPDATE operations via SQLAlchemy event listeners to catch errors at the point of entry.

2) Internationalized Naming Compliance: A context-aware governance layer that enforces Title Case while preserving the integrity of cultural naming particles (e.g., van, von, de, al-).

3) Multi-Tiered Escalation: Intelligent logic that differentiates between "AI-Fixable" formatting and "Clerk-Required" structural issues, optimizing human intervention.

4) Self-Healing "Ghost-Killer" Logic: An automated maintenance agent that identifies and archives audit logs for deleted records to maintain database hygiene.

5) Manager KPI Dashboard: Real-time business intelligence visualizing Automation Rates, Clerk Backlogs, and System Health.

6) Proactive Data Reconciliation: A system-wide audit agent designed to retroactively align legacy data with current governance standards.

7) Traceable Audit Trail: Comprehensive logging of every automated and manual action to ensure full accountability and transparency.

-------------------------------------------------------------------------------
-- Tech Stack --
1) Backend: Python 3.10+, FastAPI (Asynchronous Web Framework).

2) Database & ORM: SQLModel (unifying SQLAlchemy 2.0 and Pydantic).

3) Engine: SQLite (Local development-ready).

4) Admin/UI: SQLAdmin (SQLAlchemy-powered admin interface) with custom Jinja2 templates.

5) Documentation: Automatic OpenAPI/Swagger UI generation.

-------------------------------------------------------------------------------
-- Architectural Design Solutions --
The system implements several high-level design patterns to ensure reliability:

1) Passive vs. Active Governance:

Passive (Event Listeners): Catching errors at the "moment of entry."

Active (Repair Agents): A decoupled service that performs bulk reconciliation and background cleanup.

2) State Synchronization: Implements session.merge() and session.expire_all() to manage object states across complex agentic workflows.

3) Human-in-the-Loop (HITL) Design: A deliberate architectural choice to ensure AI actions are always auditable and reversible by a human manager.

-------------------------------------------------------------------------------
-- Installation --
1) Clone: git clone https://github.com/Okja88/janitor-ai.git

2) Dependencies: pip install -r requirements.txt

3) Run: uvicorn main:app --reload
-------------------------------------------------------------------------------
-- Access the interfaces --
Interactive API Docs: http://127.0.0.1:8000/docs

Manager Dashboard: http://127.0.0.1:8000/admin

-------------------------------------------------------------------------------
-- Roadmap & Scalability (Architectural Vision) --
1) Performance Scaling: Transitioning from SQLite to a PostgreSQL backend to support high-concurrency write operations.

2) Security & RBAC: Implementing Role-Based Access Control to separate the "Clerk" (Manual Fixes) and "Manager" (Batch Approvals) interfaces.

3) Resiliency Testing: Expanding the testing suite to include data-collision simulations and listener failure recovery.

4) Containerization: Dockerizing the application for easier deployment.

-------------------------------------------------------------------------------
-- License --

Distributed under the MIT License. See LICENSE for more information.