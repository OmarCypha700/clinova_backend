import csv
import io
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from openpyxl import Workbook, load_workbook
from rest_framework.test import APIClient

from accounts.models import User

from .models import (
    CarePlan,
    CarePlanEligibility,
    Category,
    Level,
    Procedure,
    ProcedureStep,
    ProcedureStepScore,
    Program,
    ReconciledScore,
    SiteSettings,
    Student,
    StudentProcedure,
)


class SecondCarePlanTests(TestCase):
    def setUp(self):
        self.program = Program.objects.create(name="General Nursing", abbreviation="RGN")
        self.other_program = Program.objects.create(name="Midwifery", abbreviation="RM")
        self.level = Level.objects.create(number=300, name="Level 300")
        self.other_level = Level.objects.create(number=200, name="Level 200")
        self.student = Student.objects.create(
            index_number="S001", full_name="Test Student", program=self.program, level=self.level
        )
        self.examiner = User.objects.create_user(username="ama", password="x", role="examiner")
        self.admin = User.objects.create_user(username="boss", password="x", role="admin")
        self.client = APIClient()
        self.client.force_authenticate(self.examiner)
        self.url = f"/api/exams/students/{self.student.id}/programs/{self.program.id}/care-plan"

    def enable(self, *rules):
        s = SiteSettings.get()
        s.multiple_care_plans_enabled = True
        s.save()
        for program, level in rules:
            CarePlanEligibility.objects.create(program=program, level=level)

    def test_get_lists_care_plans_and_eligibility(self):
        res = self.client.get(self.url)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["care_plans"], [])
        self.assertFalse(res.data["can_add_second"])

    def test_second_rejected_when_flag_off(self):
        self.client.post(self.url, {"score": 15})
        res = self.client.post(self.url, {"score": 10, "slot": 2})
        self.assertEqual(res.status_code, 400)
        self.assertEqual(CarePlan.objects.count(), 1)

    def test_second_rejected_when_ineligible(self):
        self.enable((self.other_program, None), (self.program, self.other_level))
        self.client.post(self.url, {"score": 15})
        res = self.client.post(self.url, {"score": 10, "slot": 2})
        self.assertEqual(res.status_code, 400)

    def test_second_rejected_before_first(self):
        self.enable()
        res = self.client.post(self.url, {"score": 10, "slot": 2})
        self.assertEqual(res.status_code, 400)

    def test_second_accepted_when_eligible(self):
        self.enable((self.program, self.level))
        self.assertEqual(self.client.post(self.url, {"score": 15}).status_code, 201)
        res = self.client.post(self.url, {"score": 18, "slot": 2})
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.data["slot"], 2)
        data = self.client.get(self.url).data
        self.assertEqual([c["slot"] for c in data["care_plans"]], [1, 2])
        self.assertTrue(data["can_add_second"])

    def test_all_levels_rule_and_empty_list(self):
        self.enable((self.program, None))
        self.assertTrue(SiteSettings.get().allows_second_care_plan(self.student))
        CarePlanEligibility.objects.all().delete()
        self.assertTrue(SiteSettings.get().allows_second_care_plan(self.student))

    def test_duplicate_slot_rejected_and_score_validated(self):
        self.enable()
        self.client.post(self.url, {"score": 15})
        self.client.post(self.url, {"score": 15, "slot": 2})
        self.assertEqual(self.client.post(self.url, {"score": 12, "slot": 2}).status_code, 400)
        self.assertEqual(self.client.post(self.url, {"score": 21}).status_code, 400)
        self.assertEqual(self.client.post(self.url, {"score": 5, "slot": 3}).status_code, 400)
        self.assertEqual(CarePlan.objects.count(), 2)

    def test_grades_total_out_of_40_and_zero_counts(self):
        self.enable()
        self.client.post(self.url, {"score": 0})
        self.client.post(self.url, {"score": 18, "slot": 2})
        self.client.force_authenticate(self.admin)
        res = self.client.get("/api/exams/grades")
        row = res.data["results"][0]
        self.assertEqual(row["care_plan_score"], 18)
        self.assertEqual(row["care_plan_max_score"], 40)
        self.assertEqual(row["care_plan_count"], 2)
        self.assertTrue(row["care_plan_completed"])
        self.assertEqual(row["max_score"], 40)

    def test_admin_settings_patch_eligibility(self):
        self.client.force_authenticate(self.admin)
        res = self.client.patch(
            "/api/exams/settings",
            {
                "multiple_care_plans_enabled": True,
                "care_plan_eligibility": [
                    {"program": self.program.id, "level": self.level.id},
                    {"program": self.other_program.id, "level": None},
                ],
            },
            format="json",
        )
        self.assertEqual(res.status_code, 200, res.data)
        self.assertTrue(res.data["multiple_care_plans_enabled"])
        self.assertEqual(len(res.data["care_plan_eligibility"]), 2)
        # Replacing the list removes old rows
        res = self.client.patch(
            "/api/exams/settings", {"care_plan_eligibility": []}, format="json"
        )
        self.assertEqual(res.data["care_plan_eligibility"], [])

    def test_admin_settings_add_to_existing_eligibility(self):
        """Saving the full list again (existing rows + a new one) must succeed."""
        self.client.force_authenticate(self.admin)
        url = "/api/exams/settings"
        first = {"program": self.program.id, "level": self.level.id}
        res = self.client.patch(url, {"care_plan_eligibility": [first]}, format="json")
        self.assertEqual(res.status_code, 200, res.data)
        res = self.client.patch(
            url,
            {
                "care_plan_eligibility": [
                    first,
                    {"program": self.program.id, "level": self.other_level.id},
                    {"program": self.other_program.id, "level": None},
                ]
            },
            format="json",
        )
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual(len(res.data["care_plan_eligibility"]), 3)
        self.assertEqual(CarePlanEligibility.objects.count(), 3)
        # Duplicates within the submitted list are still rejected
        res = self.client.patch(
            url, {"care_plan_eligibility": [first, first]}, format="json"
        )
        self.assertEqual(res.status_code, 400)
        self.assertEqual(CarePlanEligibility.objects.count(), 3)

    def test_examiner_cannot_patch_settings(self):
        res = self.client.patch(
            "/api/exams/settings", {"multiple_care_plans_enabled": True}, format="json"
        )
        self.assertEqual(res.status_code, 403)


