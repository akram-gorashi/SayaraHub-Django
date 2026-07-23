from django.core.management import call_command
from django.db import connection
from django.test.utils import CaptureQueriesContext
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
        self.login("CANDIDATE@EXAMPLE.COM", "StrongPass_123!")
        profile = self.client.get("/api/v1/users/me")
        self.assertEqual(profile.data["data"]["fullName"], "Interview User")

        self.client.credentials()
        refreshed = self.client.post("/api/v1/Auth/refresh", {}, format="json")
        self.assertEqual(refreshed.status_code, 200)
        self.assertEqual(refreshed.data["data"]["email"], "candidate@example.com")
        self.assertIn("accessTokenExpiresAt", refreshed.data["data"])

    def test_partial_car_update_preserves_brand_model_validation(self):
        car = models.Car.objects.get()
        self.login()
        response = self.client.put(
            f"/api/v1/Cars/{car.id}", {"title": "Updated without resending lookups"}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        car.refresh_from_db()
        self.assertEqual(car.title, "Updated without resending lookups")
        self.assertEqual(car.status, models.Car.Status.PENDING)

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

    def test_session_ticket_and_notification_preferences(self):
        self.login()
        sessions = self.client.get("/api/v1/Auth/sessions")
        self.assertEqual(sessions.status_code, 200)
        self.assertGreaterEqual(len(sessions.data["data"]), 1)

        ticket = self.client.post("/api/v1/Auth/websocket-ticket", {}, format="json")
        self.assertEqual(ticket.status_code, 200)
        self.assertTrue(ticket.data["data"]["ticket"])

        preferences = self.client.put("/api/v1/notifications/preferences", {
            "preferences": [{"eventType": "ChatMessage", "isEnabled": False}]
        }, format="json")
        self.assertEqual(preferences.status_code, 200)
        self.assertFalse(next(item for item in preferences.data["data"] if item["eventType"] == "ChatMessage")["isEnabled"])

    def test_seller_detail_images_and_numeric_moderation_contract(self):
        car = models.Car.objects.get()
        self.login()
        detail = self.client.get(f"/api/v1/seller/cars/{car.id}")
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.data["data"]["carBrandId"], car.brand_id)
        self.assertIn("imageProcessing", detail.data["data"])

        car.status = models.Car.Status.PENDING
        car.save(update_fields=["status"])
        self.login("admin@sayarahub.local", "AdminDemo_44")
        moderated = self.client.patch(
            f"/api/v1/admin/moderation/cars/{car.id}", {"decision": 1}, format="json"
        )
        self.assertEqual(moderated.status_code, 200)
        stats = self.client.get("/api/v1/admin/moderation/statistics")
        self.assertEqual(set(stats.data["data"]), {"pending", "approved", "rejected"})

    def test_chat_list_query_count_does_not_grow_per_chat(self):
        seller = models.User.objects.get(email="seller@sayarahub.local")
        car = models.Car.objects.get()
        first_buyer = models.User.objects.create_user(
            email="buyer-0@example.com", password="StrongPass_123!", full_name="Buyer 0"
        )
        chat = models.Chat.objects.create(car=car, buyer=first_buyer, seller=seller)
        models.Message.objects.create(chat=chat, sender=first_buyer, content="First")
        self.login()

        with CaptureQueriesContext(connection) as one_chat:
            response = self.client.get("/api/v1/chats?pageSize=20")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["data"]["items"][0]["lastMessage"], "First")
        self.assertEqual(response.data["data"]["items"][0]["unreadCount"], 1)

        for index in range(1, 6):
            buyer = models.User.objects.create_user(
                email=f"buyer-{index}@example.com", password="StrongPass_123!", full_name=f"Buyer {index}"
            )
            extra_chat = models.Chat.objects.create(car=car, buyer=buyer, seller=seller)
            models.Message.objects.create(chat=extra_chat, sender=buyer, content=f"Message {index}")

        with CaptureQueriesContext(connection) as many_chats:
            response = self.client.get("/api/v1/chats?pageSize=20")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["data"]["totalCount"], 6)
        self.assertLessEqual(len(many_chats), len(one_chat) + 1)

    def test_seller_dashboard_reports_real_image_processing_counts(self):
        car = models.Car.objects.get()
        models.CarImage.objects.create(
            car=car, image="cars/pending.jpg", processing_status="Pending"
        )
        models.CarImage.objects.create(
            car=car, image="cars/failed.jpg", processing_status="Failed"
        )
        self.login()
        response = self.client.get("/api/v1/seller/statistics")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["data"]["pendingImageCount"], 1)
        self.assertEqual(response.data["data"]["failedImageCount"], 1)
