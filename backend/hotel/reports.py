"""Reports.

Each one takes a date range and hands back plain dicts, which keeps them
testable without going near HTTP. Aggregation stays in the database.
"""

from decimal import Decimal

from django.db.models import (
    Avg,
    Case,
    Count,
    DecimalField,
    ExpressionWrapper,
    F,
    IntegerField,
    OuterRef,
    Q,
    Subquery,
    Sum,
    Value,
    When,
    Window,
)
from django.db.models.functions import Coalesce, Rank, TruncWeek

from .models import Attendance, Department, Employee, Shift, ShiftAssignment

DEFAULT_WEEKLY_OVERTIME_THRESHOLD_HOURS = 40


def _rate(numerator, denominator):
    return round(100 * numerator / denominator, 1) if denominator else 0.0


def _hours(minutes):
    return round((minutes or 0) / 60, 2)


def department_summary(start, end):
    """Staffing and attendance per department.

    Headcount and roster counts come from subqueries. Joining employees and
    attendance together multiplies the rows and throws the counts off.
    """
    active_headcount = (
        Employee.objects.filter(department=OuterRef("pk"), status=Employee.Status.ACTIVE)
        .order_by()
        .values("department")
        .annotate(n=Count("pk"))
        .values("n")
    )
    scheduled = (
        ShiftAssignment.objects.filter(
            employee__department=OuterRef("pk"),
            status=ShiftAssignment.Status.SCHEDULED,
            date__range=(start, end),
        )
        .order_by()
        .values("employee__department")
        .annotate(n=Count("pk"))
        .values("n")
    )

    zero = Value(0, output_field=IntegerField())
    rows = (
        Department.objects.annotate(
            headcount=Coalesce(Subquery(active_headcount, output_field=IntegerField()), zero),
            shifts_scheduled=Coalesce(Subquery(scheduled, output_field=IntegerField()), zero),
        )
        .filter(Q(headcount__gt=0) | Q(shifts_scheduled__gt=0))
        .annotate(
            attendance_records=Count(
                "employees__attendance",
                filter=Q(employees__attendance__date__range=(start, end)),
                distinct=True,
            ),
            present_count=Count(
                "employees__attendance",
                filter=Q(
                    employees__attendance__date__range=(start, end),
                    employees__attendance__status__in=[
                        Attendance.Status.PRESENT,
                        Attendance.Status.LATE,
                    ],
                ),
                distinct=True,
            ),
            late_count=Count(
                "employees__attendance",
                filter=Q(
                    employees__attendance__date__range=(start, end),
                    employees__attendance__status=Attendance.Status.LATE,
                ),
                distinct=True,
            ),
            absent_count=Count(
                "employees__attendance",
                filter=Q(
                    employees__attendance__date__range=(start, end),
                    employees__attendance__status=Attendance.Status.ABSENT,
                ),
                distinct=True,
            ),
            minutes_worked=Coalesce(
                Sum(
                    "employees__attendance__worked_minutes",
                    filter=Q(employees__attendance__date__range=(start, end)),
                ),
                zero,
            ),
        )
        .order_by("name")
    )

    summary = []
    for dept in rows:
        summary.append(
            {
                "department_id": dept.id,
                "department": dept.name,
                "code": dept.code,
                "headcount": dept.headcount,
                "shifts_scheduled": dept.shifts_scheduled,
                "attendance_records": dept.attendance_records,
                "present_count": dept.present_count,
                "late_count": dept.late_count,
                "absent_count": dept.absent_count,
                "attendance_rate": _rate(dept.present_count, dept.shifts_scheduled),
                "punctuality_rate": _rate(dept.present_count - dept.late_count, dept.present_count),
                "hours_worked": _hours(dept.minutes_worked),
                "labour_cost": _department_labour_cost(dept.id, start, end),
            }
        )
    return summary


def _department_labour_cost(department_id, start, end):
    """Worked minutes priced at the employee's rate, or the role's if they have none."""
    cost_expression = ExpressionWrapper(
        F("worked_minutes")
        * Coalesce(F("employee__hourly_rate"), F("employee__role__base_hourly_rate"))
        / Value(60),
        output_field=DecimalField(max_digits=12, decimal_places=2),
    )
    total = Attendance.objects.filter(
        employee__department_id=department_id, date__range=(start, end)
    ).aggregate(
        total=Coalesce(
            Sum(cost_expression),
            Value(Decimal("0")),
            output_field=DecimalField(max_digits=12, decimal_places=2),
        )
    )["total"]
    return float(round(total, 2))


