from django.core.management import call_command
from rest_framework.test import APITestCase
from . import models


class ApiFlowTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_demo", verbosity=0)

    def login(self, email="seller@sayarahub.local", password="SellerDemo_44"):
        response = self.client.post("/api/v1/Auth/login", {"email": email, "password": password}, format="json")
        self.assertEqual(response.status_code, 200)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {response.data["data"]["token"]}')
        return response

    def test_public_car_list_uses_angular_envelope(self):
        response = self.client.get("/api/v1/Cars?pageNumber=1&pageSize=5")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["success"])
        self.assertEqual(response.data["data"]["totalCount"], 1)
        self.assertIn("mainImageUrl", response.data["data"]["items"][0])

    def test_register_login_and_profile(self):
        response = self.client.post("/api/v1/Auth/register", {
            "fullName": "Interview User", "email": "candidate@example.com", "password": "StrongPass_123!"
        }, format="json")
        self.assertEqual(response.status_code, 201)
        self.assertIn("token", response.data["data"])
        self.login("candidate@example.com", "StrongPass_123!")
        profile = self.client.get("/api/v1/users/me")
        self.assertEqual(profile.data["data"]["fullName"], "Interview User")

        self.client.credentials()
        refreshed = self.client.post("/api/v1/Auth/refresh", {}, format="json")
        self.assertEqual(refreshed.status_code, 200)
        self.assertEqual(refreshed.data["data"]["email"], "candidate@example.com")
        self.assertIn("accessTokenExpiresAt", refreshed.data["data"])

    def test_favorite_is_idempotent(self):
        self.login()
        car = models.Car.objects.get()
        self.assertEqual(self.client.post(f"/api/v1/Cars/{car.id}/favorite").status_code, 200)
        self.assertEqual(self.client.post(f"/api/v1/Cars/{car.id}/favorite").status_code, 200)
        self.assertEqual(models.Favorite.objects.count(), 1)

    def test_admin_can_moderate_pending_car(self):
        seller = models.User.objects.get(email="seller@sayarahub.local")
        car = models.Car.objects.get()
        car.status = models.Car.Status.PENDING
        car.save(update_fields=["status"])
        self.login("admin@sayarahub.local", "AdminDemo_44")
        response = self.client.patch(f"/api/v1/admin/moderation/cars/{car.id}", {"decision": "Approve"}, format="json")
        self.assertEqual(response.status_code, 200)
        car.refresh_from_db()
        self.assertEqual(car.status, models.Car.Status.AVAILABLE)
        self.assertTrue(models.Notification.objects.filter(user=seller, type="ListingApproved").exists())
