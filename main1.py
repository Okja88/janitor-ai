import os
from datetime import datetime, date

from typing import Optional
from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.templating import Jinja2Templates
from fastapi.responses import JSONResponse 
from sqlmodel import Field, Session, SQLModel, create_engine, select

import sqladmin
from sqladmin import Admin, ModelView
from sqladmin import BaseView, expose
from sqlalchemy import event
from sqlalchemy import Column, DateTime, func
from sqlalchemy import inspect

# --- Business Rules & Helpers ---
PROTECTED_PARTICLES = {"de", "da", "de la", "van", "von", "der", "di", "do", "al"}

def is_author_name_compliant(name: str) -> bool:
    """Checks if Author follows Title Case, ignoring specific particles."""
    if not name:
        return True
    words = name.split()
    for word in words:
        if word.lower() in PROTECTED_PARTICLES:
            continue
        if not word[0].isupper():
            return False
    return True

# 1. ----- Define the Model ------------------------------------
class Book(SQLModel, table=True):
    """
    Represents a book entry in the database.
    
    This model serves as both the database table schema (SQLAlchemy) 
    and the API data validation model (Pydantic).
    """
    id: Optional[int] = Field(default=None, primary_key=True)
    title: str
    author: str
    pages: int
    publisher: Optional[str] = None
    publication_date: Optional[date] = None

# 2. ----- Setup the Database Engine ------------------------------------
# sqlite_url: Specifies the local file destination
# echo=True: Logs all generated SQL commands to the console for debugging
sqlite_url = "sqlite:///database.db"
engine = create_engine(sqlite_url, echo=True)

# Create the tables in the .db file
def create_db_and_tables():
    """
    Initializes the SQLite database and creates all tables defined by SQLModel.
    
    Uses the metadata from all classes inherited from SQLModel (like Book and AuditLog)
    to generate the physical .db file and its internal schema.
    """
    SQLModel.metadata.create_all(engine)

app = FastAPI()

# Run table creation when the app starts
@app.on_event("startup")
def on_startup():
    """
    FastAPI startup event handler.
    
    Triggered automatically when the Uvicorn server starts. This ensures that 
    the database and all required tables exist before the application begins 
    accepting requests.
    """
    create_db_and_tables()

# Helper function to get a database session
def get_session():
    """
    Dependency provider for scoped database sessions.
    
    This engine initialization utility handles connection resource provisioning:
    1. Session Instantiation: Opens a fresh SQLModel session mapped to the SQLite engine.
    2. Operational Context: Yields operational control back to the invoking FastAPI path dependency injection framework.
    3. Automatic Disposal: Guarantees connection cleanup and prevents thread memory leaks via automated context boundary termination.

    This ensures that each separate incoming API transaction isolated on its own HTTP request loop obtains an independent database transaction path, preserving data consistency barriers.
    
    Yields:
        Session: A live, context-closed transaction workspace for executing database operations.
    """
    with Session(engine) as session:
        yield session

