import pytest

from app.errors import AppError, map_engine_error
from app.services.attendance import AttendanceFilter
from app.services.live import LiveSession
from face_engine import exceptions as fe
from fakes import make_frame
from helpers import enrolled, faces_png, jpg_of, make_services, person, png


def test_create_validate_duplicate_and_fields(tmp_path):
    svc, _ = make_services(tmp_path)
    p = person(svc, "E7", "  Grace Hopper ", type="employee", email="g@navy.mil", phone="+1 555-0100", notes="Admiral")
    assert p["full_name"] == "Grace Hopper" and p["type"] == "employee" and p["face_status"] == "pending"
    with pytest.raises(fe.DuplicatePersonError):
        person(svc, "E7", "Someone Else")
    assert map_engine_error(fe.DuplicatePersonError("x")).status == 409
    bad = [dict(full_name="A"), dict(type="alien"), dict(email="nope"), dict(phone="abc!"), dict(full_name=" "),
           dict(department="x" * 81), dict(person_id="bad id")]
    for patch in bad:
        data = {"person_id": "Z1", "full_name": "Valid Name", "type": "student"}
        data.update(patch)
        with pytest.raises((AppError, fe.ValidationError)):
            svc.people.create(data, "web:t")


def test_update_syncs_attendance_snapshot_and_delete_options(tmp_path):
    svc, _ = make_services(tmp_path)
    enrolled(svc, "S1", 1)
    svc.attendance.mark_from_face("S1", "Ada Lovelace", "CS", 0.6)
    upd = svc.people.update("S1", {"full_name": "Ada King", "department": "Math", "type": "student"}, "web:t")
    assert upd["department"] == "Math"
    assert svc.attendance.list(AttendanceFilter())["items"][0]["person_name"] == "Ada King"
    res = svc.people.delete("S1", "web:t", purge_attendance=False)
    assert res["face_samples_removed"] == 6 and res["attendance_records_removed"] == 0
    assert svc.attendance.list(AttendanceFilter())["total"] == 1             # history kept by default
    with pytest.raises(fe.PersonNotFoundError):
        svc.people.get("S1")
    enrolled(svc, "S2", 2, name="Bob Brown")
    svc.attendance.mark_from_face("S2", "Bob Brown", "CS", 0.6)
    assert svc.people.delete("S2", "web:t", purge_attendance=True)["attendance_records_removed"] == 1


def test_face_enrolment_flow_errors_and_duplicates(tmp_path):
    svc, _ = make_services(tmp_path)
    person(svc, "S1", "Ada Lovelace")
    with pytest.raises(AppError):
        svc.people.enroll("S1", [], "web:t")
    with pytest.raises(fe.InsufficientSamplesError) as e:                    # corrupt + blurry + no face => nothing saved
        svc.people.enroll("S1", [("bad.jpg", b"garbage"), ("blur.png", png(1, blur=True)), ("none.png", png([]))], "web:t")
    err = map_engine_error(e.value)
    assert err.status == 422 and any("not a decodable" in r for s in err.details["report"]["samples"] for r in s["reasons"])
    assert svc.people.get("S1")["face_status"] == "pending"
    out = svc.people.enroll("S1", faces_png(1), "web:t")
    assert out["person"]["face_status"] == "registered" and out["report"]["accepted"] == 6
    person(svc, "S2", "Ada Clone")
    with pytest.raises(fe.PossibleDuplicateIdentityError) as d:               # same face under another ID
        svc.people.enroll("S2", [(f"c{i}.png", png(1, seed=7000 + i)) for i in range(6)], "web:t")
    m = map_engine_error(d.value)
    assert m.status == 409 and m.details["candidates"][0]["person_id"] == "S1"
    svc.people.enroll("S2", [(f"c{i}.png", png(1, seed=7000 + i)) for i in range(6)], "web:t", allow_possible_duplicate=True)
    assert svc.people.clear_faces("S2", "web:t")["person"]["face_status"] == "pending"


def test_check_frame_feedback(tmp_path):
    svc, _ = make_services(tmp_path)
    ok = svc.people.check_frame(jpg_of(make_frame([1], seed=3)))
    assert ok["ok"] and ok["bbox"] and ok["width"] == 380
    bad = svc.people.check_frame(jpg_of(make_frame([1], brightness=10, seed=4)))
    assert not bad["ok"] and any("dark" in r for r in bad["reasons"])
    assert svc.people.check_frame(jpg_of(make_frame([], seed=5)))["reasons"] == ["no face detected"]
    with pytest.raises(AppError):
        svc.people.check_frame(b"nope")


def test_list_search_filter_pagination(tmp_path):
    svc, _ = make_services(tmp_path)
    for i, (n, t, d) in enumerate([("Ada", "student", "CS"), ("Bob", "employee", "HR"), ("Cy", "student", "CS")]):
        person(svc, f"P{i}", n + " Test", type=t, department=d)
    assert svc.people.list(q="bob")["total"] == 1 and svc.people.list(type="student")["total"] == 2
    assert svc.people.list(department="CS")["total"] == 2 and svc.people.list(face_status="registered")["total"] == 0
    assert len(svc.people.list(page=2, page_size=2)["items"]) == 1 and svc.people.departments() == ["CS", "HR"]


