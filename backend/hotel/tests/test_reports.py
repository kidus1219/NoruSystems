"""Report numbers, checked against a fixture small enough to work out by hand.

The totals are also recomputed in Python and compared. That is what catches
the joins fanning out.
"""

from datetime import time, timedelta

import pytest
from django.utils import timezone

from hotel import reports
from hotel.models import Attendance, ShiftAssignment
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
def scenario():
    """Five days in Front Office, worked out in advance.

    Ada:   5 rostered, 5 worked, one of them 30 min late
    Grace: 5 rostered, 3 worked, 1 marked absent, 1 with no row at all
    """
    department = make_department()
    role = make_role(department, rate="20.00")
    shift = make_shift(start=time(8, 0), end=time(16, 0))  # 8h, no break

    ada = make_employee(department, role, first="Ada", last="Lovelace")
    grace = make_employee(department, role, first="Grace", last="Hopper", hourly_rate=30)

    end = timezone.localdate()
    days = [end - timedelta(days=offset) for offset in range(4, -1, -1)]

    for index, day in enumerate(days):
        make_attendance(make_assignment(ada, shift, day), minutes_late=30 if index == 0 else 0)

    for index, day in enumerate(days):
        assignment = make_assignment(grace, shift, day)
        if index == 3:
            Attendance.objects.create(
                employee=grace,
                shift_assignment=assignment,
                date=day,
                status=Attendance.Status.ABSENT,
            )
        elif index != 4:  # index 4 is the silent no-show: no attendance row
            make_attendance(assignment)

    return {"department": department, "ada": ada, "grace": grace, "shift": shift,
            "start": days[0], "end": days[-1]}


class TestDepartmentSummary:
    def test_counts_and_rates(self, scenario):
        row = reports.department_summary(scenario["start"], scenario["end"])[0]
        assert row["department"] == "Front Office"
        assert row["headcount"] == 2
        assert row["shifts_scheduled"] == 10
        assert row["present_count"] == 8       # 5 Ada + 3 Grace
        assert row["late_count"] == 1
        assert row["absent_count"] == 1
        assert row["attendance_rate"] == 80.0  # 8 of 10 rostered slots covered
        assert row["punctuality_rate"] == 87.5  # 7 of the 8 who showed were on time

    def test_hours_match_a_plain_python_sum(self, scenario):
        row = reports.department_summary(scenario["start"], scenario["end"])[0]
        expected = sum(
            a.worked_minutes
            for a in Attendance.objects.filter(date__range=(scenario["start"], scenario["end"]))
        )
        assert row["hours_worked"] == round(expected / 60, 2) == 64.0

    def test_labour_cost_uses_the_personal_rate_when_set(self, scenario):
        row = reports.department_summary(scenario["start"], scenario["end"])[0]
        # Ada: 5 x 8h @ 20 (role base) = 800; Grace: 3 x 8h @ 30 (override) = 720
        assert row["labour_cost"] == 1520.0

    def test_headcount_is_not_inflated_by_the_attendance_join(self, scenario):
        # Regression: the employee/attendance join used to multiply this.
        row = reports.department_summary(scenario["start"], scenario["end"])[0]
        assert row["headcount"] == 2


class TestCoverageGaps:
    def test_finds_the_absence_and_the_silent_no_show(self, scenario):
        gaps = reports.coverage_gaps(scenario["start"], scenario["end"])
        assert len(gaps) == 2
        assert {gap["missing"] for gap in gaps} == {1}
        assert {gap["scheduled"] for gap in gaps} == {2}
        assert all(gap["present"] == 1 for gap in gaps)
        assert all(gap["coverage_rate"] == 50.0 for gap in gaps)

    def test_a_no_show_with_no_attendance_row_is_still_counted(self, scenario):
        """No attendance row at all, rather than one marked absent."""
        no_show_day = scenario["end"]
        assert not Attendance.objects.filter(
            employee=scenario["grace"], date=no_show_day
        ).exists()
        gap = next(g for g in reports.coverage_gaps(scenario["start"], scenario["end"])
                   if g["date"] == no_show_day)
        assert gap["unexcused_no_shows"] == 1
        assert gap["excused_absences"] == 0

    def test_fully_covered_days_are_omitted(self, scenario):
        gaps = reports.coverage_gaps(scenario["start"], scenario["end"])
        covered_days = {scenario["start"] + timedelta(days=offset) for offset in (0, 1, 2)}
        assert not covered_days & {gap["date"] for gap in gaps}

    def test_department_filter_applies(self, scenario):
        other = make_department(name="Kitchen", code="KIT")
        assert reports.coverage_gaps(scenario["start"], scenario["end"], department_id=other.id) == []

    def test_cancelled_shifts_are_not_gaps(self, scenario):
        ShiftAssignment.objects.filter(
            employee=scenario["grace"], date=scenario["end"]
        ).update(status=ShiftAssignment.Status.CANCELLED)
        gaps = reports.coverage_gaps(scenario["start"], scenario["end"])
        assert scenario["end"] not in {gap["date"] for gap in gaps}