class AdminStudentProcedureTests(TestCase):
    URL = "/api/exams/admin/student-procedures"

    def setUp(self):
        self.program = Program.objects.create(name="General Nursing", abbreviation="RGN")
        self.level = Level.objects.create(number=100, name="Level 100")
        self.other_level = Level.objects.create(number=200, name="Level 200")
        self.admin = User.objects.create_user(username="boss", password="x", role="admin")
        self.ex_a = User.objects.create_user(
            username="ama", password="x", role="examiner", first_name="Ama", last_name="Mensah"
        )
        self.ex_b = User.objects.create_user(username="kofi", password="x", role="examiner")
        self.procedure = Procedure.objects.create(
            program=self.program, name="Bed Bath", total_score=8
        )
        self.steps = [
            ProcedureStep.objects.create(procedure=self.procedure, description=f"S{i}", step_order=i)
            for i in (1, 2)
        ]
        self.s1 = Student.objects.create(
            index_number="A001", full_name="Akua Owusu", program=self.program, level=self.level
        )
        self.s2 = Student.objects.create(
            index_number="B002", full_name="Yaw Boateng", program=self.program, level=self.other_level
        )
        self.sp1 = StudentProcedure.objects.create(
            student=self.s1, procedure=self.procedure, examiner_a=self.ex_a,
            examiner_b=self.ex_b, status="reconciled", reconciled_by=self.ex_a,
        )
        for step, a, b in zip(self.steps, (3, 4), (2, 4)):
            ProcedureStepScore.objects.create(
                student_procedure=self.sp1, step=step, examiner=self.ex_a, score=a
            )
            ProcedureStepScore.objects.create(
                student_procedure=self.sp1, step=step, examiner=self.ex_b, score=b
            )
            ReconciledScore.objects.create(
                student_procedure=self.sp1, step=step, score=a, reconciled_by=self.ex_a
            )
        self.sp2 = StudentProcedure.objects.create(
            student=self.s2, procedure=self.procedure, examiner_a=self.ex_b, status="pending"
        )
        self.client = APIClient()
        self.client.force_authenticate(self.admin)

    def test_examiner_forbidden(self):
        self.client.force_authenticate(self.ex_a)
        self.assertEqual(self.client.get(self.URL).status_code, 403)
        self.assertEqual(self.client.delete(f"{self.URL}/{self.sp1.id}").status_code, 403)

    def test_list_totals_and_query_count(self):
        with self.assertNumQueries(2):  # count + page
            res = self.client.get(self.URL)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["count"], 2)
        row = next(r for r in res.data["results"] if r["id"] == self.sp1.id)
        self.assertEqual(row["examiner_a_score"], 7)
        self.assertEqual(row["examiner_b_score"], 6)
        self.assertEqual(row["reconciled_score"], 7)
        self.assertEqual(row["procedure_max"], 8)
        self.assertEqual(row["examiner_a_name"], "Ama Mensah")
        self.assertEqual(row["examiner_b_name"], "kofi")
        self.assertEqual(row["program_name"], "RGN")

    def test_filters(self):
        def ids(**params):
            return {r["id"] for r in self.client.get(self.URL, params).data["results"]}

        self.assertEqual(ids(status="pending"), {self.sp2.id})
        self.assertEqual(ids(level_id=self.level.id), {self.sp1.id})
        self.assertEqual(ids(examiner_id=self.ex_a.id), {self.sp1.id})
        self.assertEqual(ids(examiner_id=self.ex_b.id), {self.sp1.id, self.sp2.id})
        self.assertEqual(ids(search="boateng"), {self.sp2.id})
        self.assertEqual(ids(search="mensah"), {self.sp1.id})
        self.assertEqual(ids(program_id="all", status="all"), {self.sp1.id, self.sp2.id})

    def test_delete_cascades_scores(self):
        res = self.client.delete(f"{self.URL}/{self.sp1.id}")
        self.assertEqual(res.status_code, 204)
        self.assertFalse(StudentProcedure.objects.filter(id=self.sp1.id).exists())
        self.assertEqual(ProcedureStepScore.objects.count(), 0)
        self.assertEqual(ReconciledScore.objects.count(), 0)

    def test_bulk_delete(self):
        url = f"{self.URL}/bulk-delete"
        self.assertEqual(self.client.post(url, {"ids": []}, format="json").status_code, 400)
        self.assertEqual(
            self.client.post(url, {"ids": list(range(1, 502))}, format="json").status_code, 400
        )
        res = self.client.post(url, {"ids": [self.sp1.id, self.sp2.id]}, format="json")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["deleted_count"], 2)
        self.assertEqual(StudentProcedure.objects.count(), 0)
        self.assertEqual(self.client.post(url, {"ids": [9999]}, format="json").status_code, 404)

    def test_csv_export_respects_filters(self):
        res = self.client.get(self.URL, {"export": "csv", "status": "reconciled"})
        self.assertEqual(res.status_code, 200)
        lines = res.content.decode().strip().splitlines()
        self.assertEqual(len(lines), 2)  # header + 1 row
        self.assertIn("A001", lines[1])

    def test_excel_export(self):
        res = self.client.get(self.URL, {"export": "excel"})
        self.assertEqual(res.status_code, 200)
        self.assertIn("spreadsheetml", res["Content-Type"])


