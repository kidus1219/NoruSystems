"""Core models for staff scheduling and attendance."""

from datetime import datetime, timedelta

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone

MINUTES_PER_DAY = 24 * 60


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class Department(TimeStampedModel):
    """Front Office, Housekeeping, F&B and so on."""

    name = models.CharField(max_length=100, unique=True)
    code = models.CharField(max_length=20, unique=True, help_text="Short code, e.g. FO, HK.")
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Role(TimeStampedModel):
    """Job title. Null department means the role exists hotel-wide."""

    title = models.CharField(max_length=100)
    code = models.CharField(max_length=20, unique=True)
    department = models.ForeignKey(
        Department,
        on_delete=models.CASCADE,
        related_name="roles",
        null=True,
        blank=True,
        help_text="Leave empty for roles that exist across the whole hotel (e.g. General Manager).",
    )
    base_hourly_rate = models.DecimalField(
        max_digits=8, decimal_places=2, validators=[MinValueValidator(0)]
    )
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["title"]
        constraints = [
            models.UniqueConstraint(
                fields=["department", "title"], name="unique_role_title_per_department"
            )
        ]

    def __str__(self):
        return f"{self.title} ({self.department.code})" if self.department else self.title


class Shift(TimeStampedModel):
    """A shift pattern. Putting one on the calendar creates a ShiftAssignment."""

    name = models.CharField(max_length=100, unique=True)
    code = models.CharField(max_length=20, unique=True)
    start_time = models.TimeField()
    end_time = models.TimeField()
    break_minutes = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["start_time"]

    def __str__(self):
        return f"{self.name} ({self.start_time:%H:%M}-{self.end_time:%H:%M})"

    @property
    def crosses_midnight(self):
        """True for the night shifts, e.g. 22:00-06:00."""
        return self.end_time <= self.start_time

    @property
    def duration_minutes(self):
        """Paid minutes, i.e. the span minus the unpaid break."""
        return max(self.span_minutes - self.break_minutes, 0)

    @property
    def duration_hours(self):
        return round(self.duration_minutes / 60, 2)

    @property
    def span_minutes(self):
        """Length of the shift on the clock. Wraps past midnight."""
        start = self.start_time.hour * 60 + self.start_time.minute
        end = self.end_time.hour * 60 + self.end_time.minute
        return (end - start) % MINUTES_PER_DAY or MINUTES_PER_DAY

    def clean(self):
        if self.break_minutes >= self.span_minutes:
            raise ValidationError({"break_minutes": "Break cannot consume the entire shift."})

    def start_datetime_for(self, date):
        """Aware datetime for when this shift starts on the given date."""
        return timezone.make_aware(datetime.combine(date, self.start_time))

    def end_datetime_for(self, date):
        end = timezone.make_aware(datetime.combine(date, self.end_time))
        return end + timedelta(days=1) if self.crosses_midnight else end


class Employee(TimeStampedModel):
    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        ON_LEAVE = "on_leave", "On leave"
        SUSPENDED = "suspended", "Suspended"
        TERMINATED = "terminated", "Terminated"

    class EmploymentType(models.TextChoices):
        FULL_TIME = "full_time", "Full time"
        PART_TIME = "part_time", "Part time"
        CONTRACT = "contract", "Contract"
        SEASONAL = "seasonal", "Seasonal"

    employee_code = models.CharField(max_length=20, unique=True, blank=True)
    first_name = models.CharField(max_length=80)
    last_name = models.CharField(max_length=80)
    email = models.EmailField(unique=True)
    phone = models.CharField(max_length=30, blank=True)

    department = models.ForeignKey(Department, on_delete=models.PROTECT, related_name="employees")
    role = models.ForeignKey(Role, on_delete=models.PROTECT, related_name="employees")
    manager = models.ForeignKey(
        "self", on_delete=models.SET_NULL, null=True, blank=True, related_name="direct_reports"
    )

    employment_type = models.CharField(
        max_length=20, choices=EmploymentType.choices, default=EmploymentType.FULL_TIME
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
    hire_date = models.DateField()
    termination_date = models.DateField(null=True, blank=True)
    hourly_rate = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0)],
        help_text="Overrides the role's base rate when set.",
    )

    class Meta:
        ordering = ["last_name", "first_name"]
        indexes = [
            models.Index(fields=["department", "status"]),
            models.Index(fields=["role"]),
        ]

    def __str__(self):
        return f"{self.full_name} [{self.employee_code}]"

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"

    @property
    def effective_hourly_rate(self):
        """Their own rate if they have one, otherwise the role's."""
        return self.hourly_rate if self.hourly_rate is not None else self.role.base_hourly_rate

    @property
    def is_schedulable(self):
        return self.status == self.Status.ACTIVE

    def clean(self):
        # Department-scoped roles can only be held inside that department.
        if self.role_id and self.department_id and self.role.department_id:
            if self.role.department_id != self.department_id:
                raise ValidationError(
                    {"role": f"Role '{self.role.title}' belongs to {self.role.department}, "
                             f"not to the assigned department."}
                )
        if self.termination_date and self.termination_date < self.hire_date:
            raise ValidationError({"termination_date": "Termination cannot precede the hire date."})
        if self.manager_id and self.manager_id == self.pk:
            raise ValidationError({"manager": "An employee cannot manage themselves."})

    def save(self, *args, **kwargs):
        if not self.employee_code:
            self.employee_code = self._next_employee_code()
        super().save(*args, **kwargs)

    @classmethod
    def _next_employee_code(cls):
        """Next code in the EMP-0001 sequence.

        Fine for admin-speed writes. Would need a real DB sequence if we ever
        create employees concurrently.
        """
        last = cls.objects.order_by("-id").values_list("employee_code", flat=True).first()
        next_number = int(last.split("-")[-1]) + 1 if last and "-" in last else 1
        return f"EMP-{next_number:04d}"


class ShiftAssignment(TimeStampedModel):
    """One shift pattern, one employee, one date."""

    class Status(models.TextChoices):
        SCHEDULED = "scheduled", "Scheduled"
        CANCELLED = "cancelled", "Cancelled"

    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="shift_assignments")
    shift = models.ForeignKey(Shift, on_delete=models.PROTECT, related_name="assignments")
    date = models.DateField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.SCHEDULED)
    notes = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["-date", "shift__start_time"]
        constraints = [
            models.UniqueConstraint(
                fields=["employee", "shift", "date"], name="unique_shift_per_employee_per_day"
            )
        ]
        indexes = [
            models.Index(fields=["date", "status"]),
            models.Index(fields=["employee", "date"]),
        ]

    def __str__(self):
        return f"{self.employee.full_name} - {self.shift.name} on {self.date}"

    @property
    def scheduled_start(self):
        return self.shift.start_datetime_for(self.date)

    @property
    def scheduled_end(self):
        return self.shift.end_datetime_for(self.date)

    def clean(self):
        if self.employee_id and not self.employee.is_schedulable:
            raise ValidationError(
                {"employee": f"{self.employee.full_name} is {self.employee.get_status_display().lower()} "
                             f"and cannot be scheduled."}
            )
        if self.shift_id and not self.shift.is_active:
            raise ValidationError({"shift": "Cannot assign an inactive shift."})
        if self.status == self.Status.SCHEDULED:
            self._assert_no_overlap()

    def _assert_no_overlap(self):
        """Reject a shift that overlaps one they already have.

        Has to compare real intervals, not just dates. A 22:00-06:00 shift on
        Monday runs into a 05:00-13:00 shift on Tuesday, and those are two
        different dates.
        """
        if not (self.employee_id and self.shift_id and self.date):
            return
        window = (self.date - timedelta(days=1), self.date + timedelta(days=1))
        neighbours = (
            ShiftAssignment.objects.filter(
                employee_id=self.employee_id, status=self.Status.SCHEDULED, date__range=window
            )
            .exclude(pk=self.pk)
            .select_related("shift")
        )
        start, end = self.scheduled_start, self.scheduled_end
        for other in neighbours:
            if start < other.scheduled_end and other.scheduled_start < end:
                raise ValidationError(
                    {"shift": f"Overlaps '{other.shift.name}' already scheduled on {other.date}."}
                )


