"""A short pause after repeated failed sign-ins (L41).

Five failures for the same username from the same address, inside five minutes,
close the sign-in form to that pair until the five minutes are over. Anyone else
is not affected, and a correct password clears the count. The count is kept in
memory only: it resets when the app restarts, and it holds no password.

A failure is counted whether or not the username exists, so the pause tells a
visitor nothing about which accounts are real.
"""
import threading
import time

MAX_FAILURES = 5
WINDOW_SECONDS = 300

THROTTLED_KEY = "throttled"
THROTTLED_MESSAGE = "Too many failed sign-ins. Please wait 5 minutes and try again."

_failures = {}
_lock = threading.Lock()


def _now():
    return time.time()


def _key(username, ip_address):
    return ((username or "").strip().lower(), ip_address or "")


def _recent(key, now):
    kept = [t for t in _failures.get(key, ()) if now - t < WINDOW_SECONDS]
    if kept:
        _failures[key] = kept
    else:
        _failures.pop(key, None)
    return kept


def is_throttled(username, ip_address):
    with _lock:
        return len(_recent(_key(username, ip_address), _now())) >= MAX_FAILURES


def record_failure(username, ip_address):
    with _lock:
        key = _key(username, ip_address)
        now = _now()
        _recent(key, now)
        _failures.setdefault(key, []).append(now)


def clear(username, ip_address):
    with _lock:
        _failures.pop(_key(username, ip_address), None)


def reset_all():
    with _lock:
        _failures.clear()