# The Automated Compliance Logic/Function
def compliance_monitor(mapper, connection, target):
    """
    SQLAlchemy event listener that validates Book data integrity during save operations.
    
    This interceptor acts as a low-level database engine pre-commit data guardrail:
    1. Identity Mapping: Inspects engine tracking states to extract verified, integer database primary keys.
    2. Re-entrancy Management: Queries existing logs to prevent duplicate warning entries from generating during recursive data transformations.
    3. Multi-Rule Audit Matrix: Scans transaction targets sequentially for non-compliant page configurations, lowercase string structures, and author naming protocols.

    This ensures that database records cannot bypass compliance thresholds regardless of whether data modification is initiated by user endpoints, the admin portal interface, or automated batch processes.
    
    Note: Highly critical database failures like empty titles bypass the logging lifecycle and result in immediate execution branch termination.
    """

    # Robustly extract the real database ID 
    # even mid-transaction during nested flushes
    state = inspect(target)
    
    # Force evaluation to explicit base Python integers to avoid matching wrappers
    if state.identity:
        book_id = int(state.identity[0])  # Hard primary key from the database row
    elif target.id is not None:
        book_id = int(target.id) # Fallback to model property
    else:
        book_id = None
    
    # 1. RE-ENTRANCY GUARD: Stop double flushes
    if book_id is not None:
        stmt_check = select(AuditLog).where(
            AuditLog.book_id == book_id, 
            AuditLog.agent_name == "Auto_Compliance_Agent"
        )
        already_flagged = connection.execute(stmt_check).first()
        if already_flagged:
            return  # Stop completely if this book already has an open log!

    # 2. INTEGRITY GUARD: Missing Title
    if not target.title or target.title.strip() == "":
        return

    # --- RULE 1: DUPLICATE DETECTION ---
    statement = select(Book).where(
        func.lower(Book.title) == func.lower(target.title or ""), 
        func.lower(Book.author) == func.lower(target.author or "")
    )
    all_matches = connection.execute(statement).all()

    is_genuine_duplicate = False
    
    # If the book has a verified identity row in the database table
    if book_id is not None:
        for match in all_matches:
            # Force clean integer casting to guarantee accurate evaluation matrix
            db_row_id = int(match[0])
            if db_row_id != book_id:  
                is_genuine_duplicate = True
                break
    else:
        # If it's a brand new insert and has no ID yet, 
        # any existing row in the DB means it's a genuine duplicate
        if len(all_matches) > 0:
            is_genuine_duplicate = True

    if is_genuine_duplicate:
        connection.execute(
            AuditLog.__table__.insert().values(
                book_id=book_id if book_id else 0,
                agent_name="Duplicate_Detector",
                error_type="duplicate", # Restored mapping column precision
                action_taken=f"DUPLICATE: Blocked '{target.title}'.",
                status="Fixed"
            )
        )
        return

    # --- RULE 2: PAGE COUNT COMPLIANCE ---
    if target.pages < 10:
        connection.execute(
            AuditLog.__table__.insert().values(
                book_id=book_id if book_id else 0,
                agent_name="Auto_Compliance_Agent",
                error_type="page_count",
                action_taken=f"WARNING: '{target.title}' is non-compliant ({target.pages} pages).",
                status="Pending"
            )
        )

    # --- RULE 3: TITLE CASE COMPLIANCE ---
    words = target.title.strip().split() if target.title else []
    needs_title_fix = any(w[0].islower() for w in words if w.isalpha()) if words else False

    if needs_title_fix:
        connection.execute(
            AuditLog.__table__.insert().values(
                book_id=book_id if book_id else 0,
                agent_name="Auto_Compliance_Agent",
                error_type="title_case",
                action_taken=f"FORMATTING: Title '{target.title}' is not in Title Case.",
                status="Pending"
            )
        )
       
    # --- RULE 4: Author Name Compliance ---
    if target.author and not is_author_name_compliant(target.author):
        # 1. Define the search query separately
        stmt = select(AuditLog).where(
            AuditLog.book_id == book_id, 
            AuditLog.status == "Pending",
            AuditLog.action_taken.contains("Author")
        )
        
        # 2. Execute and store the result
        existing_check = connection.execute(stmt).first()

        # 3. Only insert if no pending log was found
        if not existing_check:
            connection.execute(
                AuditLog.__table__.insert().values(
                    book_id=book_id,
                    agent_name="Auto_Compliance_Agent",
                    error_type="author_case",
                    action_taken=f"FORMATTING: Author '{target.author}' has non-compliant casing.",
                    status="Pending",
                    resolved_by="System"
                )
            )

# 3. ----- Updated Routes ------------------------------------
@app.post("/add-book")
def create_book(book: Book, session: Session = Depends(get_session)):
    """
    Primary endpoint to ingest new book records.
    
    This route performs the following lifecycle actions:
    1. Validates the incoming JSON against the Book SQLModel.
    2. Persists the record to the SQLite database.
    3. Triggers the 'Compliance Monitor' event listener to audit data integrity.
    
    Returns the created book object, including the database-generated ID.
    """
    session.add(book) # Add to the session
    session.commit()  # Save to the .db file permanently
    session.refresh(book)
    return book