class ProcedureExportTests(TestCase):
    URL = "/api/exams/admin/procedures"

    def setUp(self):
        self.program = Program.objects.create(name="General Nursing", abbreviation="RGN")
        self.category = Category.objects.create(name="Basic Nursing Procedures")
        self.with_cat = Procedure.objects.create(
            program=self.program, name="Bed Bath", total_score=8, category=self.category
        )
        self.no_cat = Procedure.objects.create(
            program=self.program, name="Hand Washing", total_score=4
        )
        for proc in (self.with_cat, self.no_cat):
            for i in (1, 2):
                ProcedureStep.objects.create(procedure=proc, description=f"Step {i}", step_order=i)
        admin = User.objects.create_user(username="boss", password="x", role="admin")
        self.client = APIClient()
        self.client.force_authenticate(admin)

    def test_csv_has_category(self):
        res = self.client.get(self.URL, {"export": "csv"})
        rows = list(csv.DictReader(io.StringIO(res.content.decode())))
        self.assertIn("Category", rows[0])
        by_name = {r["Procedure Name"]: r["Category"] for r in rows}
        self.assertEqual(by_name["Bed Bath"], "Basic Nursing Procedures")
        self.assertEqual(by_name["Hand Washing"], "")

    def test_excel_category_column_matches_import_template(self):
        res = self.client.get(self.URL, {"export": "excel"})
        ws = load_workbook(io.BytesIO(res.content))["Procedures"]
        self.assertEqual(
            [c.value for c in ws[1]],
            ["Name", "Program", "Total Score", "Category", "Steps Count"],
        )
        rows = {r[0]: r for r in ws.iter_rows(min_row=2, values_only=True)}
        self.assertEqual(rows["Bed Bath"][3], "Basic Nursing Procedures")
        self.assertEqual(rows["Bed Bath"][4], 2)

    def test_export_query_count_does_not_grow_per_procedure(self):
        # session/user + procedures + prefetched steps — not one per procedure
        with self.assertNumQueries(2):
            self.client.get(self.URL, {"export": "excel"})

    def test_excel_export_reimports_with_category(self):
        res = self.client.get(self.URL, {"export": "excel"})
        self.with_cat.category = None
        self.with_cat.save()
        upload = io.BytesIO(res.content)
        upload.name = "procedures.xlsx"
        imp = self.client.post("/api/exams/procedures/import", {"file": upload})
        self.assertIn(imp.status_code, (200, 201), imp.data)
        self.with_cat.refresh_from_db()
        self.no_cat.refresh_from_db()
        self.assertEqual(self.with_cat.category, self.category)
        self.assertIsNone(self.no_cat.category)
        self.assertFalse(Category.objects.exclude(pk=self.category.pk).exists())

    # ── Excel import reads columns by header name ──────────────────────────────

    IMPORT_URL = "/api/exams/procedures/import"

    def _xlsx(self, proc_rows, step_rows=None):
        wb = Workbook()
        ws = wb.active
        ws.title = "Procedures"
        for r in proc_rows:
            ws.append(r)
        if step_rows is not None:
            ws_steps = wb.create_sheet("Procedure Steps")
            for r in step_rows:
                ws_steps.append(r)
        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)
        buf.name = "procedures.xlsx"
        return buf

    def test_import_reordered_columns_and_extra_columns(self):
        upload = self._xlsx(
            [
                ["  category ", "Steps Count", "Total Score", "PROGRAM", "Name"],
                ["Advanced", 3, 12, "General Nursing", "Catheterisation"],
            ],
            [
                ["Step Description", "Procedure Name", "Step Order"],
                ["Explain the procedure", "Catheterisation", 1],
                ["Wash hands", "Catheterisation", 2],
            ],
        )
        res = self.client.post(self.IMPORT_URL, {"file": upload})
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual(res.data["errors"], 0, res.data)
        proc = Procedure.objects.get(name="Catheterisation")
        # The file's Total Score (12) is ignored: 2 steps x 4
        self.assertEqual(proc.total_score, 8)
        self.assertEqual(proc.category.name, "Advanced")
        self.assertEqual(
            list(proc.steps.values_list("step_order", "description")),
            [(1, "Explain the procedure"), (2, "Wash hands")],
        )
        # "Steps Count" is ignored rather than becoming a category
        self.assertFalse(Category.objects.filter(name="3").exists())

    def test_import_old_export_with_steps_count_in_column_four(self):
        upload = self._xlsx(
            [
                ["Name", "Program", "Total Score", "Steps Count"],
                ["Bed Bath", "General Nursing", 10, 2],
            ]
        )
        res = self.client.post(self.IMPORT_URL, {"file": upload})
        self.assertEqual(res.status_code, 200, res.data)
        self.with_cat.refresh_from_db()
        # The file's Total Score (10) is ignored: Bed Bath still has 2 steps
        self.assertEqual(self.with_cat.total_score, 8)
        self.assertEqual(self.with_cat.category, self.category)  # unchanged
        self.assertEqual(Category.objects.count(), 1)

    def test_import_without_category_column(self):
        upload = self._xlsx([["Name", "Program"], ["Suturing", "General Nursing"]])
        res = self.client.post(self.IMPORT_URL, {"file": upload})
        self.assertEqual(res.status_code, 200, res.data)
        self.assertIsNone(Procedure.objects.get(name="Suturing").category)

    def test_import_missing_required_column_is_rejected(self):
        upload = self._xlsx([["Name", "Category"], ["Suturing", "Basic"]])
        res = self.client.post(self.IMPORT_URL, {"file": upload})
        self.assertEqual(res.status_code, 400)
        self.assertIn("Program", res.data["error"])
        self.assertFalse(Procedure.objects.filter(name="Suturing").exists())

        upload = self._xlsx(
            [["Name", "Program", "Total Score"], ["Suturing", "General Nursing", 6]],
            [["Procedure Name", "Description"], ["Suturing", "Clean the wound"]],
        )
        res = self.client.post(self.IMPORT_URL, {"file": upload})
        self.assertEqual(res.status_code, 400)
        self.assertIn("Step Order", res.data["error"])
        self.assertFalse(Procedure.objects.filter(name="Suturing").exists())

    def test_pdf_export(self):
        res = self.client.get(self.URL, {"export": "pdf"})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res["Content-Type"], "application/pdf")


