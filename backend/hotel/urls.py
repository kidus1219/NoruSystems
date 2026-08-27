from django.urls import path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("departments", views.DepartmentViewSet, basename="department")
router.register("roles", views.RoleViewSet, basename="role")
router.register("shifts", views.ShiftViewSet, basename="shift")
router.register("employees", views.EmployeeViewSet, basename="employee")
router.register("shift-assignments", views.ShiftAssignmentViewSet, basename="shiftassignment")
router.register("attendance", views.AttendanceViewSet, basename="attendance")

urlpatterns = router.urls + [
    path("reports/<str:name>/", views.report_view, name="report"),
]
