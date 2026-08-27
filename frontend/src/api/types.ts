export type Paginated<T> = { count: number; next: string | null; previous: string | null; results: T[] };

export type Department = {
  id: number; name: string; code: string; description: string;
  is_active: boolean; employee_count: number;
};

export type Role = {
  id: number; title: string; code: string; department: number | null;
  department_name: string | null; base_hourly_rate: string; description: string;
  is_active: boolean; employee_count: number;
};

export type Shift = {
  id: number; name: string; code: string; start_time: string; end_time: string;
  break_minutes: number; duration_hours: number; crosses_midnight: boolean; is_active: boolean;
};

export type EmployeeStatus = "active" | "on_leave" | "suspended" | "terminated";

export type Employee = {
  id: number; employee_code: string; first_name: string; last_name: string; full_name: string;
  email: string; phone: string;
  department: number; department_name: string;
  role: number; role_title: string;
  manager: number | null; manager_name: string | null;
  employment_type: string; status: EmployeeStatus;
  hire_date: string; termination_date: string | null;
  hourly_rate: string | null; effective_hourly_rate: string;
};

export type ShiftAssignment = {
  id: number; employee: number; employee_name: string; department_name: string;
  shift: number; shift_name: string; start_time: string; end_time: string;
  date: string; status: "scheduled" | "cancelled"; notes: string;
  attendance_status: AttendanceStatus | null;
};

export type AttendanceStatus = "present" | "late" | "absent" | "on_leave" | "holiday";

export type Attendance = {
  id: number; employee: number; employee_name: string; department_name: string;
  shift_assignment: number | null; shift_name: string | null;
  date: string; check_in: string | null; check_out: string | null;
  status: AttendanceStatus; notes: string;
  worked_minutes: number; worked_hours: number; minutes_late: number; overtime_minutes: number;
};

export type DepartmentSummaryRow = {
  department_id: number; department: string; code: string; headcount: number;
  shifts_scheduled: number; attendance_records: number; present_count: number;
  late_count: number; absent_count: number; attendance_rate: number;
  punctuality_rate: number; hours_worked: number; labour_cost: number;
};

export type CoverageGapRow = {
  date: string; shift_id: number; shift: string; department_id: number; department: string;
  scheduled: number; present: number; late: number; excused_absences: number;
  unexcused_no_shows: number; missing: number; coverage_rate: number;
  severity: "critical" | "high" | "medium" | "low";
};

export type ScorecardRow = {
  employee_id: number; employee_code: string; name: string; department: string; role: string;
  shifts_scheduled: number; days_present: number; days_late: number; days_absent: number;
  no_shows: number; hours_worked: number; avg_minutes_late: number;
  attendance_rate: number; department_rank: number;
};

export type OvertimeRow = {
  week_starting: string; employee_id: number; employee_code: string; name: string;
  department: string; days_worked: number; hours_worked: number;
  overtime_hours: number; threshold_hours: number;
};

export type Dashboard = {
  period: { start: string; end: string };
  total_employees: number; departments: number; shifts: number;
  shifts_scheduled: number; present_count: number; late_count: number; absent_count: number;
  hours_worked: number; attendance_rate: number; open_gaps: number;
  daily_attendance: { date: string; present: number; late: number; absent: number }[];
};

export type ReportEnvelope<T> = { start: string; end: string; results: T[] };
