"""Admin config. Usable as a fallback back office."""

from django.contrib import admin

from .models import Attendance, Department, Employee, Role, Shift, ShiftAssignment


class RoleInline(admin.TabularInline):
    model = Role
    extra = 0
    fields = ["title", "code", "base_hourly_rate", "is_active"]


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ["name", "code", "headcount", "is_active"]
    search_fields = ["name", "code"]
    list_filter = ["is_active"]
    inlines = [RoleInline]

    @admin.display(description="Active staff")
    def headcount(self, obj):
        return obj.employees.filter(status=Employee.Status.ACTIVE).count()


@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    list_display = ["title", "code", "department", "base_hourly_rate", "is_active"]
    list_filter = ["department", "is_active"]
    search_fields = ["title", "code"]


@admin.register(Shift)
class ShiftAdmin(admin.ModelAdmin):
    list_display = ["name", "code", "start_time", "end_time", "duration_hours", "crosses_midnight", "is_active"]
    list_filter = ["is_active"]

    @admin.display(boolean=True, description="Overnight")
    def crosses_midnight(self, obj):
        return obj.crosses_midnight


@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = ["employee_code", "full_name", "department", "role", "status", "hire_date"]
    list_filter = ["department", "role", "status", "employment_type"]
    search_fields = ["first_name", "last_name", "email", "employee_code"]
    autocomplete_fields = ["manager", "department", "role"]
    readonly_fields = ["employee_code", "created_at", "updated_at"]
    list_select_related = ["department", "role"]


@admin.register(ShiftAssignment)
class ShiftAssignmentAdmin(admin.ModelAdmin):
    list_display = ["date", "employee", "shift", "status"]
    list_filter = ["status", "shift", "date", "employee__department"]
    search_fields = ["employee__first_name", "employee__last_name"]
    autocomplete_fields = ["employee"]
    date_hierarchy = "date"
    list_select_related = ["employee", "shift"]


@admin.register(Attendance)
class AttendanceAdmin(admin.ModelAdmin):
    list_display = ["date", "employee", "status", "check_in", "check_out", "worked_hours", "minutes_late"]
    list_filter = ["status", "date", "employee__department"]
    search_fields = ["employee__first_name", "employee__last_name", "employee__employee_code"]
    autocomplete_fields = ["employee", "shift_assignment"]
    readonly_fields = ["worked_minutes", "minutes_late"]
    date_hierarchy = "date"
    list_select_related = ["employee"]

    @admin.display(description="Hours")
    def worked_hours(self, obj):
        return obj.worked_hours