@app.get("/books")
def get_books(session: Session = Depends(get_session)):
    """
    Retrieves all book records from the database.
    
    This endpoint utilizes SQLModel's 'exec' pattern to perform a 
    SELECT statement across the entire Book table. It is used to 
    populate the main library view and verify successful batch updates.
    """
    books = session.exec(select(Book)).all() # Query all books
    return books

@app.patch("/update-book/{book_id}")
def patch_book(book_id: int, book_data: dict, session: Session = Depends(get_session)):
    """
    Performs a partial update on an existing book record.
    
    This endpoint allows for 'delta' updates where only the provided fields 
    in the request body are modified. 
    
    Lifecycle:
    1. Locates the book by its primary key (book_id).
    2. Iteratively updates attributes using 'setattr' for dynamic mapping.
    3. Persists changes, which may re-trigger compliance event listeners 
       if audited fields (like 'title' or 'pages') are changed.
    
    Raises:
        HTTPException: 404 error if the book_id does not exist in the database.
    """
    db_book = session.get(Book, book_id)
    if not db_book:
        raise HTTPException(status_code=404, detail="Book not found")
    
    # Update fields
    for key, value in book_data.items():
        setattr(db_book, key, value)
    
    session.add(db_book)
    session.commit()
    session.refresh(db_book)
    return db_book

# 4. ----- Conceptual logic for the Run Intelligent Check Agent ------------------------------------
def run_intelligent_check(session, book_data):
    """
    Orchestrates the intelligent data repair and structural escalation logic layer.
    
    This script component operates as an analytical backend system coordinator that processes pending exceptions:
    1. State Synchronization: Flushes memory buffers and expires cache records to ensure exact real-time disk readability.
    2. Automated Remediation: Rewrites mismatched text variables into proper title case structures and transfers ownership to Janitor_AI.
    3. Cultural Logic Exception: Capitalizes author profiles according to business naming conventions while explicitly preserving lowercased international naming particles.
    4. Operational Isolation: Identifies duplicate records or structural gaps, creates system log traces, and flags indicators for separate manual worker analysis.

    This ensures that structural errors capable of automated resolution are handled without human intervention, maintaining a rapid processing throughput and updating analytical logs prior to structural persistence.
    
    Returns:
        str: A resolution status tracking code ('FIXED', 'CLERK_REQUIRED', or 'DUPLICATE') mapping the tracking outcome.
    """

    # 4.1 FORCE DATABASE SYNC:
    # This forces the session to look at the disk, not the memory.
    # It ensures the 'Pending' log from the listener is visible.
    session.flush()
    session.expire_all()

    # 4.2 Find the SPECIFIC formatting log for this book
    # Filtering by 'FORMATTING' ensures we don't grab a 'Page Count' log by mistake
    existing_log = session.exec(
        select(AuditLog).where(
            AuditLog.book_id == book_data.id,
            AuditLog.status == "Pending",
        )
    ).first()

    # 4.3 FORMATTING ISSUE: Not Camel Case (AI Auto-Fix)
    if book_data.title and not book_data.title.istitle():
        old_title = book_data.title
        # Add .strip() to clean up the edges
        book_data.title = book_data.title.strip().title() 
        
        # If we found an old 'Pending' log, update it. Otherwise, create a new one.
        log = existing_log if existing_log else AuditLog(book_id=book_data.id)
        
        # This is where the caption and status are corrected
        log.status = "AI-Fixed" 
        log.action_taken = f"AI fixed '{old_title}' to Title Case."
        log.agent_name = "Janitor_AI"
        log.resolved_by = "Janitor_AI"
        log.updated_at = datetime.now()
        
        session.add(log)
        session.add(book_data)
        # No session.commit() here; let the calling function handle it.
        return "FIXED"

    # 4.4 CRITICAL ERROR: Empty Title (Hand over to Clerk)
    if not book_data.title or book_data.title.strip() == "":
        log = existing_log or AuditLog(book_id=book_data.id, agent_name="Integrity_Guard")
        log.action_taken = "MISSING TITLE: Flagged for Clerk rectification."
        log.status = "Pending"
        session.add(log)
        session.commit()
        return "CLERK_REQUIRED"

        # No return here it continue to the duplicate check!

    # 4.5 Author names Repair Logic
    if book_data.author and not is_author_name_compliant(book_data.author):
        old_author = book_data.author
        # Smart repair: Capitalize words ONLY if they aren't in PROTECTED_PARTICLES
        new_name = " ".join([w.lower() if w.lower() in PROTECTED_PARTICLES else w.capitalize() for w in old_author.split()])
        book_data.author = new_name
        # Update or Create the AuditLog for the Author fix
        # Look for a pending author-related log to "close" it
        existing_author_log = session.exec(
        select(AuditLog).where(
            AuditLog.book_id == book_data.id,
            AuditLog.status == "Pending",
            # This ensures we don't accidentally resolve a "Duplicate" log with a "Formatting" fix
            AuditLog.action_taken.contains("Author") 
        )).first()

        # Reuse the existing log if found, otherwise create a new entry
        log = existing_author_log if existing_author_log else AuditLog(book_id=book_data.id)
    
        log.status = "AI-Fixed" 
        log.action_taken = f"AI fixed Author '{old_author}' to '{new_name}' (respecting particles)."
        log.agent_name = "Janitor_AI"
        log.resolved_by = "Janitor_AI"
        log.updated_at = datetime.now() # Explicitly update the resolution timestamp
    
        session.add(log)
        session.add(book_data)
    
        # Return FIXED to tell the dashboard that Janitor_AI successfully intervened
        return "FIXED"


    # 4.6 DUPLICATE CHECK 
    existing = session.execute(
        select(Book).where(func.lower(Book.title) == book_data.title.lower())
        ).scalar_one_or_none()

    if existing and existing.id != book_data.id: # Exclude self-matching check
        new_log = AuditLog(
            book_id=existing.id,
            agent_name="Duplicate_Detector",
            error_type="duplicate", # Force structural classification 
            action_taken=f"DUPLICATE: Blocked '{book_data.title}'.",
            status="Fixed"
        )
        session.add(new_log)
        session.commit()
        return "DUPLICATE"

