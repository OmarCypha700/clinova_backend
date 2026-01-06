from django.urls import path
from .views import SubmitScoreView, SubmitReconciliationView, StudentProcedureScoresView

urlpatterns = [
    path("scores/submit/", SubmitScoreView.as_view()),
    path("scores/reconcile/", SubmitReconciliationView.as_view()),
    path("students/<int:student_id>/procedures/<int:procedure_id>/scores/", StudentProcedureScoresView.as_view()),
]
