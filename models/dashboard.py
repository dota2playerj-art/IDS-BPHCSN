"""Aggregate counts for the dashboard stat cards.

NOTE: carried over verbatim from the pre-split app.py and currently unused -- no
route calls it, and its resident count filters on role = 'student', a value the
schema.sql CHECK constraint does not permit, so it can only ever return 0. Left
as-is because this session's restructuring is explicitly behaviour-preserving;
fixing the query belongs to the Priority 6 dashboard work.
"""
from database.connection import get_db


def get_dashboard_metrics():
    conn = get_db()
    resident_count = conn.execute("SELECT COUNT(*) AS count FROM users WHERE role = 'student'").fetchone()["count"]
    consultation_count = conn.execute("SELECT COUNT(*) AS count FROM consultations").fetchone()["count"]
    conn.close()

    return {
        "resident_count": resident_count,
        "consultation_count": consultation_count,
    }
