from __future__ import annotations

from .attendance import AttendanceService
from .people import PeopleService


class DashboardService:
    def __init__(self, people: PeopleService, attendance: AttendanceService):
        self.people, self.attendance = people, attendance

    def summary(self) -> dict:
        today = self.attendance.today()
        persons = self.people.all()
        total = len(persons)
        counts = self.attendance.counts_for_date(today)
        present = counts["present"] + counts["late"]
        absent = max(total - present - counts["excused"], 0)
        present_ids = self.attendance.present_ids_for_date(today)
        by_dept: dict[str, dict] = {}
        for p in persons:
            d = by_dept.setdefault(p["department"] or "Unassigned", {"department": p["department"] or "Unassigned", "total": 0, "present": 0})
            d["total"] += 1
            d["present"] += p["person_id"] in present_ids
        return {
            "date": today,
            "total_people": total,
            "students": sum(p["type"] == "student" for p in persons),
            "employees": sum(p["type"] == "employee" for p in persons),
            "faces_registered": sum(p["face_status"] == "registered" for p in persons),
            "faces_pending": sum(p["face_status"] == "pending" for p in persons),
            "present_today": present, "late_today": counts["late"], "excused_today": counts["excused"],
            "absent_today": absent,
            "attendance_rate": round(100 * present / total, 1) if total else 0.0,
            "recent": self.attendance.recent(10),
            "trend": self.attendance.trend(7),
            "by_department": sorted(by_dept.values(), key=lambda d: d["department"]),
        }