class TestEmployeeScorecard:
    def test_per_employee_numbers(self, scenario):
        rows = {row["name"]: row for row in
                reports.employee_scorecard(scenario["start"], scenario["end"])}
        ada, grace = rows["Ada Lovelace"], rows["Grace Hopper"]

        assert (ada["shifts_scheduled"], ada["days_present"], ada["days_late"]) == (5, 5, 1)
        assert ada["no_shows"] == 0
        assert ada["hours_worked"] == 40.0
        assert ada["avg_minutes_late"] == 6.0  # 30 minutes spread over 5 attended days

        assert (grace["shifts_scheduled"], grace["days_present"], grace["days_absent"]) == (5, 3, 1)
        assert grace["no_shows"] == 2  # the explicit absence and the silent one
        assert grace["hours_worked"] == 24.0

    def test_hours_are_not_multiplied_by_the_roster_join(self, scenario):
        # Regression: Sum used to come back multiplied by shifts_scheduled.
        rows = reports.employee_scorecard(scenario["start"], scenario["end"])
        for row in rows:
            expected = sum(
                a.worked_minutes
                for a in Attendance.objects.filter(
                    employee_id=row["employee_id"], date__range=(scenario["start"], scenario["end"])
                )
            )
            assert row["hours_worked"] == round(expected / 60, 2)

    def test_ranking_orders_the_most_reliable_first(self, scenario):
        rows = reports.employee_scorecard(scenario["start"], scenario["end"])
        assert [row["name"] for row in rows] == ["Ada Lovelace", "Grace Hopper"]
        assert [row["department_rank"] for row in rows] == [1, 2]


class TestOvertime:
    def test_below_threshold_returns_nothing(self, scenario):
        assert reports.overtime(scenario["start"], scenario["end"], threshold_hours=40) == []

    def test_only_weeks_over_the_threshold_come_back(self, scenario):
        rows = reports.overtime(scenario["start"], scenario["end"], threshold_hours=20)
        assert rows  # the five-day block always puts at least one week over 20h
        for row in rows:
            assert row["hours_worked"] > 20
            assert row["overtime_hours"] == round(row["hours_worked"] - 20, 2)

    def test_hours_are_split_across_week_boundaries(self, scenario):
        """Five days can land in two ISO weeks. Totals still have to add up."""
        rows = reports.overtime(scenario["start"], scenario["end"], threshold_hours=0)
        ada_hours = sum(row["hours_worked"] for row in rows if row["name"] == "Ada Lovelace")
        assert ada_hours == 40.0

    def test_weeks_are_reported_separately(self, scenario):
        rows = reports.overtime(scenario["start"], scenario["end"], threshold_hours=1)
        weeks = {(row["employee_id"], row["week_starting"]) for row in rows}
        assert len(weeks) == len(rows)  # one row per employee per week


class TestDashboard:
    def test_headline_numbers(self, scenario):
        data = reports.dashboard(scenario["start"], scenario["end"])
        assert data["total_employees"] == 2
        assert data["shifts_scheduled"] == 10
        assert data["present_count"] == 8
        assert data["late_count"] == 1
        assert data["open_gaps"] == 2
        assert len(data["daily_attendance"]) == 5
