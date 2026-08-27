import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, qs } from "./client";
import type {
  Attendance, Dashboard, Department, Employee, Paginated, ReportEnvelope,
  Role, Shift, ShiftAssignment, CoverageGapRow, DepartmentSummaryRow,
  OvertimeRow, ScorecardRow,
} from "./types";

type Params = Record<string, string | number | boolean | undefined | null>;

const list = <T>(resource: string, params: Params = {}) => ({
  queryKey: [resource, params],
  queryFn: () => api.get<Paginated<T>>(`/${resource}/${qs(params)}`),
});

export const useDepartments = (params: Params = { page_size: 100 }) =>
  useQuery(list<Department>("departments", params));

export const useRoles = (params: Params = { page_size: 100 }) => useQuery(list<Role>("roles", params));

export const useShifts = (params: Params = { page_size: 100 }) => useQuery(list<Shift>("shifts", params));

export const useEmployees = (params: Params) => useQuery(list<Employee>("employees", params));

export const useAssignments = (params: Params) => useQuery(list<ShiftAssignment>("shift-assignments", params));

export const useAttendance = (params: Params) => useQuery(list<Attendance>("attendance", params));

const report = <T>(name: string, params: Params) => ({
  queryKey: ["report", name, params],
  queryFn: () => api.get<ReportEnvelope<T>>(`/reports/${name}/${qs(params)}`),
});

export const useDepartmentSummary = (params: Params) =>
  useQuery(report<DepartmentSummaryRow>("department-summary", params));

export const useCoverageGaps = (params: Params) => useQuery(report<CoverageGapRow>("coverage-gaps", params));

export const useScorecard = (params: Params) => useQuery(report<ScorecardRow>("employee-scorecard", params));

export const useOvertime = (params: Params) => useQuery(report<OvertimeRow>("overtime", params));

export const useDashboard = (params: Params) =>
  useQuery({
    queryKey: ["report", "dashboard", params],
    queryFn: () => api.get<Dashboard>(`/reports/dashboard/${qs(params)}`),
  });

/** Blunt invalidation. The reports touch nearly every table and this is a back
 *  office tool, so a few extra refetches are cheaper than stale numbers. */
export function useApiMutation<TVars, TData>(fn: (vars: TVars) => Promise<TData>) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: fn,
    onSuccess: () => queryClient.invalidateQueries(),
  });
}
