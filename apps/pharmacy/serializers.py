
from rest_framework import serializers

from .models import MedicineCategory


class MedicineCategorySerializer(serializers.ModelSerializer):

    class Meta:
        model = MedicineCategory
        fields = [
            "id",
            "hospital",
            "name",
            "description",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "created_at",
            "updated_at",
        ]

    def validate(self, attrs):
        if self.instance and "hospital" in attrs:
            if attrs["hospital"].id != self.instance.hospital_id:
                raise serializers.ValidationError({
                    "hospital": "Hospital cannot be changed."
                })

        return attrs
