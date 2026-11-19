from django.contrib import admin
from .models import Patient, SymptomAssessment, PredictionRecord


@admin.register(Patient)
class PatientAdmin(admin.ModelAdmin):
    list_display = (
        "patient_id",
        "patient_name",
        "created_at",
    )
    search_fields = (
        "patient_id",
        "patient_name",
    )


@admin.register(SymptomAssessment)
class SymptomAssessmentAdmin(admin.ModelAdmin):
    list_display = (
        "patient",
        "yes_count",
        "assessment_recommended",
        "created_at",
    )
    list_filter = (
        "assessment_recommended",
        "created_at",
    )
    search_fields = (
        "patient__patient_id",
        "patient__patient_name",
    )


@admin.register(PredictionRecord)
class PredictionRecordAdmin(admin.ModelAdmin):
    list_display = (
        "patient",
        "prediction_result",
        "probability",
        "created_at",
    )
    list_filter = (
        "prediction_result",
        "created_at",
    )
    search_fields = (
        "patient__patient_id",
        "patient__patient_name",
    )