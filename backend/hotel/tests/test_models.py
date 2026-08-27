"""Model rules: constraints and clean()."""

from datetime import time, timedelta

import pytest
from django.core.exceptions import ValidationError
from django.db.utils import IntegrityError
from django.utils import timezone

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


class TestShift:
    def test_day_shift_duration_subtracts_break(self):
        shift = make_shift(start=time(8, 0), end=time(16, 0), break_minutes=30)
        assert shift.crosses_midnight is False
        assert shift.duration_minutes == 450

    def test_overnight_shift_does_not_produce_negative_duration(self):
        shift = make_shift(name="Night", code="N", start=time(22, 0), end=time(6, 0), break_minutes=45)
        assert shift.crosses_midnight is True
        assert shift.duration_minutes == 8 * 60 - 45

    def test_overnight_shift_end_datetime_rolls_to_next_day(self):
        shift = make_shift(name="Night", code="N", start=time(22, 0), end=time(6, 0))
        day = timezone.localdate()
        assert shift.end_datetime_for(day).date() == day + timedelta(days=1)

    def test_break_cannot_consume_whole_shift(self):
        shift = make_shift(start=time(8, 0), end=time(9, 0), break_minutes=60)
        with pytest.raises(ValidationError):
            shift.full_clean()


class TestEmployee:
    def test_employee_code_is_generated_sequentially(self):
        department = make_department()
        role = make_role(department)
        first = make_employee(department, role, first="Ada", last="Lovelace")
        second = make_employee(department, role, first="Grace", last="Hopper")
        assert (first.employee_code, second.employee_code) == ("EMP-0001", "EMP-0002")

    def test_department_scoped_role_must_match_the_employees_department(self):
        front_office = make_department()
        housekeeping = make_department(name="Housekeeping", code="HK")
        hk_role = make_role(housekeeping, title="Room Attendant", code="HK-ATT")
        employee = make_employee(front_office, hk_role)
        with pytest.raises(ValidationError) as exc:
            employee.full_clean(exclude=["employee_code"])
        assert "role" in exc.value.message_dict

    def test_org_wide_role_is_accepted_in_any_department(self):
        department = make_department()
        gm_role = make_role(None, title="General Manager", code="GM")
        employee = make_employee(department, gm_role)
        employee.full_clean(exclude=["employee_code"])  # must not raise

    def test_effective_rate_prefers_the_personal_override(self):
        department = make_department()
        role = make_role(department, rate="20.00")
        employee = make_employee(department, role)
        assert employee.effective_hourly_rate == role.base_hourly_rate
        employee.hourly_rate = 26
        assert employee.effective_hourly_rate == 26


class TestShiftAssignment:
    @pytest.fixture
    def setup(self):
        department = make_department()
        role = make_role(department)
        return department, make_employee(department, role)

    def test_same_shift_twice_on_one_day_is_rejected(self, setup):
        _, employee = setup
        shift = make_shift()
        today = timezone.localdate()
        make_assignment(employee, shift, today)
        with pytest.raises(IntegrityError):
            ShiftAssignment.objects.create(employee=employee, shift=shift, date=today)

    def test_overlapping_shifts_on_the_same_day_are_rejected(self, setup):
        _, employee = setup
        morning = make_shift(start=time(8, 0), end=time(16, 0))
        overlapping = make_shift(name="Mid", code="MID", start=time(14, 0), end=time(22, 0))
        today = timezone.localdate()
        make_assignment(employee, morning, today)
        with pytest.raises(ValidationError):
            ShiftAssignment(employee=employee, shift=overlapping, date=today).full_clean()

    def test_overnight_shift_blocks_next_mornings_shift(self, setup):
        # The one a per-day uniqueness check would let through.
        _, employee = setup
        night = make_shift(name="Night", code="N", start=time(22, 0), end=time(6, 0))
        morning = make_shift(start=time(5, 0), end=time(13, 0))
        today = timezone.localdate()
        make_assignment(employee, night, today)
        with pytest.raises(ValidationError):
            ShiftAssignment(employee=employee, shift=morning, date=today + timedelta(days=1)).full_clean()

    def test_non_overlapping_shift_next_day_is_allowed(self, setup):
        _, employee = setup
        night = make_shift(name="Night", code="N", start=time(22, 0), end=time(6, 0))
        afternoon = make_shift(name="PM", code="PM", start=time(14, 0), end=time(22, 0))
        today = timezone.localdate()
        make_assignment(employee, night, today)
        ShiftAssignment(employee=employee, shift=afternoon, date=today + timedelta(days=1)).full_clean()

    def test_terminated_employee_cannot_be_scheduled(self, setup):
        _, employee = setup
        employee.status = Employee.Status.TERMINATED
        employee.save()
        with pytest.raises(ValidationError):
            ShiftAssignment(employee=employee, shift=make_shift(), date=timezone.localdate()).full_clean()


class TestAttendance:
    @pytest.fixture
    def assignment(self):
        department = make_department()
        employee = make_employee(department, make_role(department))
        return make_assignment(employee, make_shift(break_minutes=30), timezone.localdate())

    def test_worked_minutes_and_lateness_are_derived_on_save(self, assignment):
        attendance = make_attendance(assignment, minutes_late=20, worked_minutes=480)
        assert attendance.minutes_late == 20
        assert attendance.worked_minutes == 480 - 30  # the shift's unpaid break
        assert attendance.status == Attendance.Status.LATE

    def test_arriving_within_the_grace_period_is_still_present(self, assignment):
        attendance = make_attendance(assignment, minutes_late=Attendance.LATE_GRACE_MINUTES)
        assert attendance.status == Attendance.Status.PRESENT

    def test_arriving_early_never_produces_negative_lateness(self, assignment):
        attendance = make_attendance(assignment, minutes_late=-15)
        assert attendance.minutes_late == 0

    def test_absence_records_no_worked_time(self, assignment):
        attendance = Attendance.objects.create(
            employee=assignment.employee,
            shift_assignment=assignment,
            date=assignment.date,
            status=Attendance.Status.ABSENT,
        )
        assert (attendance.worked_minutes, attendance.minutes_late) == (0, 0)

    def test_check_out_before_check_in_is_rejected(self, assignment):
        attendance = Attendance(
            employee=assignment.employee,
            shift_assignment=assignment,
            date=assignment.date,
            check_in=assignment.scheduled_start,
            check_out=assignment.scheduled_start - timedelta(hours=1),
        )
        with pytest.raises(ValidationError):
            attendance.full_clean()

    def test_attendance_cannot_reference_another_employees_shift(self, assignment):
        other = make_employee(
            assignment.employee.department, assignment.employee.role, first="Grace", last="Hopper"
        )
        attendance = Attendance(
            employee=other, shift_assignment=assignment, date=assignment.date
        )
        with pytest.raises(ValidationError):
            attendance.full_clean()

    def test_one_attendance_row_per_employee_per_day(self, assignment):
        make_attendance(assignment)
        with pytest.raises(IntegrityError):
            Attendance.objects.create(employee=assignment.employee, date=assignment.date)

    def test_unlinked_attendance_has_no_lateness(self, assignment):
        # Cover shift, so there is no scheduled start to be late against.
        other = make_employee(
            assignment.employee.department, assignment.employee.role, first="Grace", last="Hopper"
        )
        attendance = Attendance.objects.create(
            employee=other,
            date=assignment.date,
            check_in=assignment.scheduled_start + timedelta(hours=3),
            check_out=assignment.scheduled_start + timedelta(hours=7),
        )
        assert attendance.minutes_late == 0
        assert attendance.worked_minutes == 240