# ─────────────────────────────────────────────
# Security regressions (audit run-1 P1 fixes)
# ─────────────────────────────────────────────


class ReferenceDataAdminOnlyTests(TestCase):
    """Levels and rubric steps are admin-writable only; level reads stay open."""

    def setUp(self):
        self.program = Program.objects.create(name="General Nursing", abbreviation="RGN")
        self.level = Level.objects.create(number=100, name="Level 100")
        self.procedure = Procedure.objects.create(program=self.program, name="Bed Bath", total_score=4)
        self.step = ProcedureStep.objects.create(procedure=self.procedure, description="S1", step_order=1)
        self.examiner = User.objects.create_user(username="ama", password="x", role="examiner")
        self.admin = User.objects.create_user(username="boss", password="x", role="admin")
        self.client = APIClient()

    def test_examiner_can_read_levels_but_not_write(self):
        self.client.force_authenticate(self.examiner)
        self.assertEqual(self.client.get("/api/exams/levels").status_code, 200)
        self.assertEqual(self.client.post("/api/exams/levels", {"number": 500, "name": "X"}).status_code, 403)
        self.assertEqual(self.client.patch(f"/api/exams/levels/{self.level.id}", {"name": "Y"}).status_code, 403)
        self.assertEqual(self.client.delete(f"/api/exams/levels/{self.level.id}").status_code, 403)
        self.assertEqual(Level.objects.get(pk=self.level.pk).name, "Level 100")

    def test_admin_can_write_levels(self):
        self.client.force_authenticate(self.admin)
        res = self.client.post("/api/exams/levels", {"number": 500, "name": "Level 500"})
        self.assertEqual(res.status_code, 201)

    def test_examiner_cannot_touch_procedure_steps(self):
        self.client.force_authenticate(self.examiner)
        base = "/api/exams/admin/procedure-steps"
        self.assertEqual(self.client.get(base).status_code, 403)
        res = self.client.post(base, {"procedure_id": self.procedure.id, "description": "x", "step_order": 2})
        self.assertEqual(res.status_code, 403)
        self.assertEqual(self.client.patch(f"{base}/{self.step.id}", {"description": "y"}).status_code, 403)
        self.assertEqual(self.client.delete(f"{base}/{self.step.id}").status_code, 403)
        self.assertTrue(ProcedureStep.objects.filter(pk=self.step.pk, description="S1").exists())

    def test_admin_can_manage_procedure_steps(self):
        self.client.force_authenticate(self.admin)
        self.assertEqual(self.client.get("/api/exams/admin/procedure-steps").status_code, 200)


