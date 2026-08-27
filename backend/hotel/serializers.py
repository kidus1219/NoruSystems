from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from .models import Attendance, Department, Employee, Role, Shift, ShiftAssignment


class ModelCleanMixin:
    """Runs full_clean() during validation and maps the errors onto fields."""

    def validate(self, attrs):
        attrs = super().validate(attrs)
        instance = self.instance
        if instance is None:
            instance = self.Meta.model(**attrs)
        else:
            instance = self.Meta.model.objects.get(pk=instance.pk)
            for field, value in attrs.items():
                setattr(instance, field, value)
        try:
            instance.full_clean(exclude=self._excluded_from_clean())
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.message_dict)
        return attrs

    def _excluded_from_clean(self):
        # employee_code is blank until save() fills it in.
        return [f.name for f in self.Meta.model._meta.fields if f.name in {"employee_code"}]


class DepartmentSerializer(serializers.ModelSerializer):
    employee_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Department
        fields = ["id", "name", "code", "description", "is_active", "employee_count", "created_at"]


class RoleSerializer(ModelCleanMixin, serializers.ModelSerializer):
    department_name = serializers.CharField(source="department.name", read_only=True)
    employee_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Role
        fields = [
            "id", "title", "code", "department", "department_name", "base_hourly_rate",
            "description", "is_active", "employee_count",
        ]


class ShiftSerializer(ModelCleanMixin, serializers.ModelSerializer):
    duration_hours = serializers.FloatField(read_only=True)
    crosses_midnight = serializers.BooleanField(read_only=True)

    class Meta:
        model = Shift
        fields = [
            "id", "name", "code", "start_time", "end_time", "break_minutes",
            "duration_hours", "crosses_midnight", "is_active",
        ]


class EmployeeSerializer(ModelCleanMixin, serializers.ModelSerializer):
    full_name = serializers.CharField(read_only=True)
    department_name = serializers.CharField(source="department.name", read_only=True)
    role_title = serializers.CharField(source="role.title", read_only=True)
    manager_name = serializers.CharField(source="manager.full_name", read_only=True, default=None)
    effective_hourly_rate = serializers.DecimalField(
        max_digits=8, decimal_places=2, read_only=True
    )

    class Meta:
        model = Employee
        fields = [
            "id", "employee_code", "first_name", "last_name", "full_name", "email", "phone",
            "department", "department_name", "role", "role_title", "manager", "manager_name",
            "employment_type", "status", "hire_date", "termination_date",
            "hourly_rate", "effective_hourly_rate", "created_at",
        ]
        read_only_fields = ["employee_code"]


class EmployeeAssignmentSerializer(serializers.Serializer):
    """Body for POST /employees/{id}/assign/."""

    department = serializers.PrimaryKeyRelatedField(
        queryset=Department.objects.all(), required=False
    )
    role = serializers.PrimaryKeyRelatedField(queryset=Role.objects.all(), required=False)
    manager = serializers.PrimaryKeyRelatedField(
        queryset=Employee.objects.all(), required=False, allow_null=True
    )

    def validate(self, attrs):
        if not attrs:
            raise serializers.ValidationError("Provide at least one of: department, role, manager.")
        return attrs

    def save(self, **kwargs):
        employee = self.context["employee"]
        for field, value in self.validated_data.items():
            setattr(employee, field, value)
        try:
            employee.full_clean(exclude=["employee_code"])
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.message_dict)
        employee.save()
        return employee


class ShiftAssignmentSerializer(ModelCleanMixin, serializers.ModelSerializer):
    employee_name = serializers.CharField(source="employee.full_name", read_only=True)
    department_name = serializers.CharField(source="employee.department.name", read_only=True)
    shift_name = serializers.CharField(source="shift.name", read_only=True)
    start_time = serializers.TimeField(source="shift.start_time", read_only=True)
    end_time = serializers.TimeField(source="shift.end_time", read_only=True)
    attendance_status = serializers.CharField(source="attendance.status", read_only=True, default=None)

    class Meta:
        model = ShiftAssignment
        fields = [
            "id", "employee", "employee_name", "department_name", "shift", "shift_name",
            "start_time", "end_time", "date", "status", "notes", "attendance_status",
        ]


class BulkShiftAssignmentSerializer(serializers.Serializer):
    """One shift, several people, a range of dates."""

    employees = serializers.PrimaryKeyRelatedField(
        queryset=Employee.objects.all(), many=True, allow_empty=False
    )
    shift = serializers.PrimaryKeyRelatedField(queryset=Shift.objects.all())
    start_date = serializers.DateField()
    end_date = serializers.DateField()
    weekdays = serializers.ListField(
        child=serializers.IntegerField(min_value=0, max_value=6),
        required=False,
        help_text="Restrict to these weekdays (0=Monday). Defaults to every day in the range.",
    )
    notes = serializers.CharField(required=False, allow_blank=True, default="")

    def validate(self, attrs):
        if attrs["end_date"] < attrs["start_date"]:
            raise serializers.ValidationError({"end_date": "end_date cannot precede start_date."})
        if (attrs["end_date"] - attrs["start_date"]).days > 92:
            raise serializers.ValidationError({"end_date": "Roster at most one quarter at a time."})
        return attrs


class AttendanceSerializer(ModelCleanMixin, serializers.ModelSerializer):
    employee_name = serializers.CharField(source="employee.full_name", read_only=True)
    department_name = serializers.CharField(source="employee.department.name", read_only=True)
    shift_name = serializers.CharField(source="shift_assignment.shift.name", read_only=True, default=None)
    worked_hours = serializers.FloatField(read_only=True)
    overtime_minutes = serializers.IntegerField(read_only=True)

    class Meta:
        model = Attendance
        fields = [
            "id", "employee", "employee_name", "department_name", "shift_assignment", "shift_name",
            "date", "check_in", "check_out", "status", "notes",
            "worked_minutes", "worked_hours", "minutes_late", "overtime_minutes",
        ]
        read_only_fields = ["worked_minutes", "minutes_late"]


class ClockSerializer(serializers.Serializer):
    """Optional timestamp for check-in/check-out. Defaults to now."""

    timestamp = serializers.DateTimeField(required=False)
