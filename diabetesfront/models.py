from django.db import models


# ============================================================
# PATIENT DETAILS
# ============================================================

class Patient(models.Model):

    patient_id = models.CharField(
        max_length=20,
        unique=True
    )

    patient_name = models.CharField(
        max_length=150
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    def str(self):
        return f"{self.patient_id} - {self.patient_name}"


# ============================================================
# SYMPTOM ASSESSMENT
# ============================================================

class SymptomAssessment(models.Model):

    patient = models.ForeignKey(
        Patient,
        on_delete=models.PROTECT,
        related_name="symptom_assessments"
    )

    frequent_urination = models.BooleanField()
    excessive_thirst = models.BooleanField()
    increased_hunger = models.BooleanField()
    unexplained_weight_loss = models.BooleanField()
    unusual_fatigue = models.BooleanField()
    blurred_vision = models.BooleanField()
    slow_healing_wounds = models.BooleanField()
    frequent_infections = models.BooleanField()

    yes_count = models.PositiveSmallIntegerField()

    assessment_recommended = models.BooleanField()

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    def str(self):
        return (
            f"Symptoms - {self.patient.patient_id} "
            f"({self.created_at:%Y-%m-%d})"
        )


# ============================================================
# DIABETES PREDICTION RECORD
# ============================================================

class PredictionRecord(models.Model):

    patient = models.ForeignKey(
        Patient,
        on_delete=models.PROTECT,
        related_name="predictions"
    )

    pregnancies = models.PositiveSmallIntegerField()

    glucose = models.FloatField()

    blood_pressure = models.FloatField()

    bmi = models.FloatField()

    age = models.PositiveSmallIntegerField()

    prediction_result = models.CharField(
        max_length=30
    )

    probability = models.FloatField()

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    def str(self):
        return (
            f"Prediction - {self.patient.patient_id} "
            f"({self.created_at:%Y-%m-%d})"
        )