class ProcedureTotalScoreTests(TestCase):
    """A procedure's total score is always its number of steps x 4."""

    STEPS = "/api/exams/admin/procedure-steps"

    def setUp(self):
        self.program = Program.objects.create(name="General Nursing", abbreviation="RGN")
        self.client = APIClient()
        self.client.force_authenticate(User.objects.create_user(username="boss", password="x", role="admin"))

    def total(self, name):
        return Procedure.objects.get(name=name).total_score

    def test_new_procedure_ignores_typed_total(self):
        res = self.client.post(
            "/api/exams/admin/procedures",
            {"name": "Bed Bath", "program_id": self.program.id, "total_score": 99},
        )
        self.assertEqual(res.status_code, 201, res.data)
        self.assertEqual(self.total("Bed Bath"), 0)

    def test_adding_editing_moving_and_deleting_steps(self):
        a = Procedure.objects.create(program=self.program, name="A")
        b = Procedure.objects.create(program=self.program, name="B")
        ids = [
            self.client.post(self.STEPS, {"procedure_id": a.id, "description": f"S{i}", "step_order": i}).data["id"]
            for i in (1, 2, 3)
        ]
        self.assertEqual(self.total("A"), 12)

        # editing the text doesn't change the count
        self.client.patch(f"{self.STEPS}/{ids[0]}", {"description": "Renamed"})
        self.assertEqual(self.total("A"), 12)

        # moving a step updates both procedures
        step = ProcedureStep.objects.get(pk=ids[1])
        step.procedure = b
        step.save()
        self.assertEqual((self.total("A"), self.total("B")), (8, 4))

        self.client.delete(f"{self.STEPS}/{ids[2]}")
        self.assertEqual(self.total("A"), 4)

    def test_editing_procedure_cannot_set_total(self):
        proc = Procedure.objects.create(program=self.program, name="A")
        ProcedureStep.objects.create(procedure=proc, description="S1", step_order=1)
        self.client.patch(f"/api/exams/admin/procedures/{proc.id}", {"total_score": 50, "name": "A2"})
        proc.refresh_from_db()
        self.assertEqual((proc.name, proc.total_score), ("A2", 4))

    def test_stale_in_memory_total_is_not_saved(self):
        proc = Procedure.objects.create(program=self.program, name="A")
        stale = Procedure.objects.get(pk=proc.pk)  # loaded with 0 steps
        ProcedureStep.objects.create(procedure=proc, description="S1", step_order=1)
        stale.name = "A2"
        stale.save()
        self.assertEqual(self.total("A2"), 4)

    def test_excel_import_calculates_totals(self):
        wb = Workbook()
        ws = wb.active
        ws.title = "Procedures"
        ws.append(["Name", "Program", "Total Score"])  # old-style file with a total
        ws.append(["Catheterisation", "General Nursing", 50])
        ws.append(["Suturing", "General Nursing", ""])
        steps = wb.create_sheet("Procedure Steps")
        steps.append(["Procedure Name", "Step Order", "Description"])
        for i in (1, 2, 3):
            steps.append(["Catheterisation", i, f"Step {i}"])
        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)
        buf.name = "procedures.xlsx"
        res = self.client.post("/api/exams/procedures/import", {"file": buf})
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual(res.data["errors"], 0, res.data)
        self.assertEqual(self.total("Catheterisation"), 12)
        self.assertEqual(self.total("Suturing"), 0)

    def test_csv_import_calculates_totals(self):
        content = (
            "Procedure Name,Program,Total Score,Category,Step Order,Step Description\n"
            "Bed Bath,General Nursing,,Basic,1,Explain\n"
            "Bed Bath,General Nursing,,Basic,2,Wash\n"
        )
        upload = io.BytesIO(content.encode())
        upload.name = "procedures.csv"
        res = self.client.post("/api/exams/procedures/import", {"file": upload})
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual(res.data["errors"], 0, res.data)
        self.assertEqual(self.total("Bed Bath"), 8)

    def test_single_procedure_steps_import_updates_total(self):
        proc = Procedure.objects.create(program=self.program, name="A")
        wb = Workbook()
        wb.active.append(["Step Order", "Description"])
        for i in (1, 2):
            wb.active.append([i, f"Step {i}"])
        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)
        buf.name = "steps.xlsx"
        res = self.client.post(f"/api/exams/procedures/{proc.id}/steps/import", {"file": buf})
        self.assertIn(res.status_code, (200, 201), getattr(res, "data", res))
        self.assertEqual(self.total("A"), 8)

    def test_template_has_no_total_score_column(self):
        res = self.client.get("/api/exams/procedures/template")
        ws = load_workbook(io.BytesIO(res.content))["Procedures"]
        self.assertEqual([c.value for c in ws[1]], ["Name", "Program", "Category"])


class CheckProcedureTotalsCommandTests(TestCase):
    """The pre-deploy report is accurate and never changes anything."""

    def setUp(self):
        program = Program.objects.create(name="General Nursing", abbreviation="RGN")
        level = Level.objects.create(number=100, name="Level 100")
        self.examiner = User.objects.create_user(username="ama", password="x", role="examiner")
        self.proc = Procedure.objects.create(program=program, name="Bed Bath")
        steps = [
            ProcedureStep.objects.create(procedure=self.proc, description=f"S{i}", step_order=i)
            for i in (1, 2)
        ]  # correct total would be 8
        # Simulate a typed-in total of 10 from before totals were calculated.
        Procedure.objects.filter(pk=self.proc.pk).update(total_score=10)

        self.student = Student.objects.create(
            index_number="A001", full_name="Akua Owusu", program=program, level=level
        )
        sp = StudentProcedure.objects.create(
            student=self.student, procedure=self.proc, status="reconciled"
        )
        for step, score in zip(steps, (3, 3)):  # 6 points
            ReconciledScore.objects.create(
                student_procedure=sp, step=step, score=score, reconciled_by=self.examiner
            )
        # 6/10 = 60% (Pass) now; 6/8 = 75% (Credit) after recalculation

    def run_check(self, *args):
        from django.core.management import call_command

        out = io.StringIO()
        call_command("check_procedure_totals", *args, stdout=out)
        return out.getvalue()

    def test_reports_mismatch_and_grade_change_without_changing_data(self):
        out = self.run_check()
        self.assertIn("1 with a total", out)
        self.assertIn("Bed Bath (General Nursing): 10 -> 8 (2 steps)", out)
        self.assertIn("[1 reconciled]", out)
        self.assertIn("A001  Akua Owusu: 60.0% -> 75.0%  (Pass -> Credit)", out)
        self.proc.refresh_from_db()
        self.assertEqual(self.proc.total_score, 10)  # read-only

    def test_nothing_to_do(self):
        Procedure.objects.filter(pk=self.proc.pk).update(total_score=8)
        self.assertIn("Nothing will change", self.run_check())

    def test_inactive_students_are_left_out(self):
        Student.objects.filter(pk=self.student.pk).update(is_active=False)
        self.assertIn("0 students' percentages change", self.run_check())

    def test_missing_db_file_is_an_error(self):
        from django.core.management.base import CommandError

        with self.assertRaises(CommandError):
            self.run_check("--db", "does-not-exist.sqlite3")


class SetBrandingCommandTests(TestCase):
    def run_cmd(self, *args):
        from django.core.management import call_command

        out = io.StringIO()
        call_command("set_branding", *args, stdout=out)
        return out.getvalue()

    def test_sets_only_the_options_given(self):
        SiteSettings.objects.update_or_create(pk=1, defaults={"short_name": "OLD"})
        self.run_cmd("--name", "  Tanoso College ", "--color", "#16A34A")
        s = SiteSettings.get()
        self.assertEqual(
            (s.institution_name, s.short_name, s.brand_color), ("Tanoso College", "OLD", "#16a34a")
        )

    def test_logo_is_processed_and_can_be_cleared(self):
        import tempfile

        from PIL import Image

        with tempfile.TemporaryDirectory() as d:
            path = f"{d}/logo.jpg"
            Image.new("RGB", (1024, 600), "green").save(path, "JPEG")
            out = self.run_cmd("--logo", path)
        s = SiteSettings.get()
        self.assertIn("Updated: logo", out)
        self.assertEqual(s.logo_content_type, "image/png")
        with Image.open(io.BytesIO(bytes(s.logo))) as img:
            self.assertEqual(img.format, "PNG")
            self.assertLessEqual(max(img.size), 512)

        self.run_cmd("--clear-logo")
        self.assertIsNone(SiteSettings.get().logo)

    def test_rejects_bad_input(self):
        from django.core.management.base import CommandError

        for args in (["--color", "green"], ["--logo", "missing.png"], ["--short-name", "x" * 31]):
            with self.assertRaises(CommandError):
                self.run_cmd(*args)

    def test_reset_colour_and_show(self):
        SiteSettings.objects.update_or_create(pk=1, defaults={"brand_color": "#166534"})
        self.run_cmd("--color", "")
        out = self.run_cmd()
        self.assertIn("(ClinOva default)", out)
        self.assertNotIn("Updated", out)


