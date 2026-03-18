"""Session service — thin re-export of SessionStore for DI consistency."""

from backend.app.database.session_store import SessionStore

__all__ = ["SessionStore"]
