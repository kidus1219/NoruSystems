import { Link } from "react-router-dom";

import { useCoverageGaps, useDashboard, useDepartmentSummary } from "../api/hooks";
import { AttendanceChart } from "../components/AttendanceChart";
import { PageHeader } from "../components/Shell";
import { Stat } from "../components/Stat";
import { Bar, Blank, Busy, Card, Field } from "../components/ui";
import { formatDate, usePeriod } from "../lib/period";

export function OverviewPage() {
  const { period, setStart, setEnd } = usePeriod();
  const dashboard = useDashboard(period);
  const summary = useDepartmentSummary(period);
  const gaps = useCoverageGaps(period);

  const data = dashboard.data;
  const worst = [...(gaps.data?.results ?? [])]
    .sort((a, b) => b.missing - a.missing || a.coverage_rate - b.coverage_rate)
    .slice(0, 6);

  return (
    <>
      <PageHeader
        title="Overview"
        note={`${formatDate(period.start)} to ${formatDate(period.end)}`}
      >
        <div className="toolbar">
          <Field label="From">
            <input className="input" type="date" value={period.start} onChange={(e) => setStart(e.target.value)} />
          </Field>
          <Field label="To">
            <input className="input" type="date" value={period.end} onChange={(e) => setEnd(e.target.value)} />
          </Field>
        </div>
      </PageHeader>

      <div className="content">
        {!data ? (
          <Busy text="Loading the overview" />
        ) : (
          <>
            <div className="stats">
              <Stat label="Active staff" value={data.total_employees} note={`Across ${data.departments} departments`} />
              <Stat label="Shifts rostered" value={data.shifts_scheduled} note={`${data.shifts} shift patterns`} />
              <Stat label="Attendance" value={data.attendance_rate} unit="%" note={`${data.present_count} of ${data.shifts_scheduled} covered`} />
              <Stat label="Late arrivals" value={data.late_count} note={`${data.absent_count} absences logged`} />
              <Stat label="Hours worked" value={data.hours_worked.toLocaleString()} note="Net of unpaid breaks" />
              <Stat label="Coverage gaps" value={data.open_gaps} note="Shifts that ran short" />
            </div>

            <div className="grid-2">
              <Card title="Attendance by day" note="Rostered outcomes, stacked">
                <AttendanceChart data={data.daily_attendance} />
              </Card>

              <Card
                title="Biggest coverage gaps"
                note="Rostered but not covered"
                actions={<Link className="btn btn-sm" to="/reports">See all</Link>}
              >
                {gaps.isLoading ? (
                  <Busy />
                ) : worst.length === 0 ? (
                  <Blank title="Fully covered">Every rostered shift was worked.</Blank>
                ) : (
                  <div className="scroll-x">
                    <table className="data">
                      <thead>
                        <tr>
                          <th>Date</th>
                          <th>Shift</th>
                          <th>Department</th>
                          <th className="num">Short</th>
                        </tr>
                      </thead>
                      <tbody>
                        {worst.map((gap) => (
                          <tr key={`${gap.date}-${gap.shift_id}-${gap.department_id}`}>
                            <td className="num" data-label="Date">{formatDate(gap.date)}</td>
                            <td className="key" data-label="Shift">{gap.shift}</td>
                            <td data-label="Department">{gap.department}</td>
                            <td className="num" data-label="Short">
                              <span className={`sev ${gap.severity}`}>{gap.missing} of {gap.scheduled}</span>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </Card>
            </div>

            <Card title="Departments" note="Staffing and attendance for the period">
              {summary.isLoading ? (
                <Busy />
              ) : (
                <div className="scroll-x">
                  <table className="data">
                    <thead>
                      <tr>
                        <th>Department</th>
                        <th className="num">Staff</th>
                        <th className="num">Rostered</th>
                        <th className="num">Covered</th>
                        <th>Attendance</th>
                        <th className="num">Punctuality</th>
                        <th className="num">Hours</th>
                        <th className="num">Labour cost</th>
                      </tr>
                    </thead>
                    <tbody>
                      {summary.data?.results.map((row) => (
                        <tr key={row.department_id}>
                          <td className="key">{row.department}</td>
                          <td className="num">{row.headcount}</td>
                          <td className="num">{row.shifts_scheduled}</td>
                          <td className="num">{row.present_count}</td>
                          <td>
                            <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                              <Bar value={row.attendance_rate} />
                              <span className="mono">{row.attendance_rate}%</span>
                            </div>
                          </td>
                          <td className="num">{row.punctuality_rate}%</td>
                          <td className="num">{row.hours_worked.toLocaleString()}</td>
                          <td className="num">{row.labour_cost.toLocaleString(undefined, { maximumFractionDigits: 0 })}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </Card>
          </>
        )}
      </div>
    </>
  );
}
