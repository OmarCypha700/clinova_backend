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
    StudentGradesView,
    ProgramViewSet,
    ImportStudentsView,
    DownloadStudentTemplateView,
    ImportProceduresView,
    DownloadProcedureTemplateView,
    ImportProcedureStepsView,
    DownloadProcedureStepsTemplateView,
    BulkDeleteProceduresView,
    BulkDeleteStudentsView,
    CarePlanView,
)

# Router for viewsets
router = DefaultRouter()
router.register(r'admin/examiners', ExaminerViewSet, basename='examiner')
router.register(r'admin/programs', ProgramViewSet, basename='admin-program')
router.register(r'admin/students', StudentViewSet, basename='admin-student')
router.register(r'admin/procedures', ProcedureViewSet, basename='admin-procedure')
router.register(r'admin/procedure-steps', ProcedureStepViewSet, basename='admin-procedure-step')

urlpatterns = [
    # Standard endpoints (BEFORE router)
    path("programs/", ProgramListView.as_view()),
    path("programs/<int:program_id>/students/", StudentByProgramView.as_view()),
    path("programs/<int:program_id>/procedures/", ProcedureByProgramView.as_view()),
    path("students/<int:pk>/", StudentDetailView.as_view()),
    path("students/<int:student_id>/procedures/<int:pk>/", ProcedureDetailView.as_view()),
    path("autosave-step-score/", AutosaveStepScoreView.as_view()),

    # Student import/export
    path("students/import/", ImportStudentsView.as_view(), name='import-students'),
    path("students/template/", DownloadStudentTemplateView.as_view(), name='student-template'),
    path("students/bulk-delete/", BulkDeleteStudentsView.as_view(), name='bulk-delete-students'),

    # Care Plan
    path("students/<int:student_id>/programs/<int:program_id>/care-plan/", 
         CarePlanView.as_view(), name='care-plan'),
    
    # Reconciliation
    path("students/<int:student_id>/procedures/<int:procedure_id>/reconciliation/", 
         ReconciliationView.as_view()),
    path("save-reconciliation/", SaveReconciliationView.as_view()),
    
    # Admin dashboard
    path("dashboard-stats/", DashboardStatsView.as_view()),
    
    # Grades
    path("grades/", StudentGradesView.as_view(), name='student-grades'),

    # Procedure import/template
    path("procedures/import/", ImportProceduresView.as_view(), name='import-procedures'),
    path("procedures/template/", DownloadProcedureTemplateView.as_view(), name='procedure-template'),
    path("procedures/bulk-delete/", BulkDeleteProceduresView.as_view(), name='bulk-delete-procedures'),

    
    # Procedure Steps Import/Export
    path("procedures/<int:procedure_id>/steps/import/", 
         ImportProcedureStepsView.as_view(), name='import-procedure-steps'),
    path("procedures/<int:procedure_id>/steps/template/", 
         DownloadProcedureStepsTemplateView.as_view(), name='procedure-steps-template'),

    # Router URLs LAST
    path('', include(router.urls)),
]