# 5. ----- Create Admin interface ------------------------------------
# 5.1 Initialise the Admin
admin = Admin(app, engine)

# 5.2 Define the view
class BookAdmin(ModelView, model=Book):
    """
    Administrative interface for managing the Book library.
    
    This view provides CRUD capabilities, search, and sort functionality via 
    the SQLAdmin web dashboard. It integrates the 'Janitor_AI' logic by 
    hooking into the post-creation lifecycle to automatically audit 
    newly added books.
    """

    # Use the actual class attributes here
    column_list = [Book.id, Book.title, Book.author, Book.pages, Book.publisher, Book.publication_date]
    column_searchable_list = [Book.title, Book.author, Book.publisher]
    column_sortable_list = [Book.id, Book.publication_date]
    can_export = True

    # This ensures these fields appear when adding or editing a book
    form_columns = [
        "title", 
        "author",
        "pages", 
        "publisher", 
        "publication_date", 
    ]

    # "pass" on the change event to let the database finish its work
    async def on_model_change(self, data, model, is_created, request):
        pass

    # Use AFTER_model_change to create our AuditLogs safely
    async def after_model_change(self, data, model, is_created, request):
        """
        Post-persistence hook to trigger automated compliance checks.
        
        This method executes after a book is successfully saved to the database.
        It initiates a fresh session, merges the new book record, and hands 
        it off to the 'run_intelligent_check' agent to perform AI-driven 
        formatting repairs or flag missing data for human review.
        """

        if is_created:
            # Open the session FIRST
            with Session(engine) as session:
                try:
                    # Use 'merge' to bring the 'model' object into this new session
                    book_in_session = session.merge(model)

                    # Trigger Rectify Phase
                    run_intelligent_check(session, book_in_session)
                    
                    # Commit the changes made by the intelligent check
                    session.commit()
                except Exception as e:
                    print(f"Janitor Error: {e}")
                    session.rollback()