def coverage_gaps(start, end, department_id=None):
    """Shifts where fewer people turned up than were rostered.

    Counts from the assignment side rather than the attendance side, which is
    what makes a plain no-show (no attendance row at all) show up as a gap.
    """
    rostered = ShiftAssignment.objects.filter(
        status=ShiftAssignment.Status.SCHEDULED, date__range=(start, end)
    )
    if department_id:
        rostered = rostered.filter(employee__department_id=department_id)

    showed_up = Q(
        attendance__status__in=[Attendance.Status.PRESENT, Attendance.Status.LATE]
    )
    rows = (
        rostered.values(
            "date",
            "shift_id",
            shift_name=F("shift__name"),
            dept_id=F("employee__department__id"),
            dept_name=F("employee__department__name"),
        )
        .annotate(
            scheduled=Count("id", distinct=True),
            present=Count("id", filter=showed_up, distinct=True),
            late=Count("id", filter=Q(attendance__status=Attendance.Status.LATE), distinct=True),
            excused=Count(
                "id",
                filter=Q(attendance__status__in=[Attendance.Status.ON_LEAVE, Attendance.Status.HOLIDAY]),
                distinct=True,
            ),
        )
        .annotate(missing=F("scheduled") - F("present"))
        .filter(missing__gt=0)
        .order_by("date", "shift_name")
    )

    gaps = []
    for row in rows:
        gaps.append(
            {
                "date": row["date"],
                "shift_id": row["shift_id"],
                "shift": row["shift_name"],
                "department_id": row["dept_id"],
                "department": row["dept_name"],
                "scheduled": row["scheduled"],
                "present": row["present"],
                "late": row["late"],
                "excused_absences": row["excused"],
                "unexcused_no_shows": row["missing"] - row["excused"],
                "missing": row["missing"],
                "coverage_rate": _rate(row["present"], row["scheduled"]),
                "severity": _severity(row["present"], row["scheduled"]),
            }
        )
    return gaps


def _severity(present, scheduled):
    coverage = present / scheduled if scheduled else 1
    if coverage == 0:
        return "critical"
    if coverage < 0.5:
        return "high"
    if coverage < 0.8:
        return "medium"
    return "low"


def employee_scorecard(start, end, department_id=None, limit=None):
    """Attendance per person, ranked against the rest of their department."""
    employees = Employee.objects.select_related("department", "role")
    if department_id:
        employees = employees.filter(department_id=department_id)

    in_range = Q(attendance__date__range=(start, end))
    zero = Value(0, output_field=IntegerField())

    # Subquery, not a join. Bringing in shift_assignments alongside attendance
    # gives a cross product, and Sum/Avg can't be fixed up with distinct=True
    # the way Count can.
    scheduled_count = (
        ShiftAssignment.objects.filter(
            employee=OuterRef("pk"),
            date__range=(start, end),
            status=ShiftAssignment.Status.SCHEDULED,
        )
        .order_by()
        .values("employee")
        .annotate(n=Count("pk"))
        .values("n")
    )

    rows = (
        employees.annotate(
            shifts_scheduled=Coalesce(
                Subquery(scheduled_count, output_field=IntegerField()), zero
            ),
            days_present=Count(
                "attendance",
                filter=in_range
                & Q(attendance__status__in=[Attendance.Status.PRESENT, Attendance.Status.LATE]),
                distinct=True,
            ),
            days_late=Count(
                "attendance",
                filter=in_range & Q(attendance__status=Attendance.Status.LATE),
                distinct=True,
            ),
            days_absent=Count(
                "attendance",
                filter=in_range & Q(attendance__status=Attendance.Status.ABSENT),
                distinct=True,
            ),
            minutes_worked=Coalesce(Sum("attendance__worked_minutes", filter=in_range), zero),
            avg_minutes_late=Coalesce(
                Avg(
                    Case(
                        When(
                            attendance__status__in=[Attendance.Status.PRESENT, Attendance.Status.LATE],
                            then=F("attendance__minutes_late"),
                        ),
                        output_field=IntegerField(),
                    ),
                    filter=in_range,
                ),
                Value(0.0),
                output_field=DecimalField(max_digits=8, decimal_places=2),
            ),
        )
        .filter(Q(shifts_scheduled__gt=0) | Q(days_present__gt=0))
        # Rostered but not covered, whether that's an absent row or no row.
        # Sorts ahead of lateness: a missing person costs a whole shift.
        .annotate(no_shows=F("shifts_scheduled") - F("days_present"))
        .annotate(
            department_rank=Window(
                expression=Rank(),
                partition_by=[F("department_id")],
                order_by=[F("no_shows").asc(), F("days_late").asc(), F("days_present").desc()],
            )
        )
        .order_by("department__name", "department_rank")
    )
    if limit:
        rows = rows[:limit]

    return [
        {
            "employee_id": e.id,
            "employee_code": e.employee_code,
            "name": e.full_name,
            "department": e.department.name,
            "role": e.role.title,
            "shifts_scheduled": e.shifts_scheduled,
            "days_present": e.days_present,
            "days_late": e.days_late,
            "days_absent": e.days_absent,
            "no_shows": max(e.no_shows, 0),
            "hours_worked": _hours(e.minutes_worked),
            "avg_minutes_late": float(round(e.avg_minutes_late, 1)),
            "attendance_rate": _rate(e.days_present, e.shifts_scheduled),
            "department_rank": e.department_rank,
        }
        for e in rows
    ]