class VersionEndpointTests(TestCase):
    """The release version is shown to admins only."""

    def setUp(self):
        self.client = APIClient()

    def test_admin_gets_version(self):
        from nursing_practical.version import __version__

        self.client.force_authenticate(User.objects.create_user(username="boss", password="x", role="admin"))
        res = self.client.get("/api/exams/version")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json(), {"version": __version__})

    def test_examiner_and_anonymous_are_refused(self):
        self.assertIn(self.client.get("/api/exams/version").status_code, (401, 403))
        self.client.force_authenticate(User.objects.create_user(username="ama", password="x", role="examiner"))
        self.assertEqual(self.client.get("/api/exams/version").status_code, 403)


class ReconciliationBlindScoringTests(TestCase):
    """Both examiners' scores are visible only to the examiner allowed to reconcile."""

    def setUp(self):
        program = Program.objects.create(name="General Nursing", abbreviation="RGN")
        level = Level.objects.create(number=100, name="Level 100")
        self.procedure = Procedure.objects.create(program=program, name="Bed Bath", total_score=8)
        self.steps = [
            ProcedureStep.objects.create(procedure=self.procedure, description=f"S{i}", step_order=i)
            for i in (1, 2)
        ]
        self.student = Student.objects.create(
            index_number="A001", full_name="Akua Owusu", program=program, level=level
        )
        self.ex_a = User.objects.create_user(username="ama", password="x", role="examiner")
        self.ex_b = User.objects.create_user(username="kofi", password="x", role="examiner")
        self.ex_c = User.objects.create_user(username="esi", password="x", role="examiner")
        self.sp = StudentProcedure.objects.create(
            student=self.student, procedure=self.procedure, examiner_a=self.ex_a, examiner_b=self.ex_b
        )
        self.url = f"/api/exams/students/{self.student.id}/procedures/{self.procedure.id}/reconciliation"
        self.client = APIClient()

    def score(self, examiner):
        for step in self.steps:
            ProcedureStepScore.objects.create(
                student_procedure=self.sp, step=step, examiner=examiner, score=3
            )

    def test_pending_scores_hidden_from_other_examiner(self):
        self.score(self.ex_a)
        self.client.force_authenticate(self.ex_b)
        self.assertEqual(self.client.get(self.url).status_code, 403)

    def test_get_does_not_create_assessment(self):
        other = Student.objects.create(
            index_number="B002", full_name="Yaw Boateng",
            program=self.student.program, level=self.student.level,
        )
        self.client.force_authenticate(self.ex_c)
        url = f"/api/exams/students/{other.id}/procedures/{self.procedure.id}/reconciliation"
        self.assertEqual(self.client.get(url).status_code, 404)
        self.assertFalse(StudentProcedure.objects.filter(student=other).exists())

    def test_only_last_scorer_sees_scores_once_scored(self):
        self.score(self.ex_a)
        ProcedureStepScore.objects.filter(examiner=self.ex_a).update(
            updated_at=timezone.now() - timedelta(minutes=5)
        )
        self.score(self.ex_b)
        self.sp.status = "scored"
        self.sp.save()

        for user in (self.ex_a, self.ex_c):
            self.client.force_authenticate(user)
            self.assertEqual(self.client.get(self.url).status_code, 403)

        self.client.force_authenticate(self.ex_b)
        res = self.client.get(self.url)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(len(res.data["steps"]), 2)
        self.sp.refresh_from_db()
        self.assertEqual(self.sp.assigned_reconciler, self.ex_b)


class ExaminerImportPasswordTests(TestCase):
    URL = "/api/exams/admin/examiners/import"

    def setUp(self):
        self.admin = User.objects.create_user(username="boss", password="x", role="admin")
        self.client = APIClient()
        self.client.force_authenticate(self.admin)

    def upload(self, text):
        f = io.BytesIO(text.encode())
        f.name = "examiners.csv"
        return self.client.post(self.URL, {"file": f}, format="multipart")

    def test_blank_password_gets_unique_random_password(self):
        res = self.upload("Username,First Name\nexam01,Ama\nexam02,Kofi\n")
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual(res.data["created"], 2)
        u1 = User.objects.get(username="exam01")
        u2 = User.objects.get(username="exam02")
        self.assertFalse(u1.check_password("Change123!"))
        shown = [d for d in res.data["success_details"] if "temporary password:" in d]
        self.assertEqual(len(shown), 2)
        pw1 = next(d for d in shown if "@exam01" in d).rsplit(": ", 1)[1]
        pw2 = next(d for d in shown if "@exam02" in d).rsplit(": ", 1)[1]
        self.assertNotEqual(pw1, pw2)
        self.assertTrue(u1.check_password(pw1))
        self.assertTrue(u2.check_password(pw2))

    def test_weak_supplied_password_rejected(self):
        res = self.upload("Username,Password\nexam03,123\n")
        self.assertEqual(res.data["created"], 0)
        self.assertEqual(res.data["errors"], 1)
        self.assertFalse(User.objects.filter(username="exam03").exists())

    def test_api_create_validates_password(self):
        res = self.client.post(
            "/api/exams/admin/examiners",
            {"username": "exam04", "password": "123", "role": "examiner"},
        )
        self.assertEqual(res.status_code, 400)
        self.assertIn("password", res.data)


