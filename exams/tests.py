from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import User

from .models import (
    CarePlan,
    CarePlanEligibility,
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
