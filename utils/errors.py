"""A friendly page for a server error or a missing page (Task 10, D8).

The person sees one calm sentence and a button back. Never a traceback, never an error
message. The full error is written to a file in the logs/ folder (git ignores it), with the
address, the method and the signed-in account's ID. No audit entry is written: the audit log
is for what people did, and an error is not that.
"""
import logging
import os
from logging.handlers import RotatingFileHandler

from flask import jsonify, render_template, request, session, url_for
from werkzeug.exceptions import HTTPException

import config

FETCH_HEADER = "X-Requested-With"
LOG_NAME = "errors.log"
TITLE = "Something went wrong"
LINE = ("Please go back and try again. If this keeps happening, tell the system "
        "administrator.")

# Used only if the error page itself cannot be drawn (for example the database is gone).
_PLAIN = (
    "<!doctype html><meta charset='utf-8'><title>" + TITLE + "</title>"
    "<body style='font-family:Arial,sans-serif;text-align:center;margin-top:15vh'>"
    "<h1>" + TITLE + "</h1><p>" + LINE + "</p></body>"
)

_logger = None


def error_logger():
    """The error logger, writing to <LOG_DIR>/errors.log. Made once per process."""
    global _logger
    folder = config.LOG_DIR
    if _logger is not None and getattr(_logger, "_ids_folder", None) == folder:
        return _logger
    logger = logging.getLogger("ids.errors")
    logger.setLevel(logging.ERROR)
    logger.propagate = False
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()
    try:
        os.makedirs(folder, exist_ok=True)
        handler = RotatingFileHandler(os.path.join(folder, LOG_NAME), maxBytes=1_000_000,
                                      backupCount=3, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
        logger.addHandler(handler)
    except OSError:
        pass  # a log that cannot be written must never turn one error into two
    logger._ids_folder = folder
    _logger = logger
    return logger


def _write(error, status):
    try:
        error_logger().error(
            "%s %s %s account=%s",
            status, request.method, request.path, session.get("user_id") or "-",
            exc_info=(type(error), error, error.__traceback__) if error is not None else None,
        )
    except Exception:
        pass


def _page(status):
    """The friendly page. Nothing about the error is passed to it."""
    if request.headers.get(FETCH_HEADER):
        return jsonify({"error": TITLE}), status
    signed_in = bool(session.get("user_id"))
    try:
        return render_template(
            "error.html", title=TITLE, line=LINE,
            home_url=url_for("auth.dashboard") if signed_in else url_for("auth.login"),
            home_label="Go to my dashboard" if signed_in else "Go to sign in",
            brand=config.SYSTEM_SHORT_NAME,
        ), status
    except Exception:
        return _PLAIN, status


def init_error_pages(app):
    """Register the 404 and 500 pages, and the catch-all for an error nobody handled."""

    def not_found(error):
        return _page(404)

    def server_error(error):
        original = getattr(error, "original_exception", None) or error
        _write(original, 500)
        return _page(500)

    def unhandled(error):
        if isinstance(error, HTTPException):
            return error  # 400, 403, 405 ... keep their own answers
        if app.debug:
            raise error  # with IDS_DEBUG=1 the developer wants the trace
        _write(error, 500)
        return _page(500)

    app.register_error_handler(404, not_found)
    app.register_error_handler(500, server_error)
    app.register_error_handler(Exception, unhandled)
