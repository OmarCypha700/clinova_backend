from rest_framework import serializers
from .models import Score

class ScoreCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Score
        fields = [
            "student",
            "procedure_step",
            "score",
        ]

    def create(self, validated_data):
        user = self.context["request"].user
        validated_data["examiner"] = user
        validated_data["score_type"] = "examiner"
        return super().create(validated_data)


class ReconciliationScoreSerializer(serializers.ModelSerializer):
    class Meta:
        model = Score
        fields = [
            "student",
            "procedure_step",
            "score",
        ]

    def create(self, validated_data):
        user = self.context["request"].user
        validated_data["examiner"] = user
        validated_data["score_type"] = "final"
        return super().create(validated_data)


class ScoreReadSerializer(serializers.ModelSerializer):
    examiner = serializers.StringRelatedField()
    procedure_step = serializers.StringRelatedField()

    class Meta:
        model = Score
        fields = [
            "id",
            "examiner",
            "procedure_step",
            "score",
            "score_type",
            "created_at",
        ]
