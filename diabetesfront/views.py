
from django.shortcuts import render, redirect
from django.views.decorators.http import require_POST
from django.db import transaction
from django.db.models import Q
from .models import Patient, SymptomAssessment, PredictionRecord
from django.contrib.admin.views.decorators import staff_member_required
from django.core.paginator import Paginator

import pickle
import os
import math
import logging
import re


# ============================================================
# CONFIGURATION
# ============================================================

logger = logging.getLogger(__name__)

PATIENT_SESSION_KEY = "current_patient_pk"

SYMPTOM_FIELDS = [
    "frequent_urination",
    "excessive_thirst",
    "increased_hunger",
    "unexplained_weight_loss",
    "unusual_fatigue",
    "blurred_vision",
    "slow_healing_wounds",
    "frequent_infections",
]


# ============================================================
# LOAD MACHINE LEARNING MODEL ONCE
# ============================================================

model_path = os.path.join(
    os.path.dirname(__file__),
    "models",
    "diabetes_model1.pkl"
)

with open(model_path, "rb") as model_file:
    model = pickle.load(model_file)


# ============================================================
# HOME PAGE
# ============================================================

def home(request):
    return render(request, "index.html")


# ============================================================
# SYMPTOM SCREENING PAGE
# ============================================================

def symptoms(request):

    # GET: display a fresh symptom screening page.
    if request.method == "GET":

        # Clear the previous patient's active session.
        request.session.pop(PATIENT_SESSION_KEY, None)

        return render(request, "symptoms.html")

    # Only GET and POST are supported.
    if request.method != "POST":
        return render(
            request,
            "symptoms.html",
            {"error": "Unsupported request method."},
            status=405
        )

    # --------------------------------------------------------
    # Get manually entered patient details
    # --------------------------------------------------------

    patient_id = request.POST.get(
        "patient_id", ""
    ).strip()

    patient_name = request.POST.get(
        "patient_name", ""
    ).strip()

    # Preserve submitted values if validation fails.
    context = {
        "patient_id": patient_id,
        "patient_name": patient_name,
    }

    for index in range(1, 9):
        context[f"symptom{index}"] = request.POST.get(
            f"symptom{index}", ""
        )

    # --------------------------------------------------------
    # Validate patient details
    # --------------------------------------------------------

    if not re.fullmatch(r"[A-Za-z0-9-]{3,20}", patient_id):

        context["error"] = (
            "Patient ID must contain 3 to 20 characters, "
            "using letters, numbers or hyphens."
        )

        return render(
            request,
            "symptoms.html",
            context
        )

    if not patient_name or len(patient_name) > 150:

        context["error"] = (
            "Patient name is required and must not "
            "exceed 150 characters."
        )

        return render(
            request,
            "symptoms.html",
            context
        )

    # --------------------------------------------------------
    # Validate all eight symptom responses
    # --------------------------------------------------------

    symptom_values = []

    for index in range(1, 9):

        answer = request.POST.get(
            f"symptom{index}", ""
        ).strip().lower()

        if answer not in ("yes", "no"):

            context["error"] = (
                "Please answer all eight symptom questions."
            )

            return render(
                request,
                "symptoms.html",
                context
            )

        symptom_values.append(answer == "yes")

    yes_count = sum(symptom_values)

    assessment_recommended = yes_count >= 1

    # --------------------------------------------------------
    # Register or retrieve patient
    # Save symptom assessment
    # --------------------------------------------------------

    with transaction.atomic():

        patient, created = Patient.objects.get_or_create(
            patient_id=patient_id,
            defaults={
                "patient_name": patient_name
            }
        )

        # Prevent using an existing ID for another name.
        if (
            not created
            and patient.patient_name.strip().casefold()
            != patient_name.casefold()
        ):

            context["error"] = (
                "This Patient ID is already registered "
                "under a different name. Please verify "
                "the patient details."
            )

            return render(
                request,
                "symptoms.html",
                context
            )

        symptom_data = dict(
            zip(SYMPTOM_FIELDS, symptom_values)
        )

        SymptomAssessment.objects.create(
            patient=patient,
            **symptom_data,
            yes_count=yes_count,
            assessment_recommended=assessment_recommended
        )

    # --------------------------------------------------------
    # Store active patient in the Django session
    # --------------------------------------------------------

    request.session[PATIENT_SESSION_KEY] = patient.pk

    # --------------------------------------------------------
    # Show the saved screening result
    # --------------------------------------------------------

    context.update({
        "saved": True,
        "yes_count": yes_count,
        "assessment_recommended": assessment_recommended,
        "result_heading": (
            "Further Diabetes Risk Assessment Recommended"
            if assessment_recommended
            else "No Symptom-Based Indication"
        ),
    })

    return render(
        request,
        "symptoms.html",
        context
    )


