# Noru — Hotel Employee Management

Staff module for a hotel: employees, departments, roles, shift patterns, rosters and
attendance, plus the reports a duty manager actually asks for.

Django 5.2 + DRF on the back, React + Vite on the front, SQLite by default.
Light and dark themes, and it works on a phone.

There is a separate [USAGE.md](USAGE.md) covering what each screen does.

## Running it

Two terminals.

```bash
# backend
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

python manage.py migrate
python manage.py seed_demo      # 40 staff and four weeks of history
python manage.py runserver

# frontend
cd frontend
npm install
npm run dev
```

| | |
|---|---|
| http://localhost:5173 | the app |
| http://127.0.0.1:8000/api/docs/ | Swagger, generated off the code |
| http://127.0.0.1:8000/admin/ | Django admin, needs `createsuperuser` |

`pytest` from `backend/` runs the suite (66 tests).

For Postgres: `docker compose up -d`, `pip install "psycopg[binary]"`, then set
`DATABASE_URL=postgres://hotel:hotel@localhost:5432/hotel` in `backend/.env`.
Nothing else changes.

## Layout

```
backend/
  config/            settings and root urls
  hotel/
    models.py        the domain and its rules
    reports.py       the analytical queries
    serializers.py
    views.py
    filters.py
    admin.py
    management/commands/seed_demo.py
    tests/
frontend/
  src/api/           typed client and query hooks
  src/components/
  src/pages/
```

Rules live on the models. The serializers call `full_clean()` instead of
re-implementing validation, so the API, the admin and the seed command all behave
the same way. Reports are functions that take two dates and return dicts, which
means they can be tested without HTTP. Views stay thin.

## Schema

```
Department ──< Role
     │           │
     └──< Employee >──┘        (+ manager self-FK)
             │
             └──< ShiftAssignment >── Shift
                        │
                        └──○ Attendance
```

| Table | Notes |
|---|---|
| `Department` | unique name and code |
| `Role` | title + base hourly rate. Nullable department for hotel-wide roles |
| `Employee` | FKs to department and role, self-FK to manager |
| `Shift` | a reusable pattern, e.g. Night Audit 22:00–06:00 with a 45m break |
| `ShiftAssignment` | that pattern on a date for one person. Unique per (employee, shift, date) |
| `Attendance` | what happened. Unique per (employee, date) |

A few things worth calling out.

**Shifts are patterns, not rows per day.** Putting start and end times on every
rostered day would duplicate them thousands of times and make changing a shift a
migration over history.

**Overnight shifts are handled properly.** `end_time <= start_time` means the shift
crosses midnight, and the duration wraps instead of going negative. This also makes
overlap detection a real interval comparison: a 22:00–06:00 shift on Monday clashes
with a 05:00–13:00 shift on Tuesday, and those are different dates, so a
one-shift-per-day rule would miss it. There's a test for it.

**`Attendance.shift_assignment` is nullable.** That's what lets the schema hold all
three cases: rostered and worked (linked), covered at short notice (unlinked), and
never turned up (no attendance row at all, or one marked absent). The third case is
the awkward one — an absence proved by a row that isn't there.

**`worked_minutes` and `minutes_late` are computed in `save()`.** Lateness only means
something next to the scheduled start, which is a three-table join. Deriving it per
row at read time would force every report into a Python loop. They're
`editable=False` and read-only in the serializer, so nothing else can set them.

**PROTECT on department and role, CASCADE on assignments and attendance.** You
shouldn't be able to delete a department with staff in it. Rosters and timesheets,
on the other hand, are meaningless without the employee.

**Rates fall back.** `Employee.hourly_rate` is nullable and coalesces to the role's
base rate, so a role-wide pay change is one update and per-person costs still come
out right.

## The interesting report

`GET /api/reports/coverage-gaps/` — `hotel/reports.py::coverage_gaps`

