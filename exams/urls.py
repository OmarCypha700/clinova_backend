# from django.urls import path
# from .views import (
#     ProgramListView,
#     StudentByProgramView,
#     ProcedureByProgramView,
#     ProcedureDetailView,
#     AutosaveStepScoreView,
#     ReconciliationView,
#     SaveReconciliationView,
#     AssignExaminersView,
#     StudentDetailView,
# )

# urlpatterns = [
#     path("programs/", ProgramListView.as_view()),
#     path("programs/<int:program_id>/students/", StudentByProgramView.as_view()),
#     path("programs/<int:program_id>/procedures/", ProcedureByProgramView.as_view()),

#     path(
#         "students/<int:student_id>/procedures/<int:pk>/",
#         ProcedureDetailView.as_view()
#     ),

#     path("students/<int:pk>/", StudentDetailView.as_view(), name='student-detail'),

#     path(
#         "autosave-step-score/",
#         AutosaveStepScoreView.as_view()
#     ),
    
#     # Reconciliation endpoints
#     path(
#         "students/<int:student_id>/procedures/<int:procedure_id>/reconciliation/",
#         ReconciliationView.as_view(),
#         name='reconciliation'
#     ),
    
#     path(
#         "save-reconciliation/",
#         SaveReconciliationView.as_view(),
#         name='save-reconciliation'
#     ),
    
#     path(
#         "assign-examiners/",
#         AssignExaminersView.as_view(),
#         name='assign-examiners'
#     ),
# ]

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    ProgramListView,
    StudentByProgramView,
    ProcedureByProgramView,
    ProcedureDetailView,
    AutosaveStepScoreView,
    ReconciliationView,
    SaveReconciliationView,
    StudentDetailView,
    DashboardStatsView,
    ExaminerViewSet,
    StudentViewSet,
    ProcedureViewSet,
    ProcedureStepViewSet,
    ProgramViewSet,
)

# Create router for viewsets
router = DefaultRouter()
router.register(r'admin/examiners', ExaminerViewSet, basename='examiner')
router.register(r'admin/students', StudentViewSet, basename='admin-student')
router.register(r'admin/procedures', ProcedureViewSet, basename='admin-procedure')
router.register(r'admin/procedure-steps', ProcedureStepViewSet, basename='admin-procedure-step')
router.register(r'programs', ProgramViewSet, basename='program')

urlpatterns = [
    # Include router URLs
    path('', include(router.urls)),
    
    # Existing endpoints
    path("programs/", ProgramListView.as_view()),
    path("programs/<int:program_id>/students/", StudentByProgramView.as_view()),
    path("programs/<int:program_id>/procedures/", ProcedureByProgramView.as_view()),
    path("students/<int:pk>/", StudentDetailView.as_view(), name='student-detail'),
    path("students/<int:student_id>/procedures/<int:pk>/", ProcedureDetailView.as_view()),
    path("autosave-step-score/", AutosaveStepScoreView.as_view()),
    
    # Reconciliation
    path("students/<int:student_id>/procedures/<int:procedure_id>/reconciliation/", 
         ReconciliationView.as_view(), name='reconciliation'),
    path("save-reconciliation/", SaveReconciliationView.as_view(), name='save-reconciliation'),
    
    # Dashboard
    path("admin/dashboard-stats/", DashboardStatsView.as_view(), name='dashboard-stats'),
]