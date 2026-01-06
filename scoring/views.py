from .models import Score
from rest_framework.generics import CreateAPIView, ListAPIView
from .serializers import ScoreCreateSerializer, ReconciliationScoreSerializer, ScoreReadSerializer

class SubmitScoreView(CreateAPIView):
    serializer_class = ScoreCreateSerializer


class SubmitReconciliationView(CreateAPIView):
    serializer_class = ReconciliationScoreSerializer


class StudentProcedureScoresView(ListAPIView):
    serializer_class = ScoreReadSerializer

    def get_queryset(self):
        student_id = self.kwargs["student_id"]
        procedure_id = self.kwargs["procedure_id"]

        return Score.objects.filter(
            student_id=student_id,
            procedure_step__procedure_id=procedure_id
        )
