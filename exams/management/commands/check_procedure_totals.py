"""
Read-only report: which procedures have a total score that doesn't match
their steps (steps x 4), and whose grades would change when migration 0010
recalculates them.

Run it BEFORE `migrate` on each institution, either on the server:

    python manage.py check_procedure_totals

or on a copy of an institution's database file:

    python manage.py check_procedure_totals --db path/to/copy.sqlite3

Add --students to list every affected student, not only grade changes.
It only reads; it never changes the database.
"""

from collections import defaultdict
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import connections
from django.db.models import Count, Sum

from exams.grading import grade_for, percentage
from exams.models import POINTS_PER_STEP, CarePlan, Procedure, Student, StudentProcedure


class Command(BaseCommand):
    help = (
        "Read-only: list procedures whose total score doesn't equal steps x 4, "
        "and show how students' grades would change when it's recalculated."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--db",
            metavar="PATH",
            help="Check this SQLite database file (e.g. a copy of production) instead of the configured one.",
        )
        parser.add_argument(
            "--students",
            action="store_true",
            help="List every affected student, including those whose percentage changes but grade doesn't.",
        )

    def handle(self, *args, **opts):
        if opts["db"]:
            path = Path(opts["db"]).expanduser().resolve()
            if not path.is_file():
                raise CommandError(f"Database file not found: {path}")
            conn = connections["default"]
            conn.close()
            conn.settings_dict["NAME"] = str(path)
            self.stdout.write(f"Database: {path}\n")

        procs = list(
            Procedure.objects.select_related("program")
            .annotate(n_steps=Count("steps", distinct=True))
            .order_by("program__name", "name")
        )
        mismatched = [p for p in procs if p.total_score != p.n_steps * POINTS_PER_STEP]

        self.stdout.write(self.style.MIGRATE_HEADING("Procedure totals"))
        self.stdout.write(
            f"  {len(procs)} procedures checked, {len(mismatched)} with a total "
            f"that doesn't equal steps x {POINTS_PER_STEP}."
        )
        if not mismatched:
            self.stdout.write(self.style.SUCCESS("\nNothing will change. Safe to migrate."))
            return

        reconciled = dict(
            StudentProcedure.objects.filter(
                procedure__in=mismatched, status="reconciled"
            )
            .values_list("procedure_id")
            .annotate(c=Count("id"))
        )
        self.stdout.write("")
        for p in mismatched:
            new = p.n_steps * POINTS_PER_STEP
            note = f"{reconciled.get(p.id, 0)} reconciled" if reconciled.get(p.id) else "not reconciled by anyone yet"
            self.stdout.write(
                f"  - {p.name} ({p.program.name}): {p.total_score} -> {new} "
                f"({p.n_steps} steps)  [{note}]"
            )

        self._grade_impact({p.id for p in mismatched}, opts["students"])

    # ── grade impact ────────────────────────────────────────────────────────

    def _grade_impact(self, mismatched_ids, list_all):
        new_total = {
            p.id: p.n_steps * POINTS_PER_STEP
            for p in Procedure.objects.annotate(n_steps=Count("steps", distinct=True))
        }

        # Only students with a reconciled mismatched procedure can change.
        # Inactive students are left out, as on the Grades page.
        affected = Student.objects.filter(
            is_active=True,
            studentprocedure__status="reconciled",
            studentprocedure__procedure_id__in=mismatched_ids,
        ).distinct()

        rows = (
            StudentProcedure.objects.filter(status="reconciled", student__in=affected)
            .values("student_id", "procedure_id", "procedure__total_score")
            .annotate(score=Sum("reconciled_scores__score"))
        )
        per_student = defaultdict(lambda: {"score": 0, "old_max": 0, "new_max": 0})
        for r in rows:
            s = per_student[r["student_id"]]
            s["score"] += r["score"] or 0
            s["old_max"] += r["procedure__total_score"]
            s["new_max"] += new_total[r["procedure_id"]]

        care = {
            r["student"]: (r["score"] or 0, r["max"] or 0)
            for r in CarePlan.objects.filter(student__in=affected)
            .values("student")
            .annotate(score=Sum("score"), max=Sum("max_score"))
        }

        changes = []
        for st in affected.order_by("program__name", "index_number"):
            s = per_student[st.id]
            cp_score, cp_max = care.get(st.id, (0, 0))
            total = s["score"] + cp_score
            before = percentage(total, s["old_max"] + cp_max)
            after = percentage(total, s["new_max"] + cp_max)
            if before != after:
                changes.append((st, before, after, grade_for(before), grade_for(after)))

        grade_changes = [c for c in changes if c[3] != c[4]]

        self.stdout.write("")
        self.stdout.write(self.style.MIGRATE_HEADING("Effect on grades (active students)"))
        self.stdout.write(
            f"  {len(changes)} students' percentages change; "
            f"{len(grade_changes)} of them change grade."
        )
        shown = changes if list_all else grade_changes
        if shown:
            self.stdout.write("")
            for st, before, after, g_before, g_after in shown:
                grade = f"{g_before} -> {g_after}" if g_before != g_after else g_after
                line = f"  - {st.index_number}  {st.full_name}: {before}% -> {after}%  ({grade})"
                self.stdout.write(
                    self.style.WARNING(line) if g_before != g_after else line
                )
        if not list_all and len(changes) > len(grade_changes):
            self.stdout.write(
                f"\n  Run with --students to also list the "
                f"{len(changes) - len(grade_changes)} percentage-only changes."
            )
        self.stdout.write(
            "\nNothing was changed. Migration 0010 applies these totals when you run `migrate`."
        )
