from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import User

from .models import CarePlan, CarePlanEligibility, Level, Program, SiteSettings, Student


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
