# -*- coding: utf-8 -*-
"""
Database service layer for Sewa Setu MCP servers.
Provides isolated, authorized, and audited access to the PostgreSQL database.
"""

import os
import re
import configparser
from datetime import datetime, date, timedelta
from typing import Optional, Dict, Any, List, Tuple
from zoneinfo import ZoneInfo

import psycopg2
import psycopg2.extras

IST = ZoneInfo("Asia/Kolkata")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(BASE_DIR, "app", "config", "app.ini")

config = configparser.ConfigParser()
if os.path.exists(CONFIG_PATH):
    config.read(CONFIG_PATH)

DB_HOST = os.environ.get("DB_HOST") or config.get("database", "host", fallback="localhost")
DB_PORT = os.environ.get("DB_PORT") or config.get("database", "port", fallback="5432")
DB_NAME = os.environ.get("DB_NAME") or config.get("database", "name", fallback="sewasetu")
DB_USER = os.environ.get("DB_USER") or config.get("database", "user", fallback="sewasetu")
DB_PASSWORD = os.environ.get("DB_PASSWORD") or config.get("database", "password", fallback="sewasetu123")

MIN_AGE = int(os.environ.get("MIN_AGE", 60))
SLA_DAYS = int(os.environ.get("SLA_DAYS", 15))
BLOCKS = ["Sonari", "Rajapara", "Dhemaji Pathar", "Borgaon", "Namti", "Khelua"]
ACTIVE_STATUSES = ("PENDING", "APPROVED", "DEEMED_APPROVED")


def now_ist() -> datetime:
    """Current timestamp in Indian Standard Time (naive for PostgreSQL compatibility)."""
    return datetime.now(IST).replace(tzinfo=None)


_POSTGRES_AVAILABLE = True


def get_db_connection():
    """Establish and return a connection to the PostgreSQL database with fallback."""
    global _POSTGRES_AVAILABLE
    if not _POSTGRES_AVAILABLE:
        return _get_sqlite_fallback()

    try:
        conn = psycopg2.connect(
            host=DB_HOST,
            port=DB_PORT,
            dbname=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD,
            connect_timeout=2
        )
        return conn
    except Exception:
        # PostgreSQL unavailable, use SQLite fallback
        _POSTGRES_AVAILABLE = False
        return _get_sqlite_fallback()


class SQLiteCursorWrapper:
    def __init__(self, cursor):
        self.cursor = cursor

    def execute(self, sql, params=None):
        s = sql.replace("%s", "?")
        s = re.sub(r"\bILIKE\b", "LIKE", s, flags=re.IGNORECASE)
        if params is None:
            return self.cursor.execute(s)
        return self.cursor.execute(s, params)

    def fetchone(self):
        return self.cursor.fetchone()

    def fetchall(self):
        return self.cursor.fetchall()

    def close(self):
        return self.cursor.close()


class SQLiteConnWrapper:
    def __init__(self, conn):
        self.conn = conn

    def cursor(self):
        return SQLiteCursorWrapper(self.conn.cursor())

    def commit(self):
        return self.conn.commit()

    def close(self):
        # Keep connection open for process lifetime
        pass


_SQLITE_CONN = None


def _get_sqlite_fallback():
    global _SQLITE_CONN
    if _SQLITE_CONN is not None:
        return SQLiteConnWrapper(_SQLITE_CONN)
    import sqlite3
    db_path = os.path.join(BASE_DIR, "test_local.db")
    conn = sqlite3.connect(db_path, check_same_thread=False)
    _init_sqlite_schema(conn)
    _SQLITE_CONN = conn
    return SQLiteConnWrapper(_SQLITE_CONN)


