import csv
import io

from django.test import TestCase
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
        self.assertEqual(proc.total_score, 12)
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
        self.assertEqual(self.with_cat.total_score, 10)
        self.assertEqual(self.with_cat.category, self.category)  # unchanged
        self.assertEqual(Category.objects.count(), 1)

    def test_import_without_category_column(self):
        upload = self._xlsx(
            [["Name", "Program", "Total Score"], ["Suturing", "General Nursing", 6]]
        )
        res = self.client.post(self.IMPORT_URL, {"file": upload})
        self.assertEqual(res.status_code, 200, res.data)
        self.assertIsNone(Procedure.objects.get(name="Suturing").category)

    def test_import_missing_required_column_is_rejected(self):
        upload = self._xlsx([["Name", "Total Score"], ["Suturing", 6]])
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
