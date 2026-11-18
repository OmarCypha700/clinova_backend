# Procedure.total_score is now derived (steps x 4) instead of typed in.
# This makes the field non-editable and brings every existing procedure in
# line with its steps, so percentages and grades use the right maximum.

from django.db import migrations, models
from django.db.models import Count

POINTS_PER_STEP = 4  # frozen copy: migrations must not import app code


def recalculate_totals(apps, schema_editor):
    Procedure = apps.get_model("exams", "Procedure")
    for proc in Procedure.objects.annotate(n=Count("steps")).only("id", "total_score"):
        expected = proc.n * POINTS_PER_STEP
        if proc.total_score != expected:
            Procedure.objects.filter(pk=proc.pk).update(total_score=expected)


class Migration(migrations.Migration):

    dependencies = [
        ("exams", "0009_site_settings_brand_color"),
    ]

    operations = [
        migrations.AlterField(
            model_name="procedure",
            name="total_score",
            field=models.PositiveIntegerField(default=0, editable=False),
        ),
        # Old totals can't be recovered, but nothing needs them: reversing
        # keeps the recalculated values.
        migrations.RunPython(recalculate_totals, migrations.RunPython.noop),
    ]
