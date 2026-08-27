import { useState } from "react";

import { useCoverageGaps, useDepartments, useOvertime, useScorecard } from "../api/hooks";
import { PageHeader } from "../components/Shell";
import { Bar, Blank, Busy, Card, Field, Who } from "../components/ui";
import { formatDate, usePeriod } from "../lib/period";

type Period = { start: string; end: string };
type TabKey = "gaps" | "reliability" | "overtime";

const TABS: { key: TabKey; label: string; note: string }[] = [
  { key: "gaps", label: "Coverage gaps", note: "Where the roster did not turn into actual coverage" },
  { key: "reliability", label: "Reliability", note: "Attendance per person, ranked within their department" },
  { key: "overtime", label: "Overtime", note: "Weeks that ran past the hour threshold" },
];

export function ReportsPage() {
  const { period, setStart, setEnd } = usePeriod();
  const [tab, setTab] = useState<TabKey>("gaps");
  const [department, setDepartment] = useState("");
  const [threshold, setThreshold] = useState(40);

  const departments = useDepartments();
  const current = TABS.find((t) => t.key === tab)!;

  return (
    <>
      <PageHeader title="Reports" note={`${formatDate(period.start)} to ${formatDate(period.end)}`}>
        <div className="toolbar">
          <Field label="From">
            <input className="input" type="date" value={period.start} onChange={(e) => setStart(e.target.value)} />
          </Field>
          <Field label="To">
            <input className="input" type="date" value={period.end} onChange={(e) => setEnd(e.target.value)} />
          </Field>
          <Field label="Department">
            <select className="select" value={department} onChange={(e) => setDepartment(e.target.value)}>
              <option value="">All departments</option>
              {departments.data?.results.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
            </select>
          </Field>
          {tab === "overtime" && (
            <Field label="Weekly hours">
              <input
                className="input"
                type="number"
                min={1}
                style={{ width: 90 }}
                value={threshold}
                onChange={(e) => setThreshold(Number(e.target.value) || 1)}
              />
            </Field>
          )}
        </div>
      </PageHeader>

      <div className="content">
        <div className="segmented" style={{ alignSelf: "flex-start" }}>
          {TABS.map((t) => (
            <button key={t.key} aria-pressed={tab === t.key} onClick={() => setTab(t.key)}>
              {t.label}
            </button>
          ))}
        </div>

        <Card title={current.label} note={current.note}>
          {tab === "gaps" && <CoverageGaps period={period} department={department} />}
          {tab === "reliability" && <Reliability period={period} department={department} />}
          {tab === "overtime" && <Overtime period={period} threshold={threshold} />}
        </Card>
      </div>
    </>
  );
}

function CoverageGaps({ period, department }: { period: Period; department: string }) {
  const query = useCoverageGaps({ ...period, department });
  if (query.isLoading) return <Busy />;

  const rows = query.data?.results ?? [];
  if (!rows.length) return <Blank title="No gaps">Every rostered shift was covered in this period.</Blank>;

  const missing = rows.reduce((sum, row) => sum + row.missing, 0);

  return (
    <>
      <p className="card-note" style={{ padding: "14px 18px 0" }}>
        {rows.length} shift slots ran short. {missing} rostered people did not cover their shift.
      </p>
      <div className="scroll-x">
        <table className="data">
          <thead>
            <tr>
              <th>Date</th>
              <th>Shift</th>
              <th>Department</th>
              <th className="num">Rostered</th>
              <th className="num">Present</th>
              <th className="num">Excused</th>
              <th className="num">No-shows</th>
              <th>Coverage</th>
              <th>Severity</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={`${row.date}-${row.shift_id}-${row.department_id}`}>
                <td className="num" data-label="Date">{formatDate(row.date, { weekday: "short", day: "numeric", month: "short" })}</td>
                <td className="key" data-label="Shift">{row.shift}</td>
                <td data-label="Department">{row.department}</td>
                <td className="num" data-label="Rostered">{row.scheduled}</td>
                <td className="num" data-label="Present">{row.present}</td>
                <td className="num" data-label="Excused">{row.excused_absences || "—"}</td>
                <td className="num" data-label="No-shows" style={row.unexcused_no_shows ? { color: "var(--bad)" } : undefined}>
                  {row.unexcused_no_shows || "—"}
                </td>
                <td data-label="Coverage">
                  <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                    <Bar value={row.coverage_rate} tone={coverageTone(row.coverage_rate)} />
                    <span className="mono">{row.coverage_rate}%</span>
                  </div>
                </td>
                <td data-label="Severity"><span className={`sev ${row.severity}`}>{row.severity}</span></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}

const coverageTone = (rate: number) =>
  rate < 50 ? "var(--bad)" : rate < 80 ? "var(--warn)" : "var(--ok)";

function Reliability({ period, department }: { period: Period; department: string }) {
  const query = useScorecard({ ...period, department });
  if (query.isLoading) return <Busy />;

  const rows = query.data?.results ?? [];
  if (!rows.length) return <Blank title="No activity">Nobody was rostered in this period.</Blank>;

  return (
    <div className="scroll-x">
      <table className="data">
        <thead>
          <tr>
            <th className="num">Rank</th>
            <th>Employee</th>
            <th>Department</th>
            <th className="num">Rostered</th>
            <th className="num">Present</th>
            <th className="num">Late</th>
            <th className="num">No-shows</th>
            <th className="num">Avg late</th>
            <th className="num">Hours</th>
            <th>Attendance</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.employee_id}>
              <td className="num" data-label="Rank" style={row.department_rank === 1 ? { color: "var(--gold-hi)" } : undefined}>
                {row.department_rank}
              </td>
              <td data-label="Employee"><Who name={row.name} sub={row.role} /></td>
              <td data-label="Department">{row.department}</td>
              <td className="num" data-label="Rostered">{row.shifts_scheduled}</td>
              <td className="num" data-label="Present">{row.days_present}</td>
              <td className="num" data-label="Late" style={row.days_late ? { color: "var(--gold-hi)" } : undefined}>
                {row.days_late || "—"}
              </td>
              <td className="num" data-label="No-shows" style={row.no_shows ? { color: "var(--bad)" } : undefined}>
                {row.no_shows || "—"}
              </td>
              <td className="num" data-label="Avg late">{row.avg_minutes_late ? `${row.avg_minutes_late}m` : "—"}</td>
              <td className="num" data-label="Hours">{row.hours_worked.toFixed(1)}</td>
              <td data-label="Attendance">
                <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                  <Bar value={row.attendance_rate} />
                  <span className="mono">{row.attendance_rate}%</span>
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Overtime({ period, threshold }: { period: Period; threshold: number }) {
  const query = useOvertime({ ...period, threshold_hours: threshold });
  if (query.isLoading) return <Busy />;

  const rows = query.data?.results ?? [];
  if (!rows.length) {
    return <Blank title="No overtime">Nobody passed {threshold} hours in a single week.</Blank>;
  }

  return (
    <div className="scroll-x">
      <table className="data">
        <thead>
          <tr>
            <th>Week beginning</th>
            <th>Employee</th>
            <th>Department</th>
            <th className="num">Days</th>
            <th className="num">Hours</th>
            <th className="num">Over</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={`${row.employee_id}-${row.week_starting}`}>
              <td className="num" data-label="Week">{formatDate(row.week_starting)}</td>
              <td data-label="Employee"><Who name={row.name} sub={row.employee_code} /></td>
              <td data-label="Department">{row.department}</td>
              <td className="num" data-label="Days">{row.days_worked}</td>
              <td className="num" data-label="Hours">{row.hours_worked.toFixed(1)}</td>
              <td className="num" data-label="Over" style={{ color: "var(--gold-hi)" }}>+{row.overtime_hours.toFixed(1)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
