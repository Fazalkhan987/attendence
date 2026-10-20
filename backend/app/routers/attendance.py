from typing import Optional

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel, Field

from ..deps import actor_of, csrf_guard, current_user, get_svc
from ..errors import AppError
from ..services import exporting
from ..services.attendance import AttendanceFilter

router = APIRouter(prefix="/api/attendance", tags=["attendance"], dependencies=[Depends(csrf_guard), Depends(current_user)])


class ManualIn(BaseModel):
    person_id: str = Field(max_length=64)
    status: str = "present"
    date: Optional[str] = None
    time: Optional[str] = None
    note: Optional[str] = Field(default=None, max_length=300)


class UpdateIn(BaseModel):
    status: Optional[str] = None
    time: Optional[str] = None
    note: Optional[str] = Field(default=None, max_length=300)


def _filter(date_from, date_to, q, status, person_id) -> AttendanceFilter:
    return AttendanceFilter(date_from, date_to, q, status, person_id)


@router.get("")
def list_attendance(date_from: Optional[str] = None, date_to: Optional[str] = None, q: Optional[str] = None,
                    status: Optional[str] = None, person_id: Optional[str] = None,
                    page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=200), svc=Depends(get_svc)):
    return svc.attendance.list(_filter(date_from, date_to, q, status, person_id), page, page_size)


@router.get("/export")
def export_attendance(format: str = "csv", date_from: Optional[str] = None, date_to: Optional[str] = None,
                      q: Optional[str] = None, status: Optional[str] = None, person_id: Optional[str] = None,
                      svc=Depends(get_svc)):
    rows = svc.attendance.export_rows(_filter(date_from, date_to, q, status, person_id))
    stem = f"attendance_{date_from or 'all'}_{date_to or 'all'}"
    if format == "csv":
        body, mt = exporting.to_csv(rows), "text/csv; charset=utf-8"
    elif format == "xlsx":
        body, mt = exporting.to_xlsx(rows), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    else:
        raise AppError(422, "invalid_format", "format must be csv or xlsx.")
    return Response(content=body, media_type=mt, headers={"Content-Disposition": f'attachment; filename="{stem}.{format}"'})


@router.post("", status_code=201)
def create_manual(body: ManualIn, user=Depends(current_user), svc=Depends(get_svc)):
    return svc.attendance.create_manual(body.person_id, body.status, body.date, body.time, body.note, actor_of(user))


@router.patch("/{record_id}")
def update_record(record_id: int, body: UpdateIn, user=Depends(current_user), svc=Depends(get_svc)):
    return svc.attendance.update(record_id, body.status, body.time, body.note, actor_of(user))


@router.delete("/{record_id}")
def delete_record(record_id: int, svc=Depends(get_svc)):
    svc.attendance.delete(record_id)
    return {"ok": True}
