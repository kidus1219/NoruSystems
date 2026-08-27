from datetime import date, timedelta

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action, api_view
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from . import reports
from .filters import AttendanceFilter, EmployeeFilter, RoleFilter, ShiftAssignmentFilter
from .models import Attendance, Department, Employee, Role, Shift, ShiftAssignment
from .serializers import (
    AttendanceSerializer,
    BulkShiftAssignmentSerializer,
    ClockSerializer,
    DepartmentSerializer,
    EmployeeAssignmentSerializer,
    EmployeeSerializer,
    RoleSerializer,
    ShiftAssignmentSerializer,
    ShiftSerializer,
)

DEFAULT_REPORT_WINDOW_DAYS = 30


class DepartmentViewSet(viewsets.ModelViewSet):
    serializer_class = DepartmentSerializer
    filterset_fields = ["is_active"]
    search_fields = ["name", "code"]
    ordering_fields = ["name", "code", "employee_count"]

    def get_queryset(self):
        return Department.objects.annotate(
            employee_count=Count("employees", filter=Q(employees__status=Employee.Status.ACTIVE))
        )

    @extend_schema(responses=EmployeeSerializer(many=True))
    @action(detail=True, methods=["get"])
    def employees(self, request, pk=None):
        queryset = (
            self.get_object().employees.select_related("department", "role", "manager").all()
        )
        page = self.paginate_queryset(queryset)
        serializer = EmployeeSerializer(page if page is not None else queryset, many=True)
        return self.get_paginated_response(serializer.data) if page is not None else Response(serializer.data)


class RoleViewSet(viewsets.ModelViewSet):
    serializer_class = RoleSerializer
    filterset_class = RoleFilter
    search_fields = ["title", "code"]
    ordering_fields = ["title", "base_hourly_rate"]

    def get_queryset(self):
        return Role.objects.select_related("department").annotate(
            employee_count=Count("employees", filter=Q(employees__status=Employee.Status.ACTIVE))
        )


class ShiftViewSet(viewsets.ModelViewSet):
    queryset = Shift.objects.all()
    serializer_class = ShiftSerializer
    filterset_fields = ["is_active"]
    search_fields = ["name", "code"]
    ordering_fields = ["start_time", "name"]


class EmployeeViewSet(viewsets.ModelViewSet):
    serializer_class = EmployeeSerializer
    filterset_class = EmployeeFilter
    search_fields = ["first_name", "last_name", "email", "employee_code"]
    ordering_fields = ["last_name", "hire_date", "employee_code"]

    def get_queryset(self):
        return Employee.objects.select_related("department", "role", "manager")

    @extend_schema(request=EmployeeAssignmentSerializer, responses=EmployeeSerializer)
    @action(detail=True, methods=["post"])
    def assign(self, request, pk=None):
        """Move someone between departments, roles or managers."""
        employee = self.get_object()
        serializer = EmployeeAssignmentSerializer(
            data=request.data, context={"employee": employee, "request": request}
        )
        serializer.is_valid(raise_exception=True)
        employee = serializer.save()
        return Response(EmployeeSerializer(employee).data)

    @extend_schema(responses=ShiftAssignmentSerializer(many=True))
    @action(detail=True, methods=["get"], url_path="schedule")
    def schedule(self, request, pk=None):
        """One person's shifts over a period."""
        start, end = _report_period(request)
        queryset = (
            self.get_object()
            .shift_assignments.select_related("shift", "employee__department")
            .filter(date__range=(start, end))
        )
        return Response(ShiftAssignmentSerializer(queryset, many=True).data)