# 6. ----- AuditLog Model ------------------------------------
# 6.1 Define the AuditLog Model for Tracking Agent Actions
class AuditLog(SQLModel, table=True):
    """
    Persistence layer for agentic activity and system governance.
    
    This model records every intervention made by 'Integrity_Guard', 
    'Janitor_AI', or human users. It serves as the primary data source 
    for calculating the Automation Rate (KPIs) and provides a 
    historical trail for data rectification.
    """

    id: Optional[int] = Field(default=None, primary_key=True)
    book_id: int
    agent_name: str = Field(default="System") # e.g., "Auto_Compl_Agent"
    error_type: str = Field(default="formatting") # e.g., "page_count", "title_case", "author_case"
    action_taken: str # e.g., "Flagged low page count"
    status: str = Field(default="Pending")  # New: Pending, Fixed, or Research_Needed
    
    # 6.1.0 THE BIRTH TIMESTAMP: When the error was first discovered
    created_at: datetime = Field(
        sa_column=Column(
            DateTime(timezone=True), 
            server_default=func.now()
        )
    )

    # 6.1.1 THE RESOLUTION TIMESTAMP: When the status was last changed
    updated_at: datetime = Field(
        sa_column=Column(
            DateTime(timezone=True), 
            server_default=func.now(), 
            onupdate=func.now()
        )
    )

    # 6.1.2 THE IDENTITY FIELD: Who actually performed the final fix
    resolved_by: Optional[str] = Field(default="System")

# 6.2 Register the AuditLog in SQLAdmin
class AuditLogAdmin(ModelView, model=AuditLog):
    """
    Administrative interface for system audits and troubleshooting.
    
    Provides a chronological view of all agent actions. This view 
    is essential for monitoring the 'Janitor_AI' fix rate and 
    identifying systemic data entry issues flagged by the 
    Compliance Monitor.
    """

    # Extract all the columns 
    column_list = [
        "id",           # The Log Entry ID
        "book_id",      # The Link to the Book
        "created_at", 
        "agent_name", 
        "error_type",
        "action_taken", 
        "status",
        "updated_at"
    ]

    # This renders the date exactly how you want it: YYYY-MM-DD HH:MM:SS and Specific agent names
    column_formatters = {
        "created_at": lambda m, a: m.created_at.strftime("%Y-%m-%d %H:%M:%S") if m.created_at else "",
        "updated_at": lambda m, a: m.updated_at.strftime("%Y-%m-%d %H:%M:%S") if m.updated_at else "",
        "agent_name": lambda m, a: {
                                "Dup_D_Agent": "🔍 Duplicate Detector",
                                "Tit_D_Agent": "✍️ Title Fixer",
                                "Pag_D_Agent": "📄 Page Auditor"
                                }.get(m.agent_name, m.agent_name) # Fallback to original if not in map
    }
    
    column_labels = {
        "id": "ID",             
        "book_id": "BK_ID",    
        "created_at": "Created at",
        "agent_name": "Agent",
        "action_taken": "Action",
        "status": "Status",
        "updated_at": "Updated at"
    }
    column_default_sort = ("id", True) # Shows newest logs first


# 7. ----- Dashboard Endpoint & Interface ------------------------------------
# 7.1 Define the local template path
# This gets the folder named 'templates' in the project directory
base_dir = os.path.dirname(os.path.abspath(__file__))
template_path = os.path.join(base_dir, "templates")

# 7.2 Define the SQLAdmin template path
# This finds the internal 'layout.html' that the dashboard needs to 'extend'
sqladmin_dir = os.path.dirname(sqladmin.__file__)
sqladmin_templates = os.path.join(sqladmin_dir, "templates")

# 7.3 Create the templates object using BOTH paths in a list[cite: 3]
templates = Jinja2Templates(directory=[template_path, sqladmin_templates])