def _init_sqlite_schema(conn):
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS applications (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        application_no TEXT,
        applicant_name TEXT,
        mobile TEXT,
        dob TEXT,
        gender TEXT,
        marital_status TEXT,
        husband_name TEXT,
        husband_employer TEXT,
        village TEXT,
        block TEXT,
        bank_account TEXT,
        ifsc TEXT,
        doc_path TEXT,
        status TEXT DEFAULT 'PENDING',
        submitted_at TIMESTAMP,
        decided_at TIMESTAMP,
        decided_by TEXT
    );
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS audit_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        application_id INTEGER,
        action TEXT,
        actor TEXT,
        note TEXT,
        at TIMESTAMP
    );
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS oauth_refresh_tokens (
        token_hash TEXT PRIMARY KEY,
        client_id TEXT,
        client_name TEXT,
        subject TEXT,
        role TEXT,
        scope TEXT,
        resource TEXT,
        created_at TIMESTAMP,
        expires_at TIMESTAMP,
        revoked_at TIMESTAMP
    );
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS oauth_keys (
        kid TEXT PRIMARY KEY,
        private_pem TEXT,
        created_at TIMESTAMP
    );
    """)
    conn.commit()
    cur.close()


def mask_bank_account(account: str) -> str:
    """Mask bank account showing only last 4 digits for data privacy."""
    if not account:
        return ""
    clean = re.sub(r"\s+", "", str(account))
    if len(clean) <= 4:
        return "******" + clean
    return "*" * (len(clean) - 4) + clean[-4:]


def mask_mobile(mobile: str) -> str:
    """Mask mobile number showing only last 4 digits."""
    if not mobile:
        return ""
    clean = str(mobile).strip()
    if len(clean) >= 4:
        return "XXXXXX" + clean[-4:]
    return clean


def parse_dob_any(raw: Any) -> Optional[date]:
    """Parse date of birth in various common formats."""
    if not raw:
        return None
    if isinstance(raw, date):
        return raw
    s = str(raw).strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d%m%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    return None


def calculate_age(dob: date, on_date: Optional[date] = None) -> int:
    """Calculate age on given date or today in IST."""
    if not on_date:
        on_date = now_ist().date()
    return on_date.year - dob.year - ((on_date.month, on_date.day) < (dob.month, dob.day))


# ---------------------------------------------------------------------------
# Citizen Database Operations (Strictly Scoped by Mobile Number)
# ---------------------------------------------------------------------------

def citizen_get_profile(mobile: str) -> Optional[Dict[str, Any]]:
    """Retrieve applicant profile strictly scoped to their verified mobile."""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT applicant_name, mobile, dob, village, block, bank_account, ifsc, status
        FROM applications
        WHERE mobile = %s
        ORDER BY submitted_at DESC LIMIT 1
    """, (mobile,))
    row = cur.fetchone()
    cur.close()
    conn.close()

    if not row:
        return None

    return {
        "applicant_name": row[0],
        "mobile": mask_mobile(row[1]),
        "dob": str(row[2]) if row[2] else None,
        "village": row[3],
        "block": row[4],
        "bank_account_masked": mask_bank_account(row[5]),
        "ifsc": row[6],
        "latest_application_status": row[7]
    }


def citizen_get_application(mobile: str) -> Optional[Dict[str, Any]]:
    """Retrieve latest active or most recent application for authenticated citizen."""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT id, application_no, applicant_name, dob, gender, marital_status,
               village, block, bank_account, ifsc, status, submitted_at,
               decided_at, decided_by
        FROM applications
        WHERE mobile = %s
        ORDER BY submitted_at DESC LIMIT 1
    """, (mobile,))
    row = cur.fetchone()
    cur.close()
    conn.close()

    if not row:
        return None

    return {
        "application_id": row[0],
        "application_no": row[1],
        "applicant_name": row[2],
        "dob": str(row[3]) if row[3] else None,
        "gender": row[4],
        "marital_status": row[5],
        "village": row[6],
        "block": row[7],
        "bank_account_masked": mask_bank_account(row[8]),
        "ifsc": row[9],
        "status": row[10],
        "submitted_at": str(row[11]) if row[11] else None,
        "decided_at": str(row[12]) if row[12] else None,
        "decided_by": row[13]
    }


def citizen_get_timeline(mobile: str) -> List[Dict[str, Any]]:
    """Retrieve chronological event history for citizen's application."""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, application_no FROM applications WHERE mobile = %s ORDER BY submitted_at DESC LIMIT 1", (mobile,))
    app_row = cur.fetchone()
    if not app_row:
        cur.close()
        conn.close()
        return []

    app_id = app_row[0]
    cur.execute("""
        SELECT action, actor, note, at
        FROM audit_log
        WHERE application_id = %s
        ORDER BY at ASC
    """, (app_id,))
    events = cur.fetchall()
    cur.close()
    conn.close()

    return [
        {
            "action": ev[0],
            "actor": ev[1],
            "note": ev[2] or "",
            "timestamp": str(ev[3]) if ev[3] else None
        }
        for ev in events
    ]


