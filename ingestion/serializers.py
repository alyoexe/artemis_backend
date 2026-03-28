from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from ingestion.models import CustomUser, EquipmentCategory, TechnicalDocument, Vendor


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token["role"] = user.role
        token["username"] = user.username
        return token


class RegistrationSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=True)
    confirm_password = serializers.CharField(write_only=True, required=True)
    role = serializers.ChoiceField(
        choices=[CustomUser.Roles.FIELD_TECHNICIAN, CustomUser.Roles.DATA_STEWARD],
        required=False,
    )

    class Meta:
        model = CustomUser
        fields = ["username", "email", "first_name", "last_name", "role", "password", "confirm_password"]

    def validate(self, attrs):
        if attrs["password"] != attrs["confirm_password"]:
            raise serializers.ValidationError({"confirm_password": ["Passwords do not match."]})
        return attrs

    def create(self, validated_data):
        validated_data.pop("confirm_password")
        password = validated_data.pop("password")
        role = validated_data.pop("role", CustomUser.Roles.FIELD_TECHNICIAN)

        user = CustomUser(**validated_data)
        user.role = role
        user.set_password(password)
        user.save()
        return user


class CustomUserSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=False)

    class Meta:
        model = CustomUser
        fields = ["id", "username", "email", "first_name", "last_name", "role", "password"]
        read_only_fields = ["id"]

    def create(self, validated_data):
        password = validated_data.pop("password", None)
        user = CustomUser(**validated_data)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save()
        return user

    def update(self, instance, validated_data):
        password = validated_data.pop("password", None)

        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        if password:
            instance.set_password(password)

        instance.save()
        return instance


class EquipmentCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = EquipmentCategory
        fields = ["id", "name", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]


class VendorSerializer(serializers.ModelSerializer):
    class Meta:
        model = Vendor
        fields = ["id", "name", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]


class TechnicalDocumentSerializer(serializers.ModelSerializer):
    uploaded_by = CustomUserSerializer(read_only=True)
    visible_to = serializers.PrimaryKeyRelatedField(many=True, read_only=True)
    visible_to_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        required=False,
        write_only=True,
    )

    class Meta:
        model = TechnicalDocument
        fields = [
            "id",
            "file",
            "title",
            "vendor",
            "category",
            "uploaded_by",
            "visible_to",
            "visible_to_ids",
            "status",
            "metadata",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "uploaded_by", "status", "created_at", "updated_at"]

    def validate_visible_to_ids(self, value):
        if not value:
            return []

        unique_ids = list(dict.fromkeys(value))
        valid_ids = set(
            CustomUser.objects.filter(
                id__in=unique_ids,
                role=CustomUser.Roles.FIELD_TECHNICIAN,
            ).values_list("id", flat=True)
        )
        invalid = [user_id for user_id in unique_ids if user_id not in valid_ids]
        if invalid:
            raise serializers.ValidationError(
                "All visible_to_ids must refer to Field Technicians."
            )
        return unique_ids

    def create(self, validated_data):
        visible_to_ids = validated_data.pop("visible_to_ids", None)
        document = super().create(validated_data)
        if visible_to_ids is not None:
            document.visible_to.set(visible_to_ids)
        return document

    def update(self, instance, validated_data):
        visible_to_ids = validated_data.pop("visible_to_ids", None)
        document = super().update(instance, validated_data)
        if visible_to_ids is not None:
            document.visible_to.set(visible_to_ids)
        return document


class TechnicalDocumentStatusUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = TechnicalDocument
        fields = ["status"]