# ─────────────────────────────────────────────
# Institution branding
# ─────────────────────────────────────────────


def _image_file(fmt="PNG", size=(800, 400), name="logo.png"):
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", size, (20, 120, 200)).save(buf, format=fmt)
    buf.seek(0)
    buf.name = name
    return buf


class BrandingTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username="boss", password="x", role="admin")
        self.examiner = User.objects.create_user(username="ama", password="x", role="examiner")
        self.client = APIClient()

    def test_public_branding_needs_no_login_and_ignores_bad_cookie(self):
        s = SiteSettings.get()
        s.institution_name = "Nursing and Midwifery Training College, Tanoso"
        s.short_name = "CNMT"
        s.save()
        self.client.cookies["access_token"] = "garbage"
        res = self.client.get("/api/exams/branding")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["short_name"], "CNMT")
        self.assertIsNone(res.data["logo_url"])
        self.assertEqual(self.client.get("/api/exams/branding/logo").status_code, 404)

    def test_admin_sets_names_via_settings(self):
        self.client.force_authenticate(self.admin)
        res = self.client.patch(
            "/api/exams/settings", {"institution_name": "  UENR School  ", "short_name": "UENR"}, format="json"
        )
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual(SiteSettings.get().institution_name, "UENR School")

    def test_examiner_cannot_change_branding(self):
        self.client.force_authenticate(self.examiner)
        self.assertEqual(
            self.client.patch("/api/exams/settings", {"short_name": "X"}, format="json").status_code, 403
        )
        res = self.client.post("/api/exams/branding/logo", {"logo": _image_file()}, format="multipart")
        self.assertEqual(res.status_code, 403)
        self.assertEqual(self.client.delete("/api/exams/branding/logo").status_code, 403)

    def test_anonymous_cannot_upload_logo(self):
        res = self.client.post("/api/exams/branding/logo", {"logo": _image_file()}, format="multipart")
        self.assertIn(res.status_code, (401, 403))
        self.assertFalse(SiteSettings.get().logo)

    def test_logo_upload_is_reencoded_resized_and_served(self):
        from PIL import Image

        self.client.force_authenticate(self.admin)
        res = self.client.post(
            "/api/exams/branding/logo", {"logo": _image_file("JPEG", (1200, 600), "logo.jpg")}, format="multipart"
        )
        self.assertEqual(res.status_code, 200, res.data)
        url = res.data["logo_url"]
        self.assertTrue(url.startswith("/api/exams/branding/logo?v="))

        public = APIClient()
        img_res = public.get(url)
        self.assertEqual(img_res.status_code, 200)
        self.assertEqual(img_res["Content-Type"], "image/png")
        self.assertEqual(img_res["X-Content-Type-Options"], "nosniff")
        img = Image.open(io.BytesIO(img_res.content))
        self.assertEqual(img.format, "PNG")
        self.assertLessEqual(max(img.size), 512)
        self.assertEqual(public.get("/api/exams/branding").data["logo_url"], url)

        self.assertEqual(self.client.delete("/api/exams/branding/logo").status_code, 204)
        self.assertIsNone(public.get("/api/exams/branding").data["logo_url"])

    def test_rejects_non_images_and_svg(self):
        self.client.force_authenticate(self.admin)
        bad = io.BytesIO(b"<svg xmlns='http://www.w3.org/2000/svg'><script>alert(1)</script></svg>")
        bad.name = "logo.svg"
        res = self.client.post("/api/exams/branding/logo", {"logo": bad}, format="multipart")
        self.assertEqual(res.status_code, 400)
        self.assertIn("logo", res.data)
        gif = _image_file("GIF", (50, 50), "logo.gif")
        self.assertEqual(
            self.client.post("/api/exams/branding/logo", {"logo": gif}, format="multipart").status_code, 400
        )
        self.assertFalse(SiteSettings.get().logo)

    def test_brand_color_saved_published_and_validated(self):
        self.client.force_authenticate(self.admin)
        res = self.client.patch("/api/exams/settings", {"brand_color": "#1F6F43"}, format="json")
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual(APIClient().get("/api/exams/branding").data["brand_color"], "#1f6f43")
        for bad in ["red", "#12345", "#12345g", "#000000;}body{x", "url(x)"]:
            res = self.client.patch("/api/exams/settings", {"brand_color": bad}, format="json")
            self.assertEqual(res.status_code, 400, bad)
        self.assertEqual(SiteSettings.get().brand_color, "#1f6f43")
        res = self.client.patch("/api/exams/settings", {"brand_color": ""}, format="json")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(APIClient().get("/api/exams/branding").data["brand_color"], "")

    def test_admin_header_uses_branding(self):
        from .branding import site_header

        self.assertEqual(site_header(None), "ClinOva")
        s = SiteSettings.get()
        s.short_name = "PRAMSO"
        s.save()
        self.assertEqual(site_header(None), "ClinOva · PRAMSO")