# ============================================================
# PREDICTION INPUT PAGE
# ============================================================

def predict(request):

    patient_pk = request.session.get(
        PATIENT_SESSION_KEY
    )

    if not patient_pk:
        return redirect("symptoms")

    patient = Patient.objects.filter(
        pk=patient_pk
    ).first()

    if patient is None:
        request.session.pop(PATIENT_SESSION_KEY, None)
        return redirect("symptoms")

    return render(
        request,
        "predict.html",
        {
            "patient_id": patient.patient_id,
            "patient_name": patient.patient_name,
        }
    )


# ============================================================
# RECOMMENDATIONS PAGE
# ============================================================

def recommendations(request):
    return render(
        request,
        "recommendations.html"
    )


# ============================================================
# PREDICTION RESULT AND INPUT VALIDATION
# ============================================================

@require_POST
def result(request):

    # --------------------------------------------------------
    # Retrieve the patient from the session
    # --------------------------------------------------------

    patient_pk = request.session.get(
        PATIENT_SESSION_KEY
    )

    if not patient_pk:
        return redirect("symptoms")

    patient = Patient.objects.filter(
        pk=patient_pk
    ).first()

    if patient is None:
        request.session.pop(PATIENT_SESSION_KEY, None)
        return redirect("symptoms")

    patient_id = patient.patient_id
    patient_name = patient.patient_name

    # --------------------------------------------------------
    # Define permitted input ranges
    # --------------------------------------------------------

    ranges = {
        "n1": {
            "name": "Pregnancies",
            "min": 0,
            "max": 20,
        },
        "n2": {
            "name": "Glucose",
            "min": 40,
            "max": 300,
        },
        "n3": {
            "name": "Blood Pressure",
            "min": 30,
            "max": 140,
        },
        "n4": {
            "name": "BMI",
            "min": 10,
            "max": 70,
        },
        "n5": {
            "name": "Age",
            "min": 0,
            "max": 120,
        },
    }

    # --------------------------------------------------------
    # Collect submitted values
    # --------------------------------------------------------

    values = {
        field: request.POST.get(field, "").strip()
        for field in ranges
    }

    # --------------------------------------------------------
    # Shared context for validation errors
    # --------------------------------------------------------

    def form_context(error):
        return {
            "error": error,
            "patient_id": patient_id,
            "patient_name": patient_name,
            **values,
        }

    # --------------------------------------------------------
    # Check for missing values
    # --------------------------------------------------------

    for field, rules in ranges.items():

        if values[field] == "":

            return render(
                request,
                "predict.html",
                form_context(
                    f"{rules['name']} is required."
                )
            )

    # --------------------------------------------------------
    # Convert values to numbers
    # --------------------------------------------------------

    numeric_values = {}

    for field, rules in ranges.items():

        try:

            if field in ("n1", "n5"):

                numeric_values[field] = int(
                    values[field]
                )

                if str(numeric_values[field]) != values[field]:
                    raise ValueError

            else:

                numeric_values[field] = float(
                    values[field]
                )

        except ValueError:

            message = (
                f"{rules['name']} must be a whole number."
                if field in ("n1", "n5")
                else f"{rules['name']} must be a valid number."
            )

            return render(
                request,
                "predict.html",
                form_context(message)
            )

    # --------------------------------------------------------
    # Reject invalid numbers and out-of-range values
    # --------------------------------------------------------

    for field, rules in ranges.items():

        value = numeric_values[field]

        if not math.isfinite(value):

            return render(
                request,
                "predict.html",
                form_context(
                    f"{rules['name']} must be a valid number."
                )
            )

        if (
            value < rules["min"]
            or value > rules["max"]
        ):

            return render(
                request,
                "predict.html",
                form_context(
                    f"{rules['name']} must be between "
                    f"{rules['min']} and {rules['max']}."
                )
            )

    # --------------------------------------------------------
    # Prepare model features
    # Pregnancies, Glucose, Blood Pressure, BMI, Age
    # --------------------------------------------------------

    features = [[
        numeric_values["n1"],
        numeric_values["n2"],
        numeric_values["n3"],
        numeric_values["n4"],
        numeric_values["n5"],
    ]]

    # --------------------------------------------------------
    # Generate prediction and probability
    # --------------------------------------------------------

    try:

        prediction = model.predict(features)[0]

        probabilities = model.predict_proba(
            features
        )[0]

        class_one_index = list(
            model.classes_
        ).index(1)

        risk = round(
            float(probabilities[class_one_index]) * 100,
            2
        )

    except (ValueError, AttributeError, IndexError):

        logger.exception(
            "Diabetes prediction failed"
        )

        return render(
            request,
            "predict.html",
            form_context(
                "The prediction could not be completed. "
                "Please check the values and try again."
            )
        )

    # --------------------------------------------------------
    # Determine result
    # --------------------------------------------------------

    if prediction == 1:
        result_label = "Higher Predicted Risk"
    else:
        result_label = "Lower Predicted Risk"

    # --------------------------------------------------------
    # Save prediction in the database
    # --------------------------------------------------------

    PredictionRecord.objects.create(
        patient=patient,
        pregnancies=numeric_values["n1"],
        glucose=numeric_values["n2"],
        blood_pressure=numeric_values["n3"],
        bmi=numeric_values["n4"],
        age=numeric_values["n5"],
        prediction_result=result_label,
        probability=risk
    )

    # --------------------------------------------------------
    # Display prediction result
    # --------------------------------------------------------

    context = {
        "patient_id": patient_id,
        "patient_name": patient_name,

        "result2": result_label,
        "probability": risk,

        "show_recommendations": prediction == 1,

        **values,
    }

    return render(
        request,
        "predict.html",
        context
    )

