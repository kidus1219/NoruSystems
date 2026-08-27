"""Demo data: roughly a month of hotel operations.

Seeded RNG so the numbers come out the same every time.
"""

import random
from datetime import time, timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from hotel.models import Attendance, Department, Employee, Role, Shift, ShiftAssignment

RANDOM_SEED = 20260827

DEPARTMENTS = [
    ("Front Office", "FO", "Reception, concierge and guest relations."),
    ("Housekeeping", "HK", "Rooms, laundry and public areas."),
    ("Food & Beverage", "FB", "Restaurant, bar and room service."),
    ("Kitchen", "KIT", "Main kitchen and pastry."),
    ("Maintenance", "MNT", "Engineering and facilities."),
    ("Administration", "ADM", "Finance, HR and management."),
]

# (title, code, department code or None for org-wide, hourly rate, headcount)
ROLES = [
    ("Front Desk Agent", "FO-AGT", "FO", "14.50", 6),
    ("Concierge", "FO-CON", "FO", "16.00", 2),
    ("Front Office Manager", "FO-MGR", "FO", "26.00", 1),
    ("Room Attendant", "HK-ATT", "HK", "13.00", 8),
    ("Housekeeping Supervisor", "HK-SUP", "HK", "19.50", 2),
    ("Waiter", "FB-WTR", "FB", "13.50", 6),
    ("Bartender", "FB-BAR", "FB", "15.00", 2),
    ("Restaurant Manager", "FB-MGR", "FB", "25.00", 1),
    ("Line Cook", "KIT-CK", "KIT", "17.00", 5),
    ("Head Chef", "KIT-CHF", "KIT", "32.00", 1),
    ("Maintenance Technician", "MNT-TEC", "MNT", "18.50", 3),
    ("Accountant", "ADM-ACC", "ADM", "24.00", 2),
    ("General Manager", "GM", None, "45.00", 1),
]

SHIFTS = [
    ("Morning", "AM", time(6, 0), time(14, 0), 30),
    ("Afternoon", "PM", time(14, 0), time(22, 0), 30),
    ("Night Audit", "NIGHT", time(22, 0), time(6, 0), 45),
    ("Mid Day", "MID", time(10, 0), time(18, 0), 30),
    ("Split Evening", "EVE", time(17, 0), time(23, 0), 15),
]

FIRST_NAMES = [
    "Amina", "Bereket", "Chen", "Dawit", "Elena", "Fatima", "Girma", "Hanna", "Ibrahim", "Jelena",
    "Kalkidan", "Liya", "Mekdes", "Nardos", "Omar", "Priya", "Rahel", "Samuel", "Tigist", "Yonas",
    "Abel", "Bezawit", "Caleb", "Daniel", "Eyob", "Feven", "Genet", "Helen", "Isaac", "Jemal",
    "Kidus", "Lulit", "Meron", "Natnael", "Oliver", "Paulos", "Ruth", "Selam", "Tewodros", "Zara",
]
LAST_NAMES = [
    "Abebe", "Bekele", "Chala", "Desta", "Endale", "Fikru", "Gebre", "Haile", "Iyasu", "Jemberu",
    "Kassa", "Lemma", "Mengistu", "Negash", "Oljira", "Petros", "Regassa", "Solomon", "Tadesse",
    "Wolde", "Yohannes", "Zeleke",
]


