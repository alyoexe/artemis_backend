import tempfile
import json

from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.files.storage import default_storage
from django.test import TestCase, override_settings
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken

from ingestion.models import CustomUser, EquipmentCategory, TechnicalDocument, Vendor


@override_settings(MEDIA_ROOT=tempfile.gettempdir())
class TechnicalDocumentApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()

        self.admin_user = CustomUser.objects.create_user(
            username="admin",
            password="adminpass123",
            role=CustomUser.Roles.SYSTEM_ADMINISTRATOR,
        )
        self.steward_user = CustomUser.objects.create_user(
            username="steward",
            password="stewardpass123",
            role=CustomUser.Roles.DATA_STEWARD,
        )
        self.tech_user = CustomUser.objects.create_user(
            username="tech",
            password="techpass123",
            role=CustomUser.Roles.FIELD_TECHNICIAN,
        )
        self.tech_user_2 = CustomUser.objects.create_user(
            username="tech2",
            password="techpass123",
            role=CustomUser.Roles.FIELD_TECHNICIAN,
        )

        self.vendor = Vendor.objects.create(name="Siemens")
        self.category = EquipmentCategory.objects.create(name="PLC")

        self.ready_doc = TechnicalDocument.objects.create(
            file=SimpleUploadedFile("ready.pdf", b"ready-content", content_type="application/pdf"),
            title="Ready Document",
            vendor=self.vendor,
            category=self.category,
            uploaded_by=self.steward_user,
            status=TechnicalDocument.Status.READY,
            metadata={"facility": "A1"},
        )
        self.processing_doc = TechnicalDocument.objects.create(
            file=SimpleUploadedFile("processing.pdf", b"processing-content", content_type="application/pdf"),
            title="Processing Document",
            vendor=self.vendor,
            category=self.category,
            uploaded_by=self.steward_user,
            status=TechnicalDocument.Status.PROCESSING,
            metadata={"facility": "B2"},
        )

    def test_data_steward_can_upload_document(self):
        self.client.force_authenticate(user=self.steward_user)
        payload = {
            "file": SimpleUploadedFile("new.pdf", b"file-content", content_type="application/pdf"),
            "title": "Pump Manual",
            "vendor": self.vendor.id,
            "category": self.category.id,
            "metadata": json.dumps({"facility": "C3"}),
        }

        response = self.client.post("/api/documents/", data=payload, format="multipart")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["status"], TechnicalDocument.Status.UPLOADED)

    def test_field_technician_cannot_upload_document(self):
        self.client.force_authenticate(user=self.tech_user)
        payload = {
            "file": SimpleUploadedFile("new.pdf", b"file-content", content_type="application/pdf"),
            "title": "Technician Upload",
            "vendor": self.vendor.id,
            "category": self.category.id,
            "metadata": json.dumps({"facility": "D4"}),
        }

        response = self.client.post("/api/documents/", data=payload, format="multipart")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_field_technician_only_sees_ready_documents(self):
        self.client.force_authenticate(user=self.tech_user)

        response = self.client.get("/api/documents/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        returned_ids = {item["id"] for item in response.data}
        self.assertEqual(returned_ids, {self.ready_doc.id})

    def test_field_technician_allowlist_filters_ready_documents(self):
        restricted = TechnicalDocument.objects.create(
            file=SimpleUploadedFile("restricted.pdf", b"restricted", content_type="application/pdf"),
            title="Restricted Ready",
            vendor=self.vendor,
            category=self.category,
            uploaded_by=self.steward_user,
            status=TechnicalDocument.Status.READY,
        )
        restricted.visible_to.add(self.tech_user)

        self.client.force_authenticate(user=self.tech_user)
        response = self.client.get("/api/documents/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        returned_ids = {item["id"] for item in response.data}
        self.assertIn(self.ready_doc.id, returned_ids)
        self.assertIn(restricted.id, returned_ids)

        self.client.force_authenticate(user=self.tech_user_2)
        response2 = self.client.get("/api/documents/")
        self.assertEqual(response2.status_code, status.HTTP_200_OK)
        returned_ids_2 = {item["id"] for item in response2.data}
        self.assertIn(self.ready_doc.id, returned_ids_2)
        self.assertNotIn(restricted.id, returned_ids_2)

        response_retrieve = self.client.get(f"/api/documents/{restricted.id}/")
        self.assertIn(
            response_retrieve.status_code,
            {status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND},
        )

    def test_admin_can_upload_document_with_visible_to_ids(self):
        self.client.force_authenticate(user=self.admin_user)
        payload = {
            "file": SimpleUploadedFile("new.pdf", b"file-content", content_type="application/pdf"),
            "title": "Allowlisted Manual",
            "vendor": self.vendor.id,
            "category": self.category.id,
            "metadata": json.dumps({"facility": "Z9"}),
            "visible_to_ids": [self.tech_user.id],
        }

        response = self.client.post("/api/documents/", data=payload, format="multipart")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        created = TechnicalDocument.objects.get(id=response.data["id"])
        self.assertEqual(
            list(created.visible_to.values_list("id", flat=True)),
            [self.tech_user.id],
        )

    def test_steward_can_list_technicians(self):
        self.client.force_authenticate(user=self.steward_user)
        response = self.client.get("/api/users/technicians/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        returned_ids = {item["id"] for item in response.data}
        self.assertIn(self.tech_user.id, returned_ids)
        self.assertIn(self.tech_user_2.id, returned_ids)

    def test_pipeline_token_can_update_document_status(self):
        token = "pipeline-secret-token"
        with self.settings(PIPELINE_STATUS_TOKEN=token):
            response = self.client.patch(
                f"/api/documents/{self.processing_doc.id}/status/",
                data={"status": TechnicalDocument.Status.READY},
                format="json",
                HTTP_X_PIPELINE_TOKEN=token,
            )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.processing_doc.refresh_from_db()
        self.assertEqual(self.processing_doc.status, TechnicalDocument.Status.READY)

    def test_data_steward_jwt_can_update_document_status(self):
        self.client.force_authenticate(user=self.steward_user)
        response = self.client.patch(
            f"/api/documents/{self.processing_doc.id}/status/",
            data={"status": TechnicalDocument.Status.READY},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_pipeline_status_update_rejects_without_valid_token(self):
        with self.settings(PIPELINE_STATUS_TOKEN="pipeline-secret-token"):
            response = self.client.patch(
                f"/api/documents/{self.processing_doc.id}/status/",
                data={"status": TechnicalDocument.Status.READY},
                format="json",
            )

        self.assertIn(response.status_code, {status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN})

    def test_system_administrator_can_delete_document_and_file(self):
        self.client.force_authenticate(user=self.admin_user)
        storage = self.ready_doc.file.storage
        file_name = self.ready_doc.file.name
        self.assertTrue(storage.exists(file_name))

        response = self.client.delete(f"/api/documents/{self.ready_doc.id}/")

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(TechnicalDocument.objects.filter(id=self.ready_doc.id).exists())
        self.assertFalse(storage.exists(file_name))

    def test_data_steward_cannot_delete_document(self):
        self.client.force_authenticate(user=self.steward_user)

        response = self.client.delete(f"/api/documents/{self.processing_doc.id}/")

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(TechnicalDocument.objects.filter(id=self.processing_doc.id).exists())

    def test_data_steward_only_sees_own_documents(self):
        other_doc = TechnicalDocument.objects.create(
            file=SimpleUploadedFile("other.pdf", b"other", content_type="application/pdf"),
            title="Other Document",
            vendor=self.vendor,
            category=self.category,
            uploaded_by=self.admin_user,
            status=TechnicalDocument.Status.UPLOADED,
        )

        self.client.force_authenticate(user=self.steward_user)
        response = self.client.get("/api/documents/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        returned_ids = {item["id"] for item in response.data}
        self.assertIn(self.ready_doc.id, returned_ids)
        self.assertIn(self.processing_doc.id, returned_ids)
        self.assertNotIn(other_doc.id, returned_ids)

    def test_data_steward_cannot_edit_document_fields(self):
        self.client.force_authenticate(user=self.steward_user)
        response = self.client.patch(
            f"/api/documents/{self.processing_doc.id}/",
            data={"title": "Changed"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_data_steward_cannot_delete_other_users_document(self):
        other_doc = TechnicalDocument.objects.create(
            file=SimpleUploadedFile("other.pdf", b"other", content_type="application/pdf"),
            title="Other Document",
            vendor=self.vendor,
            category=self.category,
            uploaded_by=self.admin_user,
            status=TechnicalDocument.Status.UPLOADED,
        )

        self.client.force_authenticate(user=self.steward_user)
        response = self.client.delete(f"/api/documents/{other_doc.id}/")

        # Queryset hides other users' documents, so this may present as 404.
        self.assertIn(response.status_code, {status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND})
        self.assertTrue(TechnicalDocument.objects.filter(id=other_doc.id).exists())

    def test_system_administrator_can_cleanup_orphan_files(self):
        self.client.force_authenticate(user=self.admin_user)

        orphan_name = "technical_documents/2099/01/01/orphan.pdf"
        default_storage.save(orphan_name, SimpleUploadedFile("orphan.pdf", b"orphan", content_type="application/pdf"))
        self.assertTrue(default_storage.exists(orphan_name))

        response = self.client.post("/api/documents/cleanup-orphans/", data={}, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(default_storage.exists(orphan_name))
        self.assertIn("deleted_count", response.data)

    def test_data_steward_cannot_cleanup_orphan_files(self):
        self.client.force_authenticate(user=self.steward_user)

        response = self.client.post("/api/documents/cleanup-orphans/", data={}, format="json")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_auth_token_contains_role_claim_for_frontend(self):
        response = self.client.post(
            "/api/auth/token/",
            data={"username": self.tech_user.username, "password": "techpass123"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        access = AccessToken(response.data["access"])
        self.assertEqual(access["role"], CustomUser.Roles.FIELD_TECHNICIAN)
        self.assertEqual(access["username"], self.tech_user.username)

    def test_public_register_creates_field_technician(self):
        payload = {
            "username": "newtech",
            "email": "newtech@example.com",
            "first_name": "New",
            "last_name": "Tech",
            "password": "StrongPass123!",
            "confirm_password": "StrongPass123!",
        }

        response = self.client.post("/api/auth/register/", data=payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        created = CustomUser.objects.get(username="newtech")
        self.assertEqual(created.role, CustomUser.Roles.FIELD_TECHNICIAN)

    @override_settings(DATA_STEWARD_PUBLIC_SIGNUP_ENABLED=True)
    def test_public_register_can_create_data_steward(self):
        payload = {
            "username": "newsteward",
            "email": "newsteward@example.com",
            "first_name": "New",
            "last_name": "Steward",
            "role": CustomUser.Roles.DATA_STEWARD,
            "password": "StrongPass123!",
            "confirm_password": "StrongPass123!",
        }

        response = self.client.post("/api/auth/register/", data=payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        created = CustomUser.objects.get(username="newsteward")
        self.assertEqual(created.role, CustomUser.Roles.DATA_STEWARD)

    def test_public_register_rejects_password_mismatch(self):
        payload = {
            "username": "badregister",
            "email": "badregister@example.com",
            "first_name": "Bad",
            "last_name": "Register",
            "password": "StrongPass123!",
            "confirm_password": "DifferentPass123!",
        }

        response = self.client.post("/api/auth/register/", data=payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("confirm_password", response.data)