def citizen_withdraw_application(mobile: str, confirm: bool = False) -> Dict[str, Any]:
    """Withdraw citizen's PENDING application with required explicit confirmation."""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT id, application_no, status FROM applications
        WHERE mobile = %s AND status = 'PENDING'
        ORDER BY submitted_at DESC LIMIT 1
    """, (mobile,))
    row = cur.fetchone()

    if not row:
        cur.close()
        conn.close()
        return {
            "success": False,
            "message": "No pending application found that is eligible for withdrawal. Only applications in PENDING status can be withdrawn."
        }

    app_id, app_no, status = row

    if not confirm:
        cur.close()
        conn.close()
        return {
            "success": False,
            "requires_confirmation": True,
            "application_no": app_no,
            "message": f"Are you sure you want to withdraw application {app_no}? Once withdrawn, you can submit a new application. Please confirm by setting confirm=True."
        }

    now = now_ist()
    cur.execute("""
        UPDATE applications
        SET status = 'WITHDRAWN', decided_at = %s, decided_by = 'APPLICANT'
        WHERE id = %s AND mobile = %s AND status = 'PENDING'
    """, (now, app_id, mobile))

    cur.execute("""
        INSERT INTO audit_log (application_id, action, actor, note, at)
        VALUES (%s, 'WITHDRAW', %s, 'Withdrawn by applicant via AI assistant', %s)
    """, (app_id, f"applicant:{mobile}", now))

    conn.commit()
    cur.close()
    conn.close()

    return {
        "success": True,
        "application_no": app_no,
        "status": "WITHDRAWN",
        "message": f"Application {app_no} has been successfully withdrawn. You are now eligible to submit a fresh application."
    }


def citizen_get_connected_applications(mobile: str) -> List[Dict[str, Any]]:
    """Retrieve list of third-party OAuth applications authorized by citizen."""
    conn = get_db_connection()
    cur = conn.cursor()
    subject = f"citizen:{mobile}"
    now = now_ist()
    cur.execute("""
        SELECT client_name, client_id, scope, created_at, expires_at
        FROM oauth_refresh_tokens
        WHERE subject = %s AND revoked_at IS NULL AND expires_at > %s
        ORDER BY created_at DESC
    """, (subject, now))
    rows = cur.fetchall()
    cur.close()
    conn.close()

    return [
        {
            "client_name": r[0] or "Application",
            "client_id": r[1],
            "scope": r[2],
            "authorized_at": str(r[3]),
            "session_ends_at": str(r[4])
        }
        for r in rows
    ]


# ---------------------------------------------------------------------------
# Officer Database Operations (Queue Management, Search, Audit, Decisions)
# ---------------------------------------------------------------------------

def officer_search_applications(
    query: str,
    search_type: str = "auto",
    block_filter: Optional[str] = None,
    limit: int = 50
) -> List[Dict[str, Any]]:
    """Search applications by application number, mobile, or name."""
    conn = get_db_connection()
    cur = conn.cursor()
    q = query.strip()
    limit = max(1, min(limit, 100))

    sql = """
        SELECT id, application_no, applicant_name, mobile, block, village, status, submitted_at
        FROM applications
        WHERE 1=1
    """
    params: List[Any] = []

    if block_filter:
        sql += " AND block = %s"
        params.append(block_filter)

    if search_type == "application_no" or (search_type == "auto" and q.upper().startswith("SSP")):
        sql += " AND UPPER(application_no) = %s"
        params.append(q.upper())
    elif search_type == "mobile" or (search_type == "auto" and q.isdigit() and len(q) == 10):
        sql += " AND mobile = %s"
        params.append(q)
    else:
        sql += " AND applicant_name ILIKE %s"
        params.append(f"%{q}%")

    sql += " ORDER BY submitted_at DESC LIMIT %s"
    params.append(limit)

    cur.execute(sql, tuple(params))
    rows = cur.fetchall()
    cur.close()
    conn.close()

    return [
        {
            "application_id": r[0],
            "application_no": r[1],
            "applicant_name": r[2],
            "mobile": r[3],
            "block": r[4],
            "village": r[5],
            "status": r[6],
            "submitted_at": str(r[7]) if r[7] else None
        }
        for r in rows
    ]


def officer_get_application_details(
    application_id: Any,
    officer_block: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """Retrieve comprehensive officer details for an application."""
    conn = get_db_connection()
    cur = conn.cursor()

    if isinstance(application_id, str) and application_id.upper().startswith("SSP"):
        cur.execute("SELECT id FROM applications WHERE UPPER(application_no) = %s", (application_id.upper(),))
        row_id = cur.fetchone()
        if not row_id:
            cur.close()
            conn.close()
            return None
        app_pk = row_id[0]
    else:
        try:
            app_pk = int(application_id)
        except ValueError:
            cur.close()
            conn.close()
            return None

    cur.execute("""
        SELECT id, application_no, applicant_name, mobile, dob, gender,
               marital_status, village, block, bank_account, ifsc, doc_path,
               status, submitted_at, decided_at, decided_by
        FROM applications
        WHERE id = %s
    """, (app_pk,))
    row = cur.fetchone()
    if not row:
        cur.close()
        conn.close()
        return None

    if officer_block and row[8] != officer_block:
        cur.close()
        conn.close()
        return {"error": f"Access restricted. Application belongs to block '{row[8]}', but officer is restricted to '{officer_block}'."}

    # Fetch audit log
    cur.execute("SELECT action, actor, note, at FROM audit_log WHERE application_id = %s ORDER BY at ASC", (app_pk,))
    audit_rows = cur.fetchall()
    cur.close()
    conn.close()

    return {
        "application_id": row[0],
        "application_no": row[1],
        "applicant_name": row[2],
        "mobile": row[3],
        "dob": str(row[4]) if row[4] else None,
        "gender": row[5],
        "marital_status": row[6],
        "village": row[7],
        "block": row[8],
        "bank_account_masked": mask_bank_account(row[9]),
        "ifsc": row[10],
        "doc_path": row[11],
        "status": row[12],
        "submitted_at": str(row[13]) if row[13] else None,
        "decided_at": str(row[14]) if row[14] else None,
        "decided_by": row[15],
        "audit_history": [
            {
                "action": a[0],
                "actor": a[1],
                "note": a[2] or "",
                "timestamp": str(a[3])
            }
            for a in audit_rows
        ]
    }


def officer_list_pending(
    block: Optional[str] = None,
    limit: int = 50,
    offset: int = 0
) -> List[Dict[str, Any]]:
    """List pending applications ordered by submission date (oldest first for SLA prioritization)."""
    conn = get_db_connection()
    cur = conn.cursor()
    limit = max(1, min(limit, 100))
    offset = max(0, offset)

    if block:
        cur.execute("""
            SELECT id, application_no, applicant_name, mobile, village, block, submitted_at
            FROM applications
            WHERE status = 'PENDING' AND block = %s
            ORDER BY submitted_at ASC
            LIMIT %s OFFSET %s
        """, (block, limit, offset))
    else:
        cur.execute("""
            SELECT id, application_no, applicant_name, mobile, village, block, submitted_at
            FROM applications
            WHERE status = 'PENDING'
            ORDER BY submitted_at ASC
            LIMIT %s OFFSET %s
        """, (limit, offset))

    rows = cur.fetchall()
    cur.close()
    conn.close()

    now = now_ist()
    out = []
    for r in rows:
        sub_at = r[6]
        if isinstance(sub_at, str):
            try:
                sub_at = datetime.fromisoformat(sub_at.replace(" ", "T"))
            except Exception:
                sub_at = None
        days_pending = (now - sub_at).days if (now and sub_at) else 0
        sla_warning = days_pending >= (SLA_DAYS - 3)
        out.append({
            "application_id": r[0],
            "application_no": r[1],
            "applicant_name": r[2],
            "mobile": r[3],
            "village": r[4],
            "block": r[5],
            "submitted_at": str(sub_at) if sub_at else None,
            "days_pending": days_pending,
            "sla_warning": sla_warning
        })
    return out


def officer_decide_application(
    application_id: Any,
    action: str,  # 'APPROVED' or 'REJECTED'
    note: str,
    officer_username: str,
    confirm: bool = False
) -> Dict[str, Any]:
    """
    Approve or reject a PENDING application.
    Requires explicit confirmation and validates state transitions.
    """
    conn = get_db_connection()
    cur = conn.cursor()

    if isinstance(application_id, str) and application_id.upper().startswith("SSP"):
        cur.execute("SELECT id, application_no, applicant_name, status, block FROM applications WHERE UPPER(application_no) = %s", (application_id.upper(),))
    else:
        try:
            app_pk = int(application_id)
            cur.execute("SELECT id, application_no, applicant_name, status, block FROM applications WHERE id = %s", (app_pk,))
        except ValueError:
            cur.close()
            conn.close()
            return {"success": False, "error": f"Invalid application identifier: {application_id}"}

    row = cur.fetchone()
    if not row:
        cur.close()
        conn.close()
        return {"success": False, "error": "Application not found"}

    app_id, app_no, applicant_name, current_status, block = row

    if current_status != "PENDING":
        cur.close()
        conn.close()
        return {
            "success": False,
            "error": f"Cannot {action.lower()} application {app_no}. Current status is '{current_status}'. Only applications in PENDING status can be decided."
        }

    if not confirm:
        cur.close()
        conn.close()
        return {
            "success": False,
            "requires_confirmation": True,
            "application_id": app_id,
            "application_no": app_no,
            "applicant_name": applicant_name,
            "action": action,
            "note": note,
            "message": f"Please confirm {action} decision for application {app_no} ({applicant_name}, Block: {block}). Note: '{note}'. Call this tool with confirm=True to commit."
        }

    now = now_ist()
    actor_str = f"officer:{officer_username}"
    cur.execute("""
        UPDATE applications
        SET status = %s, decided_at = %s, decided_by = %s
        WHERE id = %s AND status = 'PENDING'
    """, (action, now, officer_username, app_id))

    cur.execute("""
        INSERT INTO audit_log (application_id, action, actor, note, at)
        VALUES (%s, %s, %s, %s, %s)
    """, (app_id, action, actor_str, note or f"{action} by officer", now))

    conn.commit()
    cur.close()
    conn.close()

    return {
        "success": True,
        "application_id": app_id,
        "application_no": app_no,
        "new_status": action,
        "decided_by": officer_username,
        "timestamp": str(now),
        "message": f"Application {app_no} has been {action.lower()} successfully."
    }


def officer_get_statistics() -> Dict[str, Any]:
    """Calculate aggregated application stats across blocks, statuses, and SLAs."""
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("SELECT status, count(*) FROM applications GROUP BY status")
    by_status = dict(cur.fetchall())

    now = now_ist()
    sla_cutoff = now - timedelta(days=SLA_DAYS)
    cur.execute("SELECT count(*) FROM applications WHERE status = 'PENDING' AND submitted_at < %s", (sla_cutoff,))
    overdue_count = cur.fetchone()[0]

    cur.execute("""
        SELECT block, count(*)
        FROM applications
        WHERE status = 'PENDING'
        GROUP BY block
        ORDER BY count(*) DESC
    """)
    by_block = dict(cur.fetchall())

    cur.close()
    conn.close()

    total = sum(by_status.values())

    return {
        "total_applications": total,
        "status_breakdown": by_status,
        "overdue_pending_past_sla": overdue_count,
        "sla_days_threshold": SLA_DAYS,
        "pending_by_block": by_block
    }


def officer_get_sla_breach_report(threshold_days: int = 15) -> List[Dict[str, Any]]:
    """Retrieve all pending cases that have breached or are at imminent risk of breaching the statutory SLA."""
    conn = get_db_connection()
    cur = conn.cursor()
    now = now_ist()
    cutoff = now - timedelta(days=threshold_days)

    cur.execute("""
        SELECT id, application_no, applicant_name, mobile, block, village, submitted_at
        FROM applications
        WHERE status = 'PENDING' AND submitted_at < %s
        ORDER BY submitted_at ASC
        LIMIT 50
    """, (cutoff,))
    rows = cur.fetchall()
    cur.close()
    conn.close()

    out = []
    for r in rows:
        sub_at = r[6]
        if isinstance(sub_at, str):
            try:
                sub_at = datetime.fromisoformat(sub_at.replace(" ", "T"))
            except Exception:
                sub_at = None
        days_pending = (now - sub_at).days if (now and sub_at) else threshold_days
        out.append({
            "application_id": r[0],
            "application_no": r[1],
            "applicant_name": r[2],
            "mobile": r[3],
            "block": r[4],
            "village": r[5],
            "submitted_at": str(sub_at) if sub_at else None,
            "days_pending": days_pending,
            "overdue_days": days_pending - threshold_days,
            "statutory_deemed_approval_risk": True
        })
    return out
