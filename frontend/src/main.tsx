import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Route, Routes } from "react-router-dom";

import "./styles.css";
import { ConfirmProvider } from "./components/confirm";
import { Shell } from "./components/Shell";
import { AttendancePage } from "./pages/Attendance";
import { EmployeesPage } from "./pages/Employees";
import { OverviewPage } from "./pages/Overview";
import { ReportsPage } from "./pages/Reports";
import { SchedulingPage } from "./pages/Scheduling";

const queryClient = new QueryClient({
  defaultOptions: { queries: { refetchOnWindowFocus: false, staleTime: 15_000 } },
});

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <ConfirmProvider>
        <BrowserRouter>
          <Routes>
            <Route element={<Shell />}>
              <Route index element={<OverviewPage />} />
              <Route path="employees" element={<EmployeesPage />} />
              <Route path="scheduling" element={<SchedulingPage />} />
              <Route path="attendance" element={<AttendancePage />} />
              <Route path="reports" element={<ReportsPage />} />
            </Route>
          </Routes>
        </BrowserRouter>
      </ConfirmProvider>
    </QueryClientProvider>
  </StrictMode>,
);
