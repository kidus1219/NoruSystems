"""Endpoint behaviour, including the errors bubbling up from the models."""

from datetime import time, timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from hotel.models import Attendance, Employee, ShiftAssignment
from hotel.tests.factories import (
    make_assignment,
    make_attendance,
    make_department,
    make_employee,
    make_role,
    make_shift,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def client():
    return APIClient()


@pytest.fixture
def org():
    front_office = make_department()
    housekeeping = make_department(name="Housekeeping", code="HK")
    return {
        "fo": front_office,
        "hk": housekeeping,
        "fo_role": make_role(front_office),
        "hk_role": make_role(housekeeping, title="Room Attendant", code="HK-ATT"),
        "shift": make_shift(),
    }


class TestEmployeeCrud:
    def test_create_generates_a_code_and_returns_denormalised_labels(self, client, org):
        response = client.post(
            "/api/employees/",
            {
                "first_name": "Ada", "last_name": "Lovelace", "email": "ada@example.com",
                "department": org["fo"].id, "role": org["fo_role"].id,
                "hire_date": str(timezone.localdate()),
            },
            format="json",
        )
        assert response.status_code == 201, response.data
        assert response.data["employee_code"] == "EMP-0001"
        assert response.data["department_name"] == "Front Office"
        assert response.data["full_name"] == "Ada Lovelace"

    def test_create_rejects_a_role_from_another_department(self, client, org):
        response = client.post(
            "/api/employees/",
            {
                "first_name": "Ada", "last_name": "Lovelace", "email": "ada@example.com",
                "department": org["fo"].id, "role": org["hk_role"].id,
                "hire_date": str(timezone.localdate()),
            },
            format="json",
        )
        assert response.status_code == 400
        assert "role" in response.data

    def test_list_filters_and_searches(self, client, org):
        make_employee(org["fo"], org["fo_role"], first="Ada", last="Lovelace")
        make_employee(org["hk"], org["hk_role"], first="Grace", last="Hopper")

        assert client.get(f"/api/employees/?department={org['fo'].id}").data["count"] == 1
        assert client.get("/api/employees/?search=hopper").data["count"] == 1
        assert client.get("/api/employees/").data["count"] == 2

    def test_update_and_delete(self, client, org):
        employee = make_employee(org["fo"], org["fo_role"])
        patch = client.patch(f"/api/employees/{employee.id}/", {"phone": "+251900000000"}, format="json")
        assert patch.status_code == 200
        assert patch.data["phone"] == "+251900000000"

        assert client.delete(f"/api/employees/{employee.id}/").status_code == 204
        assert not Employee.objects.filter(pk=employee.pk).exists()

    def test_department_with_staff_cannot_be_deleted(self, client, org):
        make_employee(org["fo"], org["fo_role"])
        response = client.delete(f"/api/departments/{org['fo'].id}/")
        assert response.status_code == 409
        assert "Employees" in response.data["detail"]

    def test_empty_department_can_be_deleted(self, client, org):
        spare = make_department(name="Spa", code="SPA")
        assert client.delete(f"/api/departments/{spare.id}/").status_code == 204


class TestAssignment:
    def test_assign_moves_department_and_role_together(self, client, org):
        employee = make_employee(org["fo"], org["fo_role"])
        response = client.post(
            f"/api/employees/{employee.id}/assign/",
            {"department": org["hk"].id, "role": org["hk_role"].id},
            format="json",
        )
        assert response.status_code == 200, response.data
        employee.refresh_from_db()
        assert (employee.department_id, employee.role_id) == (org["hk"].id, org["hk_role"].id)

    def test_assign_rejects_a_department_move_that_orphans_the_role(self, client, org):
        employee = make_employee(org["fo"], org["fo_role"])
        response = client.post(
            f"/api/employees/{employee.id}/assign/", {"department": org["hk"].id}, format="json"
        )
        assert response.status_code == 400
        assert "role" in response.data

    def test_assign_requires_at_least_one_field(self, client, org):
        employee = make_employee(org["fo"], org["fo_role"])
        assert client.post(f"/api/employees/{employee.id}/assign/", {}, format="json").status_code == 400


class TestShiftAssignmentApi:
    def test_create_and_reject_overlap(self, client, org):
        employee = make_employee(org["fo"], org["fo_role"])
        today = str(timezone.localdate())
        payload = {"employee": employee.id, "shift": org["shift"].id, "date": today}
        assert client.post("/api/shift-assignments/", payload, format="json").status_code == 201

        overlapping = make_shift(name="Mid", code="MID", start=time(14, 0), end=time(22, 0))
        response = client.post(
            "/api/shift-assignments/",
            {"employee": employee.id, "shift": overlapping.id, "date": today},
            format="json",
        )
        assert response.status_code == 400
        assert "shift" in response.data

    def test_bulk_rosters_a_week_and_reports_skipped_rows(self, client, org):
        ada = make_employee(org["fo"], org["fo_role"], first="Ada", last="Lovelace")
        grace = make_employee(org["fo"], org["fo_role"], first="Grace", last="Hopper")
        start = timezone.localdate()
        # Ada already has the middle day, so exactly one row must be skipped.
        make_assignment(ada, org["shift"], start + timedelta(days=2))

        response = client.post(
            "/api/shift-assignments/bulk/",
            {
                "employees": [ada.id, grace.id],
                "shift": org["shift"].id,
                "start_date": str(start),
                "end_date": str(start + timedelta(days=4)),
            },
            format="json",
        )
        assert response.status_code == 201, response.data
        assert response.data["created_count"] == 9
        assert response.data["skipped_count"] == 1
        assert response.data["skipped"][0]["employee"] == "Ada Lovelace"
        assert ShiftAssignment.objects.count() == 10

    def test_bulk_honours_the_weekday_filter(self, client, org):
        employee = make_employee(org["fo"], org["fo_role"])
        monday = timezone.localdate() - timedelta(days=timezone.localdate().weekday())
        response = client.post(
            "/api/shift-assignments/bulk/",
            {
                "employees": [employee.id], "shift": org["shift"].id,
                "start_date": str(monday), "end_date": str(monday + timedelta(days=13)),
                "weekdays": [0, 2],
            },
            format="json",
        )
        assert response.data["created_count"] == 4  # two Mondays and two Wednesdays

    def test_bulk_rejects_a_backwards_range(self, client, org):
        employee = make_employee(org["fo"], org["fo_role"])
        today = timezone.localdate()
        response = client.post(
            "/api/shift-assignments/bulk/",
            {
                "employees": [employee.id], "shift": org["shift"].id,
                "start_date": str(today), "end_date": str(today - timedelta(days=1)),
            },
            format="json",
        )
        assert response.status_code == 400


class TestAttendanceApi:
    @pytest.fixture
    def assignment(self, org):
        employee = make_employee(org["fo"], org["fo_role"])
        return make_assignment(employee, org["shift"], timezone.localdate())

    def test_check_in_late_then_check_out_derives_the_numbers(self, client, assignment):
        attendance = Attendance.objects.create(
            employee=assignment.employee, shift_assignment=assignment, date=assignment.date
        )
        check_in = assignment.scheduled_start + timedelta(minutes=25)

        response = client.post(
            f"/api/attendance/{attendance.id}/check-in/", {"timestamp": check_in.isoformat()},
            format="json",
        )
        assert response.status_code == 200, response.data
        assert response.data["minutes_late"] == 25
        assert response.data["status"] == "late"

        response = client.post(
            f"/api/attendance/{attendance.id}/check-out/",
            {"timestamp": (check_in + timedelta(hours=8)).isoformat()},
            format="json",
        )
        assert response.data["worked_hours"] == 8.0

    def test_checking_in_clears_a_provisional_absence(self, client, assignment):
        # open-day marks them absent until they show up. Clocking in must undo it.
        client.post("/api/attendance/open-day/", {"date": str(assignment.date)}, format="json")
        attendance = Attendance.objects.get(employee=assignment.employee, date=assignment.date)
        assert attendance.status == Attendance.Status.ABSENT

        check_in = assignment.scheduled_start + timedelta(minutes=2)
        client.post(
            f"/api/attendance/{attendance.id}/check-in/", {"timestamp": check_in.isoformat()},
            format="json",
        )
        response = client.post(
            f"/api/attendance/{attendance.id}/check-out/",
            {"timestamp": (check_in + timedelta(hours=8)).isoformat()},
            format="json",
        )
        assert response.data["status"] == "present"
        assert response.data["worked_hours"] == 8.0

    def test_double_check_in_is_rejected(self, client, assignment):
        attendance = make_attendance(assignment)
        assert client.post(f"/api/attendance/{attendance.id}/check-in/", {}, format="json").status_code == 400

    def test_check_out_before_check_in_is_rejected(self, client, assignment):
        attendance = Attendance.objects.create(
            employee=assignment.employee, shift_assignment=assignment, date=assignment.date
        )
        assert client.post(f"/api/attendance/{attendance.id}/check-out/", {}, format="json").status_code == 400

    def test_open_day_creates_rows_from_the_roster_and_is_idempotent(self, client, assignment):
        today = str(assignment.date)
        first = client.post("/api/attendance/open-day/", {"date": today}, format="json")
        assert first.status_code == 201
        assert first.data["created_count"] == 1

        second = client.post("/api/attendance/open-day/", {"date": today}, format="json")
        assert second.data["created_count"] == 0
        assert Attendance.objects.count() == 1

    def test_second_attendance_row_for_one_day_is_rejected(self, client, assignment):
        make_attendance(assignment)
        response = client.post(
            "/api/attendance/",
            {"employee": assignment.employee.id, "date": str(assignment.date), "status": "present"},
            format="json",
        )
        assert response.status_code == 400


class TestReportEndpoints:
    @pytest.fixture
    def data(self, org):
        employee = make_employee(org["fo"], org["fo_role"])
        make_attendance(make_assignment(employee, org["shift"], timezone.localdate()))
        return employee

    @pytest.mark.parametrize(
        "name", ["department-summary", "coverage-gaps", "employee-scorecard", "overtime", "dashboard"]
    )
    def test_every_report_responds(self, client, data, name):
        assert client.get(f"/api/reports/{name}/").status_code == 200

    def test_unknown_report_is_a_404(self, client):
        assert client.get("/api/reports/not-a-report/").status_code == 404

    def test_period_defaults_to_the_last_30_days(self, client, data):
        response = client.get("/api/reports/department-summary/")
        assert response.data["end"] == timezone.localdate()
        assert response.data["start"] == timezone.localdate() - timedelta(days=30)

    def test_backwards_period_is_rejected(self, client, data):
        today = timezone.localdate()
        response = client.get(
            f"/api/reports/department-summary/?start={today}&end={today - timedelta(days=5)}"
        )
        assert response.status_code == 400

    def test_malformed_date_is_rejected(self, client, data):
        assert client.get("/api/reports/dashboard/?start=last-tuesday").status_code == 400


class TestSchema:
    def test_openapi_schema_builds(self, client):
        response = client.get("/api/schema/")
        assert response.status_code == 200
