import { useState } from "react";

import { api, ApiError } from "../api/client";
import { useApiMutation, useAssignments, useDepartments, useEmployees, useShifts } from "../api/hooks";
import type { Employee, Shift, ShiftAssignment } from "../api/types";
import { useConfirm } from "../components/confirm";
import { PageHeader } from "../components/Shell";
import { Alert, Blank, Busy, Card, Dialog, Field, useSnack } from "../components/ui";
import { clock, formatDate, shift as addDays, startOfWeek, today } from "../lib/period";

const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

const TONE: Record<string, string> = { present: "ok", late: "warn", absent: "bad" };

export function SchedulingPage() {
  const [weekStart, setWeekStart] = useState(startOfWeek(today()));
  const [department, setDepartment] = useState("");
  const [rostering, setRostering] = useState(false);

  const { say, snack } = useSnack();
  const confirm = useConfirm();

  const weekEnd = addDays(weekStart, 6);
  const departments = useDepartments();
  const shifts = useShifts();
  const employees = useEmployees({ page_size: 200, status: "active", department });
  const assignments = useAssignments({
    page_size: 500,
    date_from: weekStart,
    date_to: weekEnd,
    status: "scheduled",
    department,
  });

  const remove = useApiMutation<ShiftAssignment, void>((row) => api.delete(`/shift-assignments/${row.id}/`));

  const askRemove = async (row: ShiftAssignment) => {
    const ok = await confirm({
      title: "Remove this shift?",
      body: `${row.shift_name} for ${row.employee_name} on ${formatDate(row.date, { weekday: "long", day: "numeric", month: "long" })}.`,
      confirmLabel: "Remove",
      destructive: true,
    });
    if (!ok) return;
    remove.mutate(row, {
      onSuccess: () => say("Shift removed"),
      onError: (error) => say((error as Error).message, true),
    });
  };

  const staff = employees.data?.results ?? [];
  const days = DAYS.map((_, i) => addDays(weekStart, i));

  const byCell = new Map<string, ShiftAssignment[]>();
  for (const row of assignments.data?.results ?? []) {
    const key = `${row.employee}|${row.date}`;
    byCell.set(key, [...(byCell.get(key) ?? []), row]);
  }

  return (
    <>
      <PageHeader title="Scheduling" note={`Week of ${formatDate(weekStart)} to ${formatDate(weekEnd)}`}>
        <div className="toolbar">
          <div className="segmented">
            <button onClick={() => setWeekStart(addDays(weekStart, -7))}>Previous</button>
            <button onClick={() => setWeekStart(startOfWeek(today()))}>This week</button>
            <button onClick={() => setWeekStart(addDays(weekStart, 7))}>Next</button>
          </div>
          <button className="btn btn-primary" onClick={() => setRostering(true)}>Roster shifts</button>
        </div>
      </PageHeader>

      <div className="content">
        <Card
          title="Weekly roster"
          note="Active staff only. Select a shift to remove it."
          actions={
            <Field label="Department">
              <select className="select" value={department} onChange={(e) => setDepartment(e.target.value)}>
                <option value="">All departments</option>
                {departments.data?.results.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
              </select>
            </Field>
          }
        >
          {assignments.isLoading || employees.isLoading ? (
            <Busy text="Building the roster" />
          ) : staff.length === 0 ? (
            <Blank title="Nobody to roster">No active staff in this department.</Blank>
          ) : (
            <div className="scroll-x">
              <div className="roster">
                <div className="rs-head"><b>Employee</b></div>
                {days.map((day, i) => (
                  <div key={day} className={`rs-head${day === today() ? " now" : ""}`}>
                    <b>{DAYS[i]}</b>
                    {formatDate(day)}
                  </div>
                ))}

                {staff.map((employee) => (
                  <RosterRow
                    key={employee.id}
                    employee={employee}
                    days={days}
                    byCell={byCell}
                    onRemove={askRemove}
                  />
                ))}
              </div>
            </div>
          )}
        </Card>
      </div>

      {rostering && (
        <RosterDialog
          employees={staff}
          shifts={shifts.data?.results ?? []}
          from={weekStart}
          to={weekEnd}
          onClose={() => setRostering(false)}
          onDone={say}
        />
      )}

      {snack}
    </>
  );
}

// The roster is one flat CSS grid, so a row is just its cells emitted in order.
function RosterRow({ employee, days, byCell, onRemove }: {
  employee: Employee;
  days: string[];
  byCell: Map<string, ShiftAssignment[]>;
  onRemove: (row: ShiftAssignment) => void;
}) {
  return (
    <>
      <div>
        <div>{employee.full_name}</div>
        <div className="who-sub">{employee.role_title}</div>
      </div>
      {days.map((day) => (
        <div key={day} className="rs-cell">
          {(byCell.get(`${employee.id}|${day}`) ?? []).map((row) => (
            <button
              key={row.id}
              className={`shift-chip ${TONE[row.attendance_status ?? ""] ?? ""}`}
              title={`${row.shift_name} ${clock(row.start_time)}-${clock(row.end_time)}`}
              onClick={() => onRemove(row)}
            >
              {row.shift_name}
              <em>×</em>
            </button>
          ))}
        </div>
      ))}
    </>
  );
}

type BulkResult = {
  created_count: number;
  skipped_count: number;
  skipped: { employee: string; date: string; reason: string }[];
};

function RosterDialog({ employees, shifts, from, to, onClose, onDone }: {
  employees: Employee[];
  shifts: Shift[];
  from: string;
  to: string;
  onClose: () => void;
  onDone: (message: string) => void;
}) {
  const [picked, setPicked] = useState<number[]>([]);
  const [shiftId, setShiftId] = useState("");
  const [start, setStart] = useState(from);
  const [end, setEnd] = useState(to);
  const [weekdays, setWeekdays] = useState([0, 1, 2, 3, 4]);
  const [errors, setErrors] = useState<Record<string, string[]> | null>(null);
  const [skipped, setSkipped] = useState<BulkResult["skipped"]>([]);

  const roster = useApiMutation<unknown, BulkResult>((body) => api.post("/shift-assignments/bulk/", body));

  const toggle = <T,>(list: T[], value: T) =>
    list.includes(value) ? list.filter((v) => v !== value) : [...list, value];

  const submit = () => {
    setErrors(null);
    roster.mutate(
      { employees: picked, shift: Number(shiftId), start_date: start, end_date: end, weekdays },
      {
        onSuccess: (result) => {
          setSkipped(result.skipped);
          onDone(`${result.created_count} rostered, ${result.skipped_count} skipped`);
          if (result.skipped_count === 0) onClose();
        },
        onError: (error) =>
          setErrors(error instanceof ApiError ? error.fields : { detail: [String(error)] }),
      },
    );
  };

  return (
    <Dialog
      title="Roster shifts"
      lede="Apply one shift to several people across a date range."
      onClose={onClose}
      footer={
        <>
          <button className="btn" onClick={onClose}>Close</button>
          <button
            className="btn btn-primary"
            disabled={roster.isPending || !shiftId || picked.length === 0}
            onClick={submit}
          >
            {roster.isPending ? "Rostering" : "Roster shifts"}
          </button>
        </>
      }
    >
      <Alert fields={errors} />

      <Field label="Shift">
        <select className="select" value={shiftId} onChange={(e) => setShiftId(e.target.value)}>
          <option value="">Select a shift</option>
          {shifts.map((s) => (
            <option key={s.id} value={s.id}>
              {s.name} · {clock(s.start_time)}-{clock(s.end_time)}
            </option>
          ))}
        </select>
      </Field>

      <Field label="Days of the week">
        <div className="day-toggle">
          {DAYS.map((day, i) => (
            <button
              key={day}
              type="button"
              aria-pressed={weekdays.includes(i)}
              onClick={() => setWeekdays((current) => toggle(current, i))}
            >
              {day}
            </button>
          ))}
        </div>
      </Field>

      <div className="pair">
        <Field label="From">
          <input className="input" type="date" value={start} onChange={(e) => setStart(e.target.value)} />
        </Field>
        <Field label="To">
          <input className="input" type="date" value={end} onChange={(e) => setEnd(e.target.value)} />
        </Field>
      </div>

      <Field label={`Employees · ${picked.length} selected`}>
        <div className="picklist">
          {employees.map((employee) => (
            <label key={employee.id}>
              <input
                type="checkbox"
                checked={picked.includes(employee.id)}
                onChange={() => setPicked((current) => toggle(current, employee.id))}
              />
              {employee.full_name}
              <span className="who-sub">{employee.role_title}</span>
            </label>
          ))}
        </div>
      </Field>

      {skipped.length > 0 && (
        <div className="alert">
          <b>Skipped {skipped.length}</b>
          {skipped.slice(0, 6).map((row, i) => (
            <div key={i}>{row.employee} on {row.date} — {row.reason}</div>
          ))}
          {skipped.length > 6 && <div>and {skipped.length - 6} more.</div>}
        </div>
      )}
    </Dialog>
  );
}
