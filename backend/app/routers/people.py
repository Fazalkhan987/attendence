from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from pydantic import BaseModel, Field

from ..deps import actor_of, csrf_guard, current_user, get_svc, read_upload
from ..errors import AppError

router = APIRouter(prefix="/api", tags=["people"], dependencies=[Depends(csrf_guard), Depends(current_user)])


class PersonIn(BaseModel):
    person_id: Optional[str] = Field(default=None, max_length=64)
    full_name: str = Field(max_length=120)
    type: str = "student"
    department: Optional[str] = Field(default=None, max_length=80)
    class_name: Optional[str] = Field(default=None, max_length=80)
    email: Optional[str] = Field(default=None, max_length=254)
    phone: Optional[str] = Field(default=None, max_length=32)
    notes: Optional[str] = Field(default=None, max_length=500)


@router.get("/people")
def list_people(q: Optional[str] = None, type: Optional[str] = None, department: Optional[str] = None,
                face_status: Optional[str] = None, page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
                svc=Depends(get_svc)):
    return svc.people.list(q, type, department, face_status, page, page_size)


@router.get("/departments")
def departments(svc=Depends(get_svc)):
    return {"items": svc.people.departments()}


@router.post("/people", status_code=201)
def create_person(body: PersonIn, user=Depends(current_user), svc=Depends(get_svc)):
    return svc.people.create(body.model_dump(), actor_of(user))


@router.get("/people/{person_id}")
def get_person(person_id: str, svc=Depends(get_svc)):
    return svc.people.get(person_id)


@router.put("/people/{person_id}")
def update_person(person_id: str, body: PersonIn, user=Depends(current_user), svc=Depends(get_svc)):
    return svc.people.update(person_id, body.model_dump(), actor_of(user))


@router.delete("/people/{person_id}")
def delete_person(person_id: str, purge_attendance: bool = False, user=Depends(current_user), svc=Depends(get_svc)):
    return svc.people.delete(person_id, actor_of(user), purge_attendance)


@router.post("/people/{person_id}/faces")
def enroll_faces(person_id: str, files: List[UploadFile] = File(...), allow_possible_duplicate: bool = Form(False),
                 user=Depends(current_user), svc=Depends(get_svc)):
    if len(files) > svc.settings.max_files_per_upload:
        raise AppError(413, "too_many_files", f"At most {svc.settings.max_files_per_upload} images per upload.")
    data = [(f.filename or "", read_upload(f, svc.settings.max_upload_mb)) for f in files]
    return svc.people.enroll(person_id, data, actor_of(user), allow_possible_duplicate)


@router.delete("/people/{person_id}/faces")
def clear_faces(person_id: str, user=Depends(current_user), svc=Depends(get_svc)):
    return svc.people.clear_faces(person_id, actor_of(user))


@router.post("/enrollment/check")
def check_frame(file: UploadFile = File(...), svc=Depends(get_svc)):
    return svc.people.check_frame(read_upload(file, svc.settings.max_upload_mb))