class ManagerDashboardView(BaseView):
    name = "Manager KPI Dashboard"
    icon = "fa fa-chart-line"

    """
    Aggregates system audit traces to compile operational performance metrics.
        
        Calculates real-time KPIs including:
        - Total structural exceptions identified across active assets.
        - Automated remediation rate (Janitor_AI footprint over total system flags).
        - Verification throughput (proportional completion of pending system reviews).
        
        Renders calculated values directly to the administrative web template.
    """
    
    # 7.4 Display KPI Dashboard Route
    @expose("/dashboard", methods=["GET"])
    async def display_kpis(self, request: Request):
        """
        Calculates and renders real-time performance metrics.
        
        Logic:
        1. Segregates logs into tiers: AI-Fixed, Clerk-Rectified, and Manager-Reviewed.
        2. Computes the 'Automation Rate' by measuring Janitor_AI's total footprint.
        3. Computes the 'Verification Rate' to track human oversight progress.
        4. Injects calculated metrics into the dashboard.html template.

        This ensures that management personnel have absolute visibility into data ingestion compliance rates, outstanding human data entry queues, and overall software exception volume.
        """

        with Session(engine) as session:
            all_logs = session.exec(select(AuditLog)).all()
            total_raw_flags = len(all_logs) # The technical metric
            
            # 7.4.1 New Multi-Tier Orchestrated Status Counts
            status_counts = {
                # Clerk Backlog: Only items that AI cannot fix (Empty Titles, etc.)
                "clerk_backlog": len([
                    l for l in all_logs 
                    if l.status == "Pending" and "MISSING TITLE" in l.action_taken.upper()
                ]),
                "ai_auto_fixed": len([l for l in all_logs if l.status == "AI-Fixed"]),
                "clerk_rectified": len([l for l in all_logs if l.status == "Rectified"]),
                "manager_reviewed": len([l for l in all_logs if l.status == "Reviewed"]),
                # Use colon (:) for dictionary assignment
                "ai_resolved_count": len([log for log in all_logs if log.agent_name == "Janitor_AI"])
            }
            
            # 7.4.2 Automation Rate Calculation
            # Calculated as: (Everything the Janitor touched / Total logs)
            auto_val = (status_counts["ai_resolved_count"] / total_raw_flags * 100) if total_raw_flags > 0 else 0
            automation_rate = f"{auto_val:.1f}%"

            # 7.4.3 Verification Rate Calculation
            # Calculated as: (Items you reviewed / Everything the Janitor fixed)
            # This measures your progress in approving the AI's work.
            verif_val = (status_counts["manager_reviewed"] / status_counts["ai_resolved_count"] * 100) if status_counts["ai_resolved_count"] > 0 else 0
            final_verification_rate = f"{verif_val:.1f}%"
            
            # 7.4.4 The business metric: Group by unique book IDs that exist on disk
            active_book_ids = {log.book_id for log in all_logs if log.status not in ["Reviewed", "Archived_Ghost_Log"]}
            
            # Cross-reference against live books to prevent ghost metric inflation
            live_books_count = 0
            for b_id in active_book_ids:
                if session.get(Book, b_id) is not None:
                    live_books_count += 1

            # Pack data for the HTML template
            kpi_data = {
                "total_issues": live_books_count,  # Strategic: Accurate active broken books count
                "system_exception_volume": total_raw_flags,  # Technical: Total raw signals processed by agents
                "automation_rate": automation_rate,
                "verification_rate": final_verification_rate,
                "verification_queue": status_counts["ai_auto_fixed"],
                "clerk_backlog": status_counts["clerk_backlog"],
                "avg_cycle_time": 0  # Placeholder
            }

            return await self.templates.TemplateResponse(
                request, 
                "dashboard.html", 
                {"kpi": kpi_data}
            )
    
    # 7.5 Manager Batch Review Route
    @expose("/manager-batch-review", methods=["POST"])
    async def manager_batch_review(self, request: Request):
        """
        Bulk approval transaction endpoint for the data reconciliation pipeline.
        
        This structural execution pathway finalizes data states by applying verified tracking changes in bulk:
        1. Automated Log Sweeping: Queries the database repository for any data rows currently matching an 'AI-Fixed' or 'Rectified' status framework.
        2. State Escalation: Overwrites target status properties to 'Reviewed' and generates fresh transaction timestamps to establish accountability records.
        3. Target Model Optimization: Iterates across individual linked database items to register tracking revisions alongside verified audit entries.

        This ensures that a clean data lifecycle is enforced, transforming raw data modifications into historical audit history records with one singular application operation.
        """

        # USE standard 'with Session'
        with Session(engine) as session:
            # SQLModel uses session.exec()
            statement = select(AuditLog).where(AuditLog.status.in_(["AI-Fixed", "Rectified"]))
            batch_logs = session.exec(statement).all()

            if not batch_logs:
                return JSONResponse(content={"message": "No logs to review."})

            for log in batch_logs:
                log.status = "Reviewed"
                log.updated_at = datetime.now()
                
                # Update the Book
                book = session.get(Book, log.book_id)
                if book:
                    # Only set updated_at if your Book model has that column
                    # book.updated_at = datetime.now() 
                    session.add(book)
                
                session.add(log)

            session.commit() # NO 'await' here
            return JSONResponse(content={"status": "Success", "message": "Batch Approved"})

    # 7.6 Janitor Cleanup Route
    @expose("/janitor/cleanup", methods=["POST"]) # SQLAdmin prefixes this with the view's path
    async def run_janitor_cleanup(self, request: Request):
        """
        Custom endpoint to trigger the Section 9 Repair Agent from the Dashboard UI.
        """
        with Session(engine) as session:
            # This calls your existing Section 9 logic
            stats = run_repair_agent(session) 
            
            # Return the results so the JavaScript alert can show them
            return JSONResponse(content={"status": "success", "data": stats})

