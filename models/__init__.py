"""Data access, one module per entity.

Modules here own the SQL. Routes call these functions; routes do not open
connections or write queries themselves.

Import rule: always reach the connection helper as ``from database.connection
import get_db``, never ``from database import get_db`` -- database/schema.py
bootstraps through models.users, and going via the package would make that a
circular import.
"""
