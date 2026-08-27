"""Builders for the tests.

Hand-rolled rather than a factory library because the report tests assert
exact numbers, so the fixtures need to be obvious at a glance.
"""

from datetime import date, time, timedelta
from decimal import Decimal

from django.utils import timezone

from hotel.models import Attendance, Department, Employee, Role, Shift, ShiftAssignment


def make_department(name="Front Office", code="FO"):
    return Department.objects.create(name=name, code=code)


def make_role(department=None, title="Front Desk Agent", code="FO-AGT", rate="20.00"):
    return Role.objects.create(
        title=title, code=code, department=department, base_hourly_rate=Decimal(rate)
    )


def make_shift(name="Morning", code="AM", start=time(8, 0), end=time(16, 0), break_minutes=0):
    return Shift.objects.create(
        name=name, code=code, start_time=start, end_time=end, break_minutes=break_minutes
    )


def make_employee(department, role, first="Ada", last="Lovelace", **kwargs):
    kwargs.setdefault("email", f"{first}.{last}@example.com".lower())
    kwargs.setdefault("hire_date", timezone.localdate() - timedelta(days=365))
    return Employee.objects.create(
        first_name=first, last_name=last, department=department, role=role, **kwargs
    )


def make_assignment(employee, shift, on_date):
    return ShiftAssignment.objects.create(employee=employee, shift=shift, date=on_date)


def make_attendance(assignment, minutes_late=0, worked_minutes=480, status=None):
    """Clocks in relative to the scheduled start so lateness is exact."""
    check_in = assignment.scheduled_start + timedelta(minutes=minutes_late)
    return Attendance.objects.create(
        employee=assignment.employee,
        shift_assignment=assignment,
        date=assignment.date,
        check_in=check_in,
        check_out=check_in + timedelta(minutes=worked_minutes),
        status=status or Attendance.Status.PRESENT,
    )