# Register the views to appear in the sidebar automatically
admin.add_view(BookAdmin)
admin.add_view(AuditLogAdmin)
admin.add_view(ManagerDashboardView)

# 8. ----- Active Compliance Agent Router ----------------------------
@app.post("/compliance/run-audit")
def run_compliance_audit(session: Session = Depends(get_session)):
    """
    Executes a comprehensive system-wide data integrity sweep.
    
    This active agent reconciles existing Book records against governance rules:
    1. Integrity Check (Manual): Flags invalid page counts (<1) for Clerk intervention.
    2. Intelligent Repair (AI): Re-scans titles for formatting errors and triggers 
       the Janitor_AI repair sequence if non-compliance is detected.
    3. Cultural Logic (New): Validates and repairs Author names, ensuring Title Case 
       while preserving international naming particles (e.g., 'de', 'van', 'al').

    This ensures that records added before guardrails were implemented (or through 
    bulk imports) are brought up to standard, maintaining a clean audit trail and 
    reducing false positives in reporting.
    
    Returns:
        dict: A summary of the audit status, including the count of issues identified 
          and the success rate of automated repairs.
    """

    # 8.1 Fetch all books and existing pending logs
    books = session.exec(select(Book)).all()
    issues_found = 0
    
    for target in books:
        # Check for Rule 1: Pages (Manual Clerk Work)
        if target.pages < 1:
            # We only create a log if one doesn't already exist for this book
            existing_log = session.exec(
                select(AuditLog).where(AuditLog.book_id == target.id, AuditLog.status == "Pending")
            ).first()
            
            if not existing_log:
                new_log = AuditLog(
                    book_id=target.id,
                    agent_name="Manual_Compliance_Agent",
                    error_type="page_count",
                    action_taken=f"MISSING DATA: '{target.title}' has invalid pages ({target.pages}).",
                    status="Pending"
                )
                session.add(new_log)
                issues_found += 1
    
        # Check for Rule 2: Title Case (AI-Rectified Step)
        words = target.title.strip().split() if target.title else []
        needs_title_fix = any(w[0].islower() for w in words if w.isalpha()) if words else False
        
        if needs_title_fix:
            run_intelligent_check(session, target)
            issues_found += 1

        # Check for Rule 3: Author Name Compliance in existing records
        if target.author and not is_author_name_compliant(target.author):
            run_intelligent_check(session, target)
            issues_found += 1
            
    # Commit all changes (Book titles AND Audit logs) to the DB
    session.commit() 
    return {"status": "Audit Complete", "issues_logged": issues_found}

