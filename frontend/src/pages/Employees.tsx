import { useState } from "react";

import { api, ApiError } from "../api/client";
import { useApiMutation, useDepartments, useEmployees, useRoles } from "../api/hooks";
import type { Department, Employee, Role } from "../api/types";
import { useConfirmDelete } from "../components/confirm";
import { PageHeader } from "../components/Shell";
import { Alert, Blank, Busy, Card, Dialog, Field, Who, useSnack } from "../components/ui";
import { formatDate, today } from "../lib/period";

const PAGE_SIZE = 15;

const STATUS = {
  active: "Active",
  on_leave: "On leave",
  suspended: "Suspended",
  terminated: "Terminated",
} as const;

const EMPLOYMENT = {
  full_time: "Full time",
  part_time: "Part time",
  contract: "Contract",
  seasonal: "Seasonal",
} as const;

export function EmployeesPage() {
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [department, setDepartment] = useState("");
  const [status, setStatus] = useState("");
  const [editing, setEditing] = useState<Employee | "new" | null>(null);
  const [assigning, setAssigning] = useState<Employee | null>(null);

  const { say, snack } = useSnack();
  const confirmDelete = useConfirmDelete();

  const departments = useDepartments();
  const roles = useRoles();
  const employees = useEmployees({ page, page_size: PAGE_SIZE, search, department, status });

  const remove = useApiMutation<Employee, void>((e) => api.delete(`/employees/${e.id}/`));

  // Any filter change invalidates the current page number.
  const filter = (set: (v: string) => void) => (value: string) => {
    set(value);
    setPage(1);
  };

  const askDelete = async (employee: Employee) => {
    const ok = await confirmDelete(
      employee.full_name,
      "Their shift assignments and attendance records will be removed too.",
    );
    if (!ok) return;
    remove.mutate(employee, {
      onSuccess: () => say(`${employee.full_name} removed`),
      onError: (error) => say((error as Error).message, true),
    });
  };

  const rows = employees.data?.results ?? [];
  const total = employees.data?.count ?? 0;
  const pages = Math.max(Math.ceil(total / PAGE_SIZE), 1);

  return (
    <>
      <PageHeader title="Employees" note={`${total} on file`}>
        <button className="btn btn-primary" onClick={() => setEditing("new")}>New employee</button>
      </PageHeader>

      <div className="content">
        <Card>
          <div className="card-head">
            <div className="toolbar" style={{ flex: 1 }}>
              <div className="grow">
                <Field label="Search">
                  <input
                    className="input"
                    placeholder="Name, email or staff number"
                    value={search}
                    onChange={(e) => filter(setSearch)(e.target.value)}
                  />
                </Field>
              </div>
              <Field label="Department">
                <select className="select" value={department} onChange={(e) => filter(setDepartment)(e.target.value)}>
                  <option value="">All departments</option>
                  {departments.data?.results.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
                </select>
              </Field>
              <Field label="Status">
                <select className="select" value={status} onChange={(e) => filter(setStatus)(e.target.value)}>
                  <option value="">Any status</option>
                  {Object.entries(STATUS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
                </select>
              </Field>
            </div>
          </div>

          {employees.isLoading ? (
            <Busy text="Loading employees" />
          ) : rows.length === 0 ? (
            <Blank title="No matches">Try a different search or clear the filters.</Blank>
          ) : (
            <div className="scroll-x">
              <table className="data">
                <thead>
                  <tr>
                    <th>Employee</th>
                    <th>Department</th>
                    <th>Role</th>
                    <th>Reports to</th>
                    <th>Status</th>
                    <th className="num">Rate</th>
                    <th className="num">Hired</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {rows.map((employee) => (
                    <tr key={employee.id}>
                      <td data-label="Employee"><Who name={employee.full_name} sub={employee.employee_code} /></td>
                      <td data-label="Department">{employee.department_name}</td>
                      <td className="key" data-label="Role">{employee.role_title}</td>
                      <td data-label="Reports to">{employee.manager_name ?? <span className="muted">—</span>}</td>
                      <td data-label="Status">
                        <span className={`tag ${employee.status === "active" ? "ok" : "off"}`}>
                          <span className="dot" />
                          {STATUS[employee.status]}
                        </span>
                      </td>
                      <td className="num" data-label="Rate">{Number(employee.effective_hourly_rate).toFixed(2)}</td>
                      <td className="num" data-label="Hired">{formatDate(employee.hire_date, { year: "2-digit", month: "short", day: "numeric" })}</td>
                      <td className="row-actions">
                        <button className="btn btn-quiet btn-sm" onClick={() => setAssigning(employee)}>Assign</button>
                        <button className="btn btn-quiet btn-sm" onClick={() => setEditing(employee)}>Edit</button>
                        <button className="btn btn-quiet btn-sm danger" onClick={() => askDelete(employee)}>Delete</button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          <div className="pager">
            <span>Page {page} of {pages}</span>
            <span style={{ display: "flex", gap: 8 }}>
              <button className="btn btn-sm" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>Previous</button>
              <button className="btn btn-sm" disabled={page >= pages} onClick={() => setPage((p) => p + 1)}>Next</button>
            </span>
          </div>
        </Card>
      </div>

      {editing && (
        <EmployeeDialog
          employee={editing === "new" ? null : editing}
          departments={departments.data?.results ?? []}
          roles={roles.data?.results ?? []}
          onClose={() => setEditing(null)}
          onSaved={(name) => say(`${name} saved`)}
        />
      )}

      {assigning && (
        <AssignDialog
          employee={assigning}
          departments={departments.data?.results ?? []}
          roles={roles.data?.results ?? []}
          onClose={() => setAssigning(null)}
          onSaved={(name) => say(`${name} reassigned`)}
        />
      )}

      {snack}
    </>
  );
}

type Lookups = { departments: Department[]; roles: Role[] };

// Hotel-wide roles have no department, so they stay selectable everywhere.
const rolesFor = (roles: Role[], departmentId: string) =>
  roles.filter((r) => !r.department || r.department === Number(departmentId));

function EmployeeDialog({ employee, departments, roles, onClose, onSaved }: Lookups & {
  employee: Employee | null;
  onClose: () => void;
  onSaved: (name: string) => void;
}) {
  const [form, setForm] = useState({
    first_name: employee?.first_name ?? "",
    last_name: employee?.last_name ?? "",
    email: employee?.email ?? "",
    phone: employee?.phone ?? "",
    department: String(employee?.department ?? departments[0]?.id ?? ""),
    role: String(employee?.role ?? ""),
    employment_type: employee?.employment_type ?? "full_time",
    status: String(employee?.status ?? "active"),
    hire_date: employee?.hire_date ?? today(),
    hourly_rate: employee?.hourly_rate ?? "",
  });
  const [errors, setErrors] = useState<Record<string, string[]> | null>(null);

  const save = useApiMutation<typeof form, Employee>((body) => {
    const payload = { ...body, hourly_rate: body.hourly_rate === "" ? null : body.hourly_rate };
    return employee
      ? api.patch<Employee>(`/employees/${employee.id}/`, payload)
      : api.post<Employee>("/employees/", payload);
  });

  const set = (key: keyof typeof form) => (value: string) =>
    setForm((current) => ({ ...current, [key]: value }));

  const submit = () =>
    save.mutate(form, {
      onSuccess: (saved) => {
        onSaved(saved.full_name);
        onClose();
      },
      onError: (error) =>
        setErrors(error instanceof ApiError ? error.fields : { detail: [String(error)] }),
    });

  return (
    <Dialog
      title={employee ? `Edit ${employee.full_name}` : "New employee"}
      onClose={onClose}
      footer={
        <>
          <button className="btn" onClick={onClose}>Cancel</button>
          <button className="btn btn-primary" disabled={save.isPending} onClick={submit}>
            {save.isPending ? "Saving" : "Save"}
          </button>
        </>
      }
    >
      <Alert fields={errors} />

      <div className="pair">
        <Field label="First name">
          <input className="input" value={form.first_name} onChange={(e) => set("first_name")(e.target.value)} />
        </Field>
        <Field label="Last name">
          <input className="input" value={form.last_name} onChange={(e) => set("last_name")(e.target.value)} />
        </Field>
      </div>

      <div className="pair">
        <Field label="Email">
          <input className="input" type="email" value={form.email} onChange={(e) => set("email")(e.target.value)} />
        </Field>
        <Field label="Phone">
          <input className="input" value={form.phone} onChange={(e) => set("phone")(e.target.value)} />
        </Field>
      </div>

      <div className="pair">
        <Field label="Department">
          <select
            className="select"
            value={form.department}
            onChange={(e) => setForm((c) => ({ ...c, department: e.target.value, role: "" }))}
          >
            {departments.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
          </select>
        </Field>
        <Field label="Role">
          <select className="select" value={form.role} onChange={(e) => set("role")(e.target.value)}>
            <option value="">Select a role</option>
            {rolesFor(roles, form.department).map((r) => (
              <option key={r.id} value={r.id}>{r.title}{r.department ? "" : " (hotel-wide)"}</option>
            ))}
          </select>
        </Field>
      </div>

      <div className="pair">
        <Field label="Employment type">
          <select className="select" value={form.employment_type} onChange={(e) => set("employment_type")(e.target.value)}>
            {Object.entries(EMPLOYMENT).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
          </select>
        </Field>
        <Field label="Status">
          <select className="select" value={form.status} onChange={(e) => set("status")(e.target.value)}>
            {Object.entries(STATUS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
          </select>
        </Field>
      </div>

      <div className="pair">
        <Field label="Hire date">
          <input className="input" type="date" value={form.hire_date} onChange={(e) => set("hire_date")(e.target.value)} />
        </Field>
        <Field label="Hourly rate">
          <input
            className="input"
            type="number"
            step="0.01"
            placeholder="Role base rate"
            value={form.hourly_rate ?? ""}
            onChange={(e) => set("hourly_rate")(e.target.value)}
          />
        </Field>
      </div>
    </Dialog>
  );
}

function AssignDialog({ employee, departments, roles, onClose, onSaved }: Lookups & {
  employee: Employee;
  onClose: () => void;
  onSaved: (name: string) => void;
}) {
  const [department, setDepartment] = useState(String(employee.department));
  const [role, setRole] = useState(String(employee.role));
  const [errors, setErrors] = useState<Record<string, string[]> | null>(null);

  const assign = useApiMutation<{ department: number; role: number }, Employee>((body) =>
    api.post<Employee>(`/employees/${employee.id}/assign/`, body),
  );

  const submit = () =>
    assign.mutate(
      { department: Number(department), role: Number(role) },
      {
        onSuccess: (saved) => {
          onSaved(saved.full_name);
          onClose();
        },
        onError: (error) =>
          setErrors(error instanceof ApiError ? error.fields : { detail: [String(error)] }),
      },
    );

  return (
    <Dialog
      title={`Assign ${employee.full_name}`}
      lede={`Currently ${employee.role_title} in ${employee.department_name}.`}
      onClose={onClose}
      footer={
        <>
          <button className="btn" onClick={onClose}>Cancel</button>
          <button className="btn btn-primary" disabled={assign.isPending || !role} onClick={submit}>
            {assign.isPending ? "Assigning" : "Confirm"}
          </button>
        </>
      }
    >
      <Alert fields={errors} />

      <Field label="Department">
        <select
          className="select"
          value={department}
          onChange={(e) => {
            setDepartment(e.target.value);
            setRole("");
          }}
        >
          {departments.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
        </select>
      </Field>

      <Field label="Role">
        <select className="select" value={role} onChange={(e) => setRole(e.target.value)}>
          <option value="">Select a role</option>
          {rolesFor(roles, department).map((r) => (
            <option key={r.id} value={r.id}>{r.title}{r.department ? "" : " (hotel-wide)"}</option>
          ))}
        </select>
      </Field>
    </Dialog>
  );
}
