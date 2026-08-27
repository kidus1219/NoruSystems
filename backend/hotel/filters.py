"""Filters for the list endpoints."""

import django_filters as filters

from .models import Attendance, Employee, Role, ShiftAssignment


class EmployeeFilter(filters.FilterSet):
    hired_after = filters.DateFilter(field_name="hire_date", lookup_expr="gte")
    hired_before = filters.DateFilter(field_name="hire_date", lookup_expr="lte")

    class Meta:
        model = Employee
        fields = ["department", "role", "status", "employment_type", "manager"]


class RoleFilter(filters.FilterSet):
    class Meta:
        model = Role
        fields = ["department", "is_active"]


class ShiftAssignmentFilter(filters.FilterSet):
    date_from = filters.DateFilter(field_name="date", lookup_expr="gte")
    date_to = filters.DateFilter(field_name="date", lookup_expr="lte")
    department = filters.NumberFilter(field_name="employee__department_id")
    unattended = filters.BooleanFilter(
        field_name="attendance", lookup_expr="isnull", label="No attendance recorded yet"
    )

    class Meta:
        model = ShiftAssignment
        fields = ["employee", "shift", "date", "status"]


class AttendanceFilter(filters.FilterSet):
    date_from = filters.DateFilter(field_name="date", lookup_expr="gte")
    date_to = filters.DateFilter(field_name="date", lookup_expr="lte")
    department = filters.NumberFilter(field_name="employee__department_id")

    class Meta:
        model = Attendance
        fields = ["employee", "date", "status"]