class Attendance(TimeStampedModel):
    """What actually happened on the day.

    shift_assignment is nullable because not every case has one:

      worked a rostered shift -> linked to the assignment
      covered at short notice -> no assignment
      never turned up         -> no attendance row at all, or status=absent
    """

    class Status(models.TextChoices):
        PRESENT = "present", "Present"
        LATE = "late", "Late"
        ABSENT = "absent", "Absent"
        ON_LEAVE = "on_leave", "On leave"
        HOLIDAY = "holiday", "Public holiday"

    LATE_GRACE_MINUTES = 5
    STANDARD_DAY_MINUTES = 8 * 60

    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="attendance")
    shift_assignment = models.OneToOneField(
        ShiftAssignment,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="attendance",
    )
    date = models.DateField()
    check_in = models.DateTimeField(null=True, blank=True)
    check_out = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PRESENT)
    notes = models.CharField(max_length=255, blank=True)

    # Worked out in save(). Keeps the reports to one aggregate query each.
    worked_minutes = models.PositiveIntegerField(default=0, editable=False)
    minutes_late = models.IntegerField(default=0, editable=False)

    class Meta:
        ordering = ["-date", "employee__last_name"]
        verbose_name_plural = "attendance"
        constraints = [
            models.UniqueConstraint(
                fields=["employee", "date"], name="unique_attendance_per_employee_per_day"
            )
        ]
        indexes = [
            models.Index(fields=["date", "status"]),
            models.Index(fields=["employee", "date"]),
        ]

    def __str__(self):
        return f"{self.employee.full_name} - {self.date} ({self.get_status_display()})"

    @property
    def worked_hours(self):
        return round(self.worked_minutes / 60, 2)

    @property
    def overtime_minutes(self):
        return max(self.worked_minutes - self.STANDARD_DAY_MINUTES, 0)

    def clock_in(self, timestamp):
        """Clock in. Clears the provisional 'absent' that open-day writes."""
        if self.check_in:
            raise ValidationError({"check_in": "Already checked in."})
        if self.status in (self.Status.ABSENT, self.Status.ON_LEAVE):
            self.status = self.Status.PRESENT
        self.check_in = timestamp
        self.full_clean()
        self.save()
        return self

    def clock_out(self, timestamp):
        if not self.check_in:
            raise ValidationError({"check_out": "Cannot check out before checking in."})
        if self.check_out:
            raise ValidationError({"check_out": "Already checked out."})
        self.check_out = timestamp
        self.full_clean()
        self.save()
        return self

    def clean(self):
        if self.check_out and not self.check_in:
            raise ValidationError({"check_out": "Cannot check out without a check-in."})
        if self.check_in and self.check_out and self.check_out <= self.check_in:
            raise ValidationError({"check_out": "Check-out must be after check-in."})
        if self.shift_assignment_id:
            if self.shift_assignment.employee_id != self.employee_id:
                raise ValidationError(
                    {"shift_assignment": "The shift assignment belongs to a different employee."}
                )
            if self.shift_assignment.date != self.date:
                raise ValidationError(
                    {"date": "Attendance date must match the assigned shift's date."}
                )

    def save(self, *args, **kwargs):
        self.worked_minutes = self._compute_worked_minutes()
        self.minutes_late = self._compute_minutes_late()
        if self.status in (self.Status.PRESENT, self.Status.LATE):
            self.status = (
                self.Status.LATE if self.minutes_late > self.LATE_GRACE_MINUTES
                else self.Status.PRESENT
            )
        super().save(*args, **kwargs)

    def _compute_worked_minutes(self):
        if self.status in (self.Status.ABSENT, self.Status.ON_LEAVE):
            return 0
        if not (self.check_in and self.check_out):
            return 0
        minutes = int((self.check_out - self.check_in).total_seconds() // 60)
        break_minutes = self.shift_assignment.shift.break_minutes if self.shift_assignment_id else 0
        return max(minutes - break_minutes, 0)

    def _compute_minutes_late(self):
        # No assignment means nothing to be late against.
        if not (self.check_in and self.shift_assignment_id):
            return 0
        delta = self.check_in - self.shift_assignment.scheduled_start
        return max(int(delta.total_seconds() // 60), 0)