For every `(date, shift, department)` that was planned, compare how many people were
rostered against how many actually showed up, and return only the ones that came up
short, split into excused leave and unexcused no-shows.

```python
rostered.values("date", "shift_id", shift_name=…, dept_id=…, dept_name=…)
        .annotate(
            scheduled = Count("id", distinct=True),
            present   = Count("id", filter=Q(attendance__status__in=[PRESENT, LATE]), distinct=True),
            excused   = Count("id", filter=Q(attendance__status__in=[ON_LEAVE, HOLIDAY]), distinct=True),
        )
        .annotate(missing=F("scheduled") - F("present"))
        .filter(missing__gt=0)
```

The important bit is counting from the assignment side rather than the attendance
side. A rostered shift with no attendance record still counts towards `scheduled`
and contributes nothing to `present`, so the silent no-show shows up. Filtering on
the annotation becomes a `HAVING`, so covered shifts never leave the database.

The other three:

- **department-summary** — headcount, roster volume, attendance and punctuality
  rates, hours, labour cost.
- **employee-scorecard** — per person, ranked inside their department with
  `Window(Rank())`. No-shows sort ahead of lateness.
- **overtime** — `TruncWeek` and a `HAVING` on a configurable weekly threshold.

### Watch the joins

`department_summary` and `employee_scorecard` pull roster counts from subqueries
rather than a second join. Joining `shift_assignments` and `attendance` in the same
query gives a cross product. `Count` survives that with `distinct=True`, `Sum` and
`Avg` don't — total hours quietly come back multiplied. It bit me during
development; two tests now compare the ORM result against the same sum done in
Python.

## API

Full docs at `/api/docs/`.

| | |
|---|---|
| `/api/employees/` | CRUD. Filter on department, role, status, employment_type. `?search=` hits name, email, staff number |
| `/api/employees/{id}/assign/` | POST. Department, role and manager together |
| `/api/employees/{id}/schedule/` | GET. Their shifts over a period |
| `/api/departments/`, `/api/roles/`, `/api/shifts/` | CRUD |
| `/api/shift-assignments/` | CRUD. `date_from`, `date_to`, `department`, `unattended` |
| `/api/shift-assignments/bulk/` | POST. One shift, many people, a date range |
| `/api/attendance/` | CRUD. `date_from`, `date_to`, `department`, `status` |
| `/api/attendance/open-day/` | POST. Creates the day's records off the roster |
| `/api/attendance/{id}/check-in/`, `/check-out/` | POST |
| `/api/reports/{name}/` | `start`, `end`, `department`, `threshold_hours` |

Assignment is its own endpoint rather than a plain PATCH because department and role
have to be validated together. Moving someone to a department where their role
doesn't exist has to fail as one operation:

```bash
curl -X POST localhost:8000/api/employees/7/assign/ \
     -H 'Content-Type: application/json' -d '{"department": 2}'

{"role": ["Role 'Front Desk Agent' belongs to Front Office, not to the assigned department."]}
```

Bulk rostering skips what it can't create instead of failing the batch:

```json
{ "created_count": 279, "skipped_count": 1,
  "skipped": [{"employee": "Ada Lovelace", "date": "2026-09-03",
               "reason": "Overlaps 'Night Audit' already scheduled on 2026-09-02."}] }
```

## Tests

```
cd backend && pytest -q
66 passed
```

`test_models.py` covers the constraints and clean() rules — overnight durations, the
cross-midnight overlap, role/department consistency, derived lateness and hours, the
grace period. `test_api.py` covers CRUD, filtering, the assign failure, bulk skips
and the clock lifecycle. `test_reports.py` asserts exact numbers against a five-day
fixture, plus the two fan-out regressions.

## Not done

Auth and per-department permissions, an audit trail on roster and attendance edits,
leave requests, and moving `employee_code` off max-plus-one onto a database
sequence. Fine at admin speed, would race under concurrent writes.