def overtime(start, end, threshold_hours=DEFAULT_WEEKLY_OVERTIME_THRESHOLD_HOURS):
    """Anyone over the weekly hour threshold, broken down by week."""
    threshold_minutes = int(threshold_hours * 60)
    rows = (
        Attendance.objects.filter(date__range=(start, end), worked_minutes__gt=0)
        .annotate(week=TruncWeek("date"))
        .values(
            "week",
            "employee_id",
            employee_code=F("employee__employee_code"),
            first_name=F("employee__first_name"),
            last_name=F("employee__last_name"),
            department=F("employee__department__name"),
        )
        .annotate(minutes_worked=Sum("worked_minutes"), days_worked=Count("id", distinct=True))
        .filter(minutes_worked__gt=threshold_minutes)
        .order_by("-minutes_worked")
    )
    return [
        {
            "week_starting": row["week"],
            "employee_id": row["employee_id"],
            "employee_code": row["employee_code"],
            "name": f"{row['first_name']} {row['last_name']}",
            "department": row["department"],
            "days_worked": row["days_worked"],
            "hours_worked": _hours(row["minutes_worked"]),
            "overtime_hours": _hours(row["minutes_worked"] - threshold_minutes),
            "threshold_hours": threshold_hours,
        }
        for row in rows
    ]


def dashboard(start, end):
    """Totals for the overview screen, plus the daily series for the chart."""
    totals = Attendance.objects.filter(date__range=(start, end)).aggregate(
        present=Count("id", filter=Q(status__in=[Attendance.Status.PRESENT, Attendance.Status.LATE])),
        late=Count("id", filter=Q(status=Attendance.Status.LATE)),
        absent=Count("id", filter=Q(status=Attendance.Status.ABSENT)),
        minutes=Coalesce(Sum("worked_minutes"), Value(0, output_field=IntegerField())),
    )
    scheduled = ShiftAssignment.objects.filter(
        date__range=(start, end), status=ShiftAssignment.Status.SCHEDULED
    ).count()
    daily = (
        Attendance.objects.filter(date__range=(start, end))
        .values("date")
        .annotate(
            present=Count("id", filter=Q(status__in=[Attendance.Status.PRESENT, Attendance.Status.LATE])),
            late=Count("id", filter=Q(status=Attendance.Status.LATE)),
            absent=Count("id", filter=Q(status=Attendance.Status.ABSENT)),
        )
        .order_by("date")
    )
    return {
        "period": {"start": start, "end": end},
        "total_employees": Employee.objects.filter(status=Employee.Status.ACTIVE).count(),
        "departments": Department.objects.filter(is_active=True).count(),
        "shifts": Shift.objects.filter(is_active=True).count(),
        "shifts_scheduled": scheduled,
        "present_count": totals["present"],
        "late_count": totals["late"],
        "absent_count": totals["absent"],
        "hours_worked": _hours(totals["minutes"]),
        "attendance_rate": _rate(totals["present"], scheduled),
        "open_gaps": len(coverage_gaps(start, end)),
        "daily_attendance": list(daily),
    }