# ------------------------------------------------------------------- live
def _session(svc):
    return LiveSession(svc.engine, svc.lock, svc.attendance)


def test_live_recognises_then_marks_exactly_once(tmp_path):
    svc, _ = make_services(tmp_path)
    enrolled(svc, "S1", 1)
    live = _session(svc)
    first = live.process_bytes(jpg_of(make_frame([1], seed=100)))
    assert first["faces"][0]["status"] == "verifying" and first["events"] == []        # not enough votes yet
    assert svc.attendance.list(AttendanceFilter())["total"] == 0
    events = []
    for s in range(101, 110):
        r = live.process_bytes(jpg_of(make_frame([1], seed=s)))
        events += r["events"]
    face = r["faces"][0]
    assert face["status"] == "recognized" and face["person_id"] == "S1" and face["name"] == "Ada Lovelace"
    assert face["attendance"]["outcome"] == "created" and face["det_score"] == 0.9 and face["similarity"] > 0.45
    assert len(events) == 1 and events[0]["type"] == "attendance" and events[0]["outcome"] == "created"
    assert svc.attendance.list(AttendanceFilter())["total"] == 1


def test_live_second_session_reports_already_marked_without_duplicate(tmp_path):
    svc, _ = make_services(tmp_path)
    enrolled(svc, "S1", 1)
    for round_ in range(2):
        live, evs = _session(svc), []
        for s in range(8):
            evs += live.process(make_frame([1], seed=200 + round_ * 50 + s))["events"]
        assert evs[0]["outcome"] == ("created" if round_ == 0 else "already_marked")
    assert svc.attendance.list(AttendanceFilter())["total"] == 1


def test_live_unknown_and_low_quality_never_mark(tmp_path):
    svc, _ = make_services(tmp_path)
    enrolled(svc, "S1", 1)
    live = _session(svc)
    for s in range(10):
        r = live.process(make_frame([30], seed=300 + s))                        # a stranger
    assert r["faces"][0]["status"] == "unknown" and r["faces"][0]["person_id"] is None
    live2 = _session(svc)
    for s in range(10):
        r = live2.process(make_frame([1], blur=True, seed=400 + s))             # enrolled person, but blurry
    assert r["faces"][0]["status"] == "low_quality" and r["faces"][0]["message"]
    assert svc.attendance.list(AttendanceFilter())["total"] == 0


def test_live_multiple_faces_independent(tmp_path):
    svc, _ = make_services(tmp_path)
    enrolled(svc, "S1", 1)
    enrolled(svc, "S2", 2, name="Bob Brown")
    live = _session(svc)
    for s in range(9):
        r = live.process(make_frame([1, 30, 2], seed=500 + s))
    st = {f["bbox"][0]: (f["status"], f["person_id"]) for f in r["faces"]}
    assert sorted(st.values(), key=str) == sorted([("recognized", "S1"), ("unknown", None), ("recognized", "S2")], key=str)
    assert {x["id"] for x in svc.attendance.list(AttendanceFilter())["items"]} and svc.attendance.list(AttendanceFilter())["total"] == 2


def test_live_invalid_frames_raise_cleanly(tmp_path):
    svc, _ = make_services(tmp_path)
    live = _session(svc)
    with pytest.raises(fe.InvalidFrameError):
        live.process_bytes(b"not a jpeg")
    with pytest.raises(fe.InvalidFrameError):
        live.process_bytes(b"0" * (3 * 1024 * 1024 + 1))
    assert live.process(make_frame([]))["faces"] == []


def test_live_deleted_person_is_not_marked(tmp_path):
    svc, _ = make_services(tmp_path)
    enrolled(svc, "S1", 1)
    live = _session(svc)
    for s in range(3):
        live.process(make_frame([1], seed=600 + s))
    svc.people.delete("S1", "web:t")                                           # removed mid-session
    for s in range(6):
        live.process(make_frame([1], seed=610 + s))
    assert svc.attendance.list(AttendanceFilter())["total"] == 0


def test_dashboard_numbers(tmp_path):
    svc, _ = make_services(tmp_path, late_after="08:00")
    for i in range(4):
        person(svc, f"P{i}", f"Person {i}", department="CS" if i < 3 else "HR", type="employee" if i == 3 else "student")
    enrolled(svc, "P9", 9, name="Nine Nine")
    svc.attendance.mark_from_face("P0", "Person 0", "CS", .6)                  # 08:30 > 08:00 => late
    svc.attendance.create_manual("P1", "excused", None, None, None, "x")
    d = svc.dashboard.summary()
    assert d["total_people"] == 5 and d["present_today"] == 1 and d["late_today"] == 1 and d["excused_today"] == 1
    assert d["absent_today"] == 3 and d["faces_registered"] == 1 and d["faces_pending"] == 4 and d["employees"] == 1
    assert d["attendance_rate"] == 20.0 and len(d["trend"]) == 7 and d["recent"][0]["person_id"] in ("P0", "P1")
    assert {x["department"]: x["present"] for x in d["by_department"]}["CS"] == 1