# ============================================================
# ADMINISTRATOR PATIENT RECORDS DASHBOARD
# ============================================================

@staff_member_required
def patient_records(request):

    search_query = request.GET.get("q", "").strip()
    result_filter = request.GET.get("result", "").strip()

    # --------------------------------------------------------
    # PATIENT RECORDS
    # --------------------------------------------------------

    patients = Patient.objects.all().order_by("-created_at")

    if search_query:
        patients = patients.filter(
            Q(patient_id__icontains=search_query) |
            Q(patient_name__icontains=search_query)
        )

    # --------------------------------------------------------
    # PREDICTION RECORDS
    # --------------------------------------------------------

    predictions = PredictionRecord.objects.select_related(
        "patient"
    ).order_by("-created_at")

    if search_query:
        predictions = predictions.filter(
            Q(patient__patient_id__icontains=search_query) |
            Q(patient__patient_name__icontains=search_query)
        )

    if result_filter:
        predictions = predictions.filter(
            prediction_result=result_filter
        )

    # --------------------------------------------------------
    # SYMPTOM ASSESSMENTS
    # --------------------------------------------------------

    assessments = SymptomAssessment.objects.select_related(
        "patient"
    ).order_by("-created_at")

    if search_query:
        assessments = assessments.filter(
            Q(patient__patient_id__icontains=search_query) |
            Q(patient__patient_name__icontains=search_query)
        )

    # --------------------------------------------------------
    # PAGINATION
    # --------------------------------------------------------

    patient_page = Paginator(patients, 10).get_page(
        request.GET.get("patients_page")
    )

    prediction_page = Paginator(predictions, 10).get_page(
        request.GET.get("predictions_page")
    )

    assessment_page = Paginator(assessments, 10).get_page(
        request.GET.get("assessments_page")
    )

    # --------------------------------------------------------
    # DASHBOARD STATISTICS
    # --------------------------------------------------------

    context = {
        "total_patients": Patient.objects.count(),
        "total_predictions": PredictionRecord.objects.count(),
        "total_assessments": SymptomAssessment.objects.count(),

        "patients": patient_page,
        "predictions": prediction_page,
        "assessments": assessment_page,

        "search_query": search_query,
        "result_filter": result_filter,
    }

    return render(
        request,
        "records.html",
        context
    )