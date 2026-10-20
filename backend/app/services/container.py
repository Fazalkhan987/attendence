from __future__ import annotations

import threading

from ..config import Settings
from ..db import AppDatabase
from .attendance import AttendanceService
from .auth import AuthService
from .dashboard import DashboardService
from .people import PeopleService


class Services:
    """Wires every service once at start-up (a very small dependency-injection container)."""

    def __init__(self, settings: Settings, engine, clock=None):
        self.settings, self.engine = settings, engine
        self.lock = threading.RLock()            # serialises engine use (gallery rebuilds + shared ONNX sessions)
        self.db = AppDatabase(settings.app_db_path)
        self.auth = AuthService(self.db, settings)
        self.attendance = AttendanceService(self.db, settings, lambda pid: self.people.lookup(pid), clock)
        self.people = PeopleService(engine, self.lock, self.attendance)
        self.dashboard = DashboardService(self.people, self.attendance)
        if settings.admin_username and settings.admin_password and not self.auth.has_admins():
            self.auth.create_admin(settings.admin_username, settings.admin_password)

    def close(self) -> None:
        self.db.close()
        self.engine.close()