# 9. ----- Smart Repair Agent Background Service ------------------------------------
@app.post("/repair-agent/run")
def run_repair_agent(session: Session = Depends(get_session)):
    """
    Synchronizes the AuditLog with the current database state.
    
    This agent acts as a cleanup and verification utility that:
    1. Ghost Log Handling: Archives logs linked to deleted books.
    2. Human-Fix Verification: Automatically resolves logs if the underlying 
       data (pages/title) now meets compliance standards.
    3. AI Intervention: Attempts to auto-repair formatting errors that 
       remained in a 'Pending' state.
    4. Escalation: Flags records for 'Research_Needed' if automated repair 
       is logically impossible (e.g., missing page counts).
    
    Returns:
        dict: A summary of processed logs, categorized by the resolution type.
    """

    # 9.1 ALWAYS initialize first for API consistency
    counts = {"deleted": 0, "fixed": 0, "resolved": 0}
    
    # 9.2 Fetch logs that are NOT 'Fixed' or 'Resolved_by_User'
    # This targets everything that still needs attention
    statement = select(AuditLog).where(
        AuditLog.status != "Reviewed",
        AuditLog.status != "Resolved_by_User"
    )
    pending_logs = session.exec(statement).all()

    # 9.3 If none are found, this loop is skipped automatically
    for log in pending_logs:
        book = session.get(Book, log.book_id)

        # 9.3.1 Ghost Log Handling
        if not book:
            log.status = "Archived_Ghost_Log"
            current_action = log.action_taken or "Unknown anomaly detected."
            log.action_taken = f"{current_action} | System: Book no longer exists."
            session.add(log)
            counts["deleted"] += 1
            continue

        # 9.3.2 DECOUPLED FIELD VERIFICATION Metrics(Using explicit error_type columns)
        is_page_ok = log.error_type == "page_count" and book.pages >= 10
        is_title_ok = log.error_type == "title_case" and book.title.strip().istitle()
        is_author_ok = log.error_type == "author_case" and is_author_name_compliant(book.author)

        if is_page_ok or is_title_ok or is_author_ok:
            log.status = "Resolved_by_User"
            counts["resolved"] += 1
            session.add(log)
            continue  # Exit current item immediately

        # 9.3.4 Entity Collision & Duplicate Handling
        if log.error_type == "duplicate":
            log.status = "Resolved_by_User" 
            session.add(log)          
            continue  # ✨ FIXED: This continue stops the duplicate log from falling into formatting repairs!

        # 9.3.5 Structural Auto-Remediation Execution Block
        changed = False
        
        # Check error_type OR inspect the action text to prevent stranded logs
        is_title_issue = log.error_type == "title_case" or "TITLE" in log.action_taken.upper()
        is_author_issue = log.error_type == "author_case" or "AUTHOR" in log.action_taken.upper()

        if is_title_issue and (not book.title.istitle() or book.title != book.title.strip()):
            old_title = book.title
            book.title = book.title.strip().title()
            log.action_taken = f"AI fixed '{old_title}' to Title Case."
            changed = True

        if is_author_issue and not is_author_name_compliant(book.author):
            old_author = book.author
            book.author = " ".join([
                w.lower() if w.lower() in PROTECTED_PARTICLES else w.capitalize() 
                for w in book.author.strip().split()
            ])
            log.action_taken = f"AI fixed Author '{old_author}' to '{book.author}' (respecting particles)."
            changed = True
        
        if changed:
            log.status = "AI-Fixed"  # This flags it so "Approve Batch" can see it!
            log.agent_name = "Janitor_AI"       # Explicitly route attribution to the fixing agent
            log.resolved_by = "Janitor_AI"     # Track accountability properly
            log.updated_at = datetime.now()
            
            counts["fixed"] += 1
            session.add(book)
            session.add(log)
            continue
        
        # 9.3.6 Anomaly Escalation Processing
        if log.error_type == "page_count" and (not book.pages or book.pages == 0):
            log.status = "Research_Needed"
            log.action_taken += " | AI: Page count missing, research required."
            session.add(log)

    session.commit()
    return {
        "status": "Cleanup Finished",
        "results": {
            "auto_fixed": counts["fixed"],
            "user_fixes_verified": counts["resolved"],
            "duplicates_removed": counts["deleted"]
        }
    }

# Register the "triggers"
event.listen(Book, 'after_insert', compliance_monitor)
event.listen(Book, 'after_update', compliance_monitor)
