from django.core.management import call_command
from django.db import connection
from django.db import IntegrityError, transaction
from django.test.utils import CaptureQueriesContext
from unittest.mock import patch
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

    def test_ninja_master_data_preserves_contract_and_validates_queries(self):
        response = self.client.get("/api/v1/MasterData/car-brands?pageNumber=1&pageSize=5")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["success"])
        self.assertEqual(payload["data"]["pageNumber"], 1)
        self.assertEqual(payload["data"]["pageSize"], 5)
        self.assertGreater(payload["data"]["totalCount"], 0)

        invalid = self.client.get("/api/v1/MasterData/car-brands?pageSize=101")
        self.assertEqual(invalid.status_code, 422)
        self.assertEqual(invalid.json()["message"], "Validation failed")

        missing = self.client.get("/api/v1/MasterData/not-a-kind")
        self.assertEqual(missing.status_code, 404)
        self.assertFalse(missing.json()["success"])

    def test_ninja_openapi_documents_migrated_routes(self):
        response = self.client.get("/api/v1/openapi.json")
        self.assertEqual(response.status_code, 200)
        paths = response.json()["paths"]
        self.assertIn("/api/v1/MasterData", paths)
        self.assertIn("/api/v1/MasterData/{kind}", paths)
        self.assertIn("/api/v1/Auth/login", paths)
        self.assertIn("/api/v1/Cars", paths)
        self.assertIn("/api/v1/chats", paths)
        self.assertIn("/api/v1/admin/moderation/cars", paths)
        self.assertGreaterEqual(len(paths), 90)

        docs_redirect = self.client.get("/api/docs/")
        schema_redirect = self.client.get("/api/schema/")
        self.assertRedirects(docs_redirect, "/api/v1/docs/", fetch_redirect_response=False)
        self.assertRedirects(schema_redirect, "/api/v1/openapi.json", fetch_redirect_response=False)

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
        self.client.post(
            "/api/v1/Auth/login",
            {"email": "seller@sayarahub.local", "password": "SellerDemo_44"},
            format="json",
            HTTP_USER_AGENT="Mozilla/5.0 Chrome/140.0.0.0 Safari/537.36",
            REMOTE_ADDR="203.0.113.10",
        )
        login = self.client.post(
            "/api/v1/Auth/login",
            {"email": "seller@sayarahub.local", "password": "SellerDemo_44"},
            format="json",
            HTTP_USER_AGENT="Mozilla/5.0 Chrome/140.0.0.0 Safari/537.36",
            REMOTE_ADDR="203.0.113.10",
        )
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {login.data["data"]["token"]}')
        sessions = self.client.get("/api/v1/Auth/sessions")
        self.assertEqual(sessions.status_code, 200)
        self.assertGreaterEqual(len(sessions.data["data"]), 1)
        current = next(item for item in sessions.data["data"] if item["isCurrent"])
        self.assertIn("Chrome", current["browser"])
        self.assertEqual(current["ipAddress"], "203.0.113.10")

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

    def test_cursor_pagination_is_signed_and_does_not_duplicate_items(self):
        seller = models.User.objects.get(email="seller@sayarahub.local")
        for index in range(5):
            models.Notification.objects.create(
                user=seller, type="CursorTest", title=f"Notice {index}", message="Cursor pagination"
            )
        self.login()
        first = self.client.get("/api/v1/notifications?pagination=cursor&pageSize=2")
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.data["data"]["paginationMode"], "cursor")
        self.assertEqual(len(first.data["data"]["items"]), 2)
        cursor = first.data["data"]["nextCursor"]
        second = self.client.get(
            "/api/v1/notifications", {"pagination": "cursor", "pageSize": 2, "cursor": cursor}
        )
        first_ids = {item["id"] for item in first.data["data"]["items"]}
        second_ids = {item["id"] for item in second.data["data"]["items"]}
        self.assertFalse(first_ids & second_ids)
        invalid = self.client.get("/api/v1/notifications?pagination=cursor&cursor=tampered")
        self.assertEqual(invalid.status_code, 400)

    def test_contact_creation_replays_idempotently(self):
        car = models.Car.objects.get()
        payload = {
            "name": "Interested Buyer",
            "email": "buyer@example.com",
            "subject": "Availability",
            "message": "Is this still available?",
        }
        headers = {"HTTP_IDEMPOTENCY_KEY": "contact-request-0001"}
        first = self.client.post(
            f"/api/v1/cars/{car.id}/contact-messages", payload, format="json", **headers
        )
        second = self.client.post(
            f"/api/v1/cars/{car.id}/contact-messages", payload, format="json", **headers
        )
        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 201)
        self.assertEqual(second["Idempotency-Replayed"], "true")
        self.assertEqual(models.ContactMessage.objects.filter(car=car).count(), 1)
        changed = self.client.post(
            f"/api/v1/cars/{car.id}/contact-messages",
            {**payload, "message": "A different request"},
            format="json",
            **headers,
        )
        self.assertEqual(changed.status_code, 409)

    def test_only_one_main_image_is_allowed_per_car(self):
        car = models.Car.objects.get()
        models.CarImage.objects.create(car=car, image="cars/main-one.jpg", is_main=True)
        with self.assertRaises(IntegrityError), transaction.atomic():
            models.CarImage.objects.create(car=car, image="cars/main-two.jpg", is_main=True)

    def test_car_image_task_dispatch_failure_does_not_fail_committed_save(self):
        car = models.Car.objects.get()
        with patch("marketplace.tasks.process_car_image.delay", side_effect=RuntimeError("broker unavailable")) as delay:
            with self.captureOnCommitCallbacks(execute=True):
                image = models.CarImage.objects.create(car=car, image="cars/pending-dispatch.jpg")

        delay.assert_called_once_with(image.id)
        self.assertTrue(models.CarImage.objects.filter(id=image.id, processing_status="Pending").exists())

    def test_feature_flags_and_postgres_search_remain_available(self):
        flags = self.client.get("/api/v1/features")
        self.assertEqual(flags.status_code, 200)
        self.assertTrue(flags.data["data"]["cursor-pagination"])
        self.assertTrue(flags.data["data"]["postgres-full-text-search"])
        search = self.client.get("/api/v1/Cars?search=Camry")
        self.assertEqual(search.status_code, 200)
        self.assertEqual(search.data["data"]["totalCount"], 1)