class Command(BaseCommand):
    help = "Seed the database with demo hotel data (departments, staff, roster and attendance)."

    def add_arguments(self, parser):
        parser.add_argument("--days", type=int, default=28, help="Days of history to generate.")
        parser.add_argument(
            "--flush", action="store_true", help="Delete existing hotel data before seeding."
        )

    @transaction.atomic
    def handle(self, *args, **options):
        random.seed(RANDOM_SEED)

        if options["flush"]:
            for model in (Attendance, ShiftAssignment, Employee, Role, Shift, Department):
                model.objects.all().delete()
            self.stdout.write(self.style.WARNING("Existing hotel data removed."))

        if Employee.objects.exists():
            self.stdout.write(
                self.style.WARNING("Data already present -- re-run with --flush to rebuild.")
            )
            return

        departments = self._create_departments()
        roles = self._create_roles(departments)
        shifts = self._create_shifts()
        employees = self._create_employees(departments, roles)
        self._assign_managers(employees)
        assignments = self._create_roster(employees, shifts, options["days"])
        attendance_count = self._create_attendance(assignments)

        self.stdout.write(
            self.style.SUCCESS(
                f"Seeded {len(departments)} departments, {len(roles)} roles, {len(shifts)} shifts, "
                f"{len(employees)} employees, {len(assignments)} shift assignments and "
                f"{attendance_count} attendance records."
            )
        )

    def _create_departments(self):
        return {
            code: Department.objects.create(name=name, code=code, description=description)
            for name, code, description in DEPARTMENTS
        }

    def _create_roles(self, departments):
        roles = {}
        for title, code, dept_code, rate, _ in ROLES:
            roles[code] = Role.objects.create(
                title=title,
                code=code,
                department=departments[dept_code] if dept_code else None,
                base_hourly_rate=Decimal(rate),
                description=f"{title} at the hotel.",
            )
        return roles

    def _create_shifts(self):
        return [
            Shift.objects.create(
                name=name, code=code, start_time=start, end_time=end, break_minutes=brk
            )
            for name, code, start, end, brk in SHIFTS
        ]

    def _create_employees(self, departments, roles):
        employees = []
        used_names = set()
        today = timezone.localdate()

        for title, code, dept_code, _, headcount in ROLES:
            role = roles[code]
            # Org-wide roles (the GM) still need a home department for reporting.
            department = departments[dept_code] if dept_code else departments["ADM"]
            for _ in range(headcount):
                first, last = self._unique_name(used_names)
                status = self._weighted_status()
                employees.append(
                    Employee.objects.create(
                        first_name=first,
                        last_name=last,
                        email=f"{first}.{last}{len(employees)}".lower() + "@noruhotel.example",
                        phone=f"+2519{random.randint(10_000_000, 99_999_999)}",
                        department=department,
                        role=role,
                        employment_type=random.choices(
                            [t for t, _ in Employee.EmploymentType.choices],
                            weights=[70, 18, 8, 4],
                        )[0],
                        status=status,
                        hire_date=today - timedelta(days=random.randint(30, 2200)),
                        # A quarter of them are on a premium over the role rate.
                        hourly_rate=(
                            role.base_hourly_rate + Decimal(random.choice(["0.50", "1.00", "2.00"]))
                            if random.random() < 0.25
                            else None
                        ),
                    )
                )
        return employees

    def _unique_name(self, used):
        while True:
            pair = (random.choice(FIRST_NAMES), random.choice(LAST_NAMES))
            if pair not in used:
                used.add(pair)
                return pair

    def _weighted_status(self):
        return random.choices(
            [Employee.Status.ACTIVE, Employee.Status.ON_LEAVE, Employee.Status.TERMINATED],
            weights=[90, 6, 4],
        )[0]

    def _assign_managers(self, employees):
        """Staff report to their department head, heads report to the GM."""
        managers = {
            e.department_id: e
            for e in employees
            if e.role.code in {"FO-MGR", "FB-MGR", "KIT-CHF", "HK-SUP"}
        }
        gm = next((e for e in employees if e.role.code == "GM"), None)
        for employee in employees:
            manager = managers.get(employee.department_id)
            if manager and manager.pk != employee.pk:
                employee.manager = manager
            elif gm and gm.pk != employee.pk:
                employee.manager = gm
            employee.save(update_fields=["manager"])

    def _create_roster(self, employees, shifts, days):
        """About five days a week each, skipping anything that clashes."""
        today = timezone.localdate()
        start = today - timedelta(days=days - 1)
        schedulable = [e for e in employees if e.is_schedulable]
        assignments = []

        for employee in schedulable:
            # People mostly stick to one shift and occasionally cover another.
            usual_shift = random.choice(shifts)
            for offset in range(days):
                day = start + timedelta(days=offset)
                if random.random() < 0.28:  # days off
                    continue
                shift = usual_shift if random.random() < 0.85 else random.choice(shifts)
                assignment = ShiftAssignment(employee=employee, shift=shift, date=day)
                try:
                    assignment.full_clean()
                except Exception:
                    continue  # clashes with something, skip it
                assignment.save()
                assignments.append(assignment)
        return assignments

    def _create_attendance(self, assignments):
        """Mostly on time, some late, a few no-shows."""
        created = 0
        seen = set()
        for assignment in assignments:
            key = (assignment.employee_id, assignment.date)
            if key in seen:
                continue
            seen.add(key)

            roll = random.random()
            if roll < 0.04:
                # No row at all. This is the case coverage_gaps has to catch.
                continue
            if roll < 0.07:
                Attendance.objects.create(
                    employee=assignment.employee,
                    shift_assignment=assignment,
                    date=assignment.date,
                    status=Attendance.Status.ABSENT,
                    notes="Called in sick.",
                )
                created += 1
                continue
            if roll < 0.09:
                Attendance.objects.create(
                    employee=assignment.employee,
                    shift_assignment=assignment,
                    date=assignment.date,
                    status=Attendance.Status.ON_LEAVE,
                    notes="Approved leave.",
                )
                created += 1
                continue

            scheduled_start = assignment.scheduled_start
            lateness = random.choices([0, 3, 9, 22, 47], weights=[58, 18, 14, 7, 3])[0]
            check_in = scheduled_start + timedelta(minutes=lateness - random.randint(0, 4))
            worked = assignment.shift.span_minutes + random.choices(
                [0, 15, 45, 90], weights=[70, 15, 10, 5]
            )[0]
            Attendance.objects.create(
                employee=assignment.employee,
                shift_assignment=assignment,
                date=assignment.date,
                check_in=check_in,
                check_out=check_in + timedelta(minutes=worked),
                status=Attendance.Status.PRESENT,
            )
            created += 1
        return created
