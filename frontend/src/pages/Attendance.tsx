import { useState } from "react";

import { api } from "../api/client";
import { useApiMutation, useAttendance, useDepartments } from "../api/hooks";
import type { Attendance } from "../api/types";
import { useConfirm } from "../components/confirm";
import { PageHeader } from "../components/Shell";
import { Blank, Busy, Card, Field, Tag, Who, useSnack } from "../components/ui";
import { formatDate, formatTime, shift as addDays, today } from "../lib/period";

export function AttendancePage() {
  const [date, setDate] = useState(today());
  const [department, setDepartment] = useState("");

  const { say, snack } = useSnack();
  const confirm = useConfirm();

  const departments = useDepartments();
  const attendance = useAttendance({ page_size: 200, date, department, ordering: "employee__last_name" });

  const openDay = useApiMutation<void, { created_count: number }>(() =>
    api.post("/attendance/open-day/", { date, department: department || undefined }),
  );
  const punch = useApiMutation<{ id: number; action: "check-in" | "check-out" }, Attendance>(({ id, action }) =>
    api.post(`/attendance/${id}/${action}/`, {}),
  );

  const rows = attendance.data?.results ?? [];
  const onFloor = rows.filter((row) => row.check_in && !row.check_out).length;

  const askOpenDay = async () => {
    const scope = department
      ? departments.data?.results.find((d) => String(d.id) === department)?.name
      : "every department";
    const ok = await confirm({
      title: "Open the day?",
      body: `Creates clock-in records from the roster for ${formatDate(date, { weekday: "long", day: "numeric", month: "long" })} in ${scope}. Existing records are left alone.`,
      confirmLabel: "Open the day",
    });
    if (!ok) return;
    openDay.mutate(undefined, {
      onSuccess: (result) =>
        say(
          result.created_count
            ? `${result.created_count} records opened for clock-in`
            : "Every rostered shift already has a record",
        ),
      onError: (error) => say((error as Error).message, true),
    });
  };

  const clockIn = (row: Attendance, action: "check-in" | "check-out") =>
    punch.mutate(
      { id: row.id, action },
      {
        onSuccess: (saved) =>
          say(`${saved.employee_name} ${action === "check-in" ? "checked in" : "checked out"}`),
        onError: (error) => say((error as Error).message, true),
      },
    );

  return (
    <>
      <PageHeader
        title="Attendance"
        note={`${rows.length} records · ${onFloor} currently on the floor`}
      >
        <div className="toolbar">
          <button className="btn btn-icon" aria-label="Previous day" onClick={() => setDate(addDays(date, -1))}>‹</button>
          <Field label="Date">
            <input className="input" type="date" value={date} onChange={(e) => setDate(e.target.value)} />
          </Field>
          <button className="btn btn-icon" aria-label="Next day" onClick={() => setDate(addDays(date, 1))}>›</button>
          <button className="btn btn-primary" disabled={openDay.isPending} onClick={askOpenDay}>
            {openDay.isPending ? "Opening" : "Open the day"}
          </button>
        </div>
      </PageHeader>

      <div className="content">
        <Card
          title={formatDate(date, { weekday: "long", day: "numeric", month: "long", year: "numeric" })}
          note="Lateness is measured against the scheduled start of the assigned shift."
          actions={
            <Field label="Department">
              <select className="select" value={department} onChange={(e) => setDepartment(e.target.value)}>
                <option value="">All departments</option>
                {departments.data?.results.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
              </select>
            </Field>
          }
        >
          {attendance.isLoading ? (
            <Busy text="Loading the day sheet" />
          ) : rows.length === 0 ? (
            <Blank title="Nothing recorded yet">
              Use “Open the day” to create clock-in records from the roster.
            </Blank>
          ) : (
            <div className="scroll-x">
              <table className="data">
                <thead>
                  <tr>
                    <th>Employee</th>
                    <th>Department</th>
                    <th>Shift</th>
                    <th>Status</th>
                    <th className="num">In</th>
                    <th className="num">Out</th>
                    <th className="num">Late</th>
                    <th className="num">Hours</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row) => (
                    <tr key={row.id}>
                      <td data-label="Employee"><Who name={row.employee_name} /></td>
                      <td data-label="Department">{row.department_name}</td>
                      <td className="key" data-label="Shift">
                        {row.shift_name ?? <span className="tag off">Unscheduled cover</span>}
                      </td>
                      <td data-label="Status"><Tag status={row.status} /></td>
                      <td className="num" data-label="In">{formatTime(row.check_in)}</td>
                      <td className="num" data-label="Out">{formatTime(row.check_out)}</td>
                      <td className="num" data-label="Late" style={row.minutes_late > 5 ? { color: "var(--gold-hi)" } : undefined}>
                        {row.minutes_late ? `${row.minutes_late}m` : "—"}
                      </td>
                      <td className="num" data-label="Hours">{row.worked_hours ? row.worked_hours.toFixed(2) : "—"}</td>
                      <td className="row-actions">
                        {!row.check_in && (
                          <button className="btn btn-sm" disabled={punch.isPending} onClick={() => clockIn(row, "check-in")}>
                            Check in
                          </button>
                        )}
                        {row.check_in && !row.check_out && (
                          <button className="btn btn-sm" disabled={punch.isPending} onClick={() => clockIn(row, "check-out")}>
                            Check out
                          </button>
                        )}
                        {row.check_in && row.check_out && <span className="who-sub">Done</span>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      </div>

      {snack}
    </>
  );
}
