from rest_framework import viewsets

from .models import Doctor
from .serializers import DoctorSerializer


class DoctorViewSet(viewsets.ModelViewSet):
    serializer_class = DoctorSerializer
    queryset = Doctor.objects.select_related("hospital").all()

    def get_queryset(self):
        queryset = super().get_queryset()
        hospital_id = self.request.query_params.get("hospital")
        specialization = self.request.query_params.get("specialization")
        employee_type = self.request.query_params.get("employee_type")

        if hospital_id:
            queryset = queryset.filter(hospital_id=hospital_id)
        if specialization:
            queryset = queryset.filter(specialization__icontains=specialization)
        if employee_type:
            queryset = queryset.filter(employee_type=employee_type)

        return queryset