class ShiftAssignmentViewSet(viewsets.ModelViewSet):
    serializer_class = ShiftAssignmentSerializer
    filterset_class = ShiftAssignmentFilter
    search_fields = ["employee__first_name", "employee__last_name", "shift__name"]
    ordering_fields = ["date", "employee__last_name"]

    def get_queryset(self):
        return ShiftAssignment.objects.select_related(
            "employee", "employee__department", "shift", "attendance"
        )

    @extend_schema(request=BulkShiftAssignmentSerializer, responses=ShiftAssignmentSerializer(many=True))
    @action(detail=False, methods=["post"])
    def bulk(self, request):
        """Roster a shift across several people over a date range.

        Conflicts (duplicate, overlap, inactive employee) are skipped and listed
        in the response. Failing the whole batch over one clash would be worse.
        """
        serializer = BulkShiftAssignmentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        weekdays = set(data.get("weekdays") or range(7))
        created, skipped = [], []
        with transaction.atomic():
            for employee in data["employees"]:
                current = data["start_date"]
                while current <= data["end_date"]:
                    if current.weekday() in weekdays:
                        assignment = ShiftAssignment(
                            employee=employee,
                            shift=data["shift"],
                            date=current,
                            notes=data.get("notes", ""),
                        )
                        try:
                            assignment.full_clean()
                            assignment.save()
                            created.append(assignment)
                        except Exception as exc:  # noqa: BLE001 - goes back in the response
                            skipped.append(
                                {
                                    "employee": employee.full_name,
                                    "date": current,
                                    "reason": _first_error(exc),
                                }
                            )
                    current += timedelta(days=1)

        return Response(
            {
                "created_count": len(created),
                "skipped_count": len(skipped),
                "created": ShiftAssignmentSerializer(created, many=True).data,
                "skipped": skipped,
            },
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class AttendanceViewSet(viewsets.ModelViewSet):
    serializer_class = AttendanceSerializer
    filterset_class = AttendanceFilter
    search_fields = ["employee__first_name", "employee__last_name", "employee__employee_code"]
    ordering_fields = ["date", "minutes_late", "worked_minutes"]

    def get_queryset(self):
        return Attendance.objects.select_related(
            "employee", "employee__department", "shift_assignment__shift"
        )

    @extend_schema(request=ClockSerializer, responses=AttendanceSerializer)
    @action(detail=True, methods=["post"], url_path="check-in")
    def check_in(self, request, pk=None):
        return self._clock(request, "clock_in")

    @extend_schema(request=ClockSerializer, responses=AttendanceSerializer)
    @action(detail=True, methods=["post"], url_path="check-out")
    def check_out(self, request, pk=None):
        return self._clock(request, "clock_out")

    def _clock(self, request, method_name):
        # Rules live on the model, this just converts the exception type.
        attendance = self.get_object()
        try:
            getattr(attendance, method_name)(_clock_timestamp(request))
        except DjangoValidationError as exc:
            raise ValidationError(exc.message_dict)
        return Response(self.get_serializer(attendance).data)

    @extend_schema(
        parameters=[OpenApiParameter("date", OpenApiTypes.DATE), OpenApiParameter("department", int)],
        responses=AttendanceSerializer(many=True),
    )
    @action(detail=False, methods=["post"], url_path="open-day")
    def open_day(self, request):
        """Build the day's attendance rows off the roster.

        Safe to run twice, anything that already has a record is left alone.
        """
        day = _parse_date(request.data.get("date")) or timezone.localdate()
        assignments = ShiftAssignment.objects.filter(
            date=day, status=ShiftAssignment.Status.SCHEDULED, attendance__isnull=True
        ).select_related("employee", "shift")
        if department := request.data.get("department"):
            assignments = assignments.filter(employee__department_id=department)

        rows = [
            Attendance(
                employee=assignment.employee,
                shift_assignment=assignment,
                date=day,
                status=Attendance.Status.ABSENT,
            )
            for assignment in assignments
            # They might already have an unlinked row from covering something.
            if not Attendance.objects.filter(employee=assignment.employee, date=day).exists()
        ]
        Attendance.objects.bulk_create(rows)
        return Response(
            {"date": day, "created_count": len(rows)}, status=status.HTTP_201_CREATED
        )


@extend_schema(
    parameters=[
        OpenApiParameter("start", OpenApiTypes.DATE, description="Defaults to 30 days ago."),
        OpenApiParameter("end", OpenApiTypes.DATE, description="Defaults to today."),
        OpenApiParameter("department", int, required=False),
        OpenApiParameter("threshold_hours", float, required=False, description="Overtime report only."),
    ],
    responses=OpenApiTypes.OBJECT,
)
@api_view(["GET"])
def report_view(request, name):
    start, end = _report_period(request)
    department = request.query_params.get("department") or None

    if name == "department-summary":
        data = reports.department_summary(start, end)
    elif name == "coverage-gaps":
        data = reports.coverage_gaps(start, end, department_id=department)
    elif name == "employee-scorecard":
        data = reports.employee_scorecard(start, end, department_id=department)
    elif name == "overtime":
        threshold = float(
            request.query_params.get("threshold_hours")
            or reports.DEFAULT_WEEKLY_OVERTIME_THRESHOLD_HOURS
        )
        data = reports.overtime(start, end, threshold_hours=threshold)
    elif name == "dashboard":
        data = reports.dashboard(start, end)
    else:
        return Response({"detail": f"Unknown report '{name}'."}, status=status.HTTP_404_NOT_FOUND)

    payload = {"start": start, "end": end, "results": data} if isinstance(data, list) else data
    return Response(payload)


def _report_period(request):
    """?start and ?end, defaulting to the last 30 days."""
    end = _parse_date(request.query_params.get("end")) or timezone.localdate()
    start = _parse_date(request.query_params.get("start")) or end - timedelta(
        days=DEFAULT_REPORT_WINDOW_DAYS
    )
    if start > end:
        raise ValidationError({"start": "start must be on or before end."})
    return start, end


def _parse_date(value):
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        raise ValidationError({"date": f"'{value}' is not a valid ISO date (YYYY-MM-DD)."})


def _clock_timestamp(request):
    serializer = ClockSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    return serializer.validated_data.get("timestamp") or timezone.now()


def _first_error(exc):
    messages = getattr(exc, "messages", None)
    return messages[0] if messages else str(exc)
