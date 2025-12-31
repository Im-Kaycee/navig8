from django.shortcuts import render, get_object_or_404
from django.db import transaction
from django.utils import timezone
from rest_framework import viewsets, status, decorators, permissions, generics
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle, UserRateThrottle
from .models import Route, RouteStep, RouteSubmission, Place, PlaceAlias
from .serializers import *
# Create your views here.

def approve_submission(submission_id, place_id, reviewer=None):
    """
    Approve a RouteSubmission by id, mapping its destination to an existing Place (place_id).
    Returns the created Route instance.
    """
    submission = get_object_or_404(RouteSubmission.objects.select_for_update(), pk=submission_id)
    if submission.status != RouteSubmission.SUBMITTED:
        raise ValueError("Submission is not in 'submitted' state")

    place = get_object_or_404(Place, pk=place_id)

    # Use the model method that handles transaction and linkage
    return submission.approve(place=place, reviewer=reviewer)

# Example reject helper
def reject_submission(submission_id, reviewer=None, admin_notes=""):
    submission = get_object_or_404(RouteSubmission.objects.select_for_update(), pk=submission_id)
    if submission.status != RouteSubmission.SUBMITTED:
        raise ValueError("Submission is not in 'submitted' state")
    return submission.reject(reviewer=reviewer, notes=admin_notes)

class IsStaffOrReadOnly(permissions.BasePermission):
    def has_permission(self, request, view):
        if view.action in ("approve", "reject"):
            return request.user and request.user.is_staff
        return True

class RouteSubmissionViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Read-only list/retrieve of submissions.
    Admin-only actions:
      - POST /submissions/{pk}/approve/  { "place_id": 123 }
      - POST /submissions/{pk}/reject/   { "admin_notes": "reason" }
    """
    queryset = RouteSubmission.objects.all().order_by("-created_at")
    serializer_class = RouteSubmissionSerializer
    permission_classes = [IsStaffOrReadOnly]
    throttle_classes = [UserRateThrottle]

    @decorators.action(detail=True, methods=["post"], url_path="approve")
    def approve(self, request, pk=None):
        # fetch & lock candidate row early
        submission = get_object_or_404(RouteSubmission.objects.select_for_update(), pk=pk)
        if submission.status != RouteSubmission.SUBMITTED:
            return Response({"detail": "Submission not in submitted state"}, status=status.HTTP_400_BAD_REQUEST)

        serializer = ApproveSubmissionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        validated = serializer.validated_data

        place = None

        # 1) explicit place_id chosen by admin
        place_id = validated.get("place_id")
        if place_id:
            place = get_object_or_404(Place, pk=place_id)
            if place.city_id != submission.city_id:
                return Response({"detail": "Place city does not match submission city"}, status=status.HTTP_400_BAD_REQUEST)

        # 2) create_place requested by admin
        elif validated.get("create_place"):
            cp = validated["create_place"]
            canonical = (cp.get("canonical_name") or submission.destination).strip()
            area = cp.get("area", "")
            place = Place.objects.filter(city=submission.city, canonical_name__iexact=canonical).first()
            if not place:
                place = Place.objects.create(city=submission.city, canonical_name=canonical, area=area)

        # 3) try auto-match by canonical_name or alias
        else:
            # try canonical name
            place = Place.objects.filter(city=submission.city, canonical_name__iexact=submission.destination.strip()).first()
            if not place:
                alias = PlaceAlias.objects.filter(place__city=submission.city, name__iexact=submission.destination.strip()).select_related("place").first()
                if alias:
                    place = alias.place

            # 4) if still not found -> auto-create using submission.destination
            if not place:
                canonical = submission.destination.strip()
                # double-check to avoid race/duplicates (case-insensitive)
                place = Place.objects.filter(city=submission.city, canonical_name__iexact=canonical).first()
                if not place:
                    place = Place.objects.create(city=submission.city, canonical_name=canonical)

        # At this point we have a Place; approve inside a transaction with re-lock
        with transaction.atomic():
            submission = RouteSubmission.objects.select_for_update().get(pk=submission.pk)
            if submission.status != RouteSubmission.SUBMITTED:
                return Response({"detail": "Submission not in submitted state"}, status=status.HTTP_400_BAD_REQUEST)
            route = submission.approve(place=place, reviewer=(request.user if request.user.is_authenticated else None))

        return Response({"route_id": route.pk}, status=status.HTTP_201_CREATED)

    @decorators.action(detail=True, methods=["post"], url_path="reject")
    def reject(self, request, pk=None):
        submission = get_object_or_404(RouteSubmission.objects.select_for_update(), pk=pk)
        if submission.status != RouteSubmission.SUBMITTED:
            return Response({"detail": "Submission not in submitted state"}, status=status.HTTP_400_BAD_REQUEST)

        serializer = RejectSubmissionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        notes = serializer.validated_data.get("admin_notes", "")

        with transaction.atomic():
            submission = RouteSubmission.objects.select_for_update().get(pk=submission.pk)
            if submission.status != RouteSubmission.SUBMITTED:
                return Response({"detail": "Submission not in submitted state"}, status=status.HTTP_400_BAD_REQUEST)
            submission.reject(reviewer=(request.user if request.user.is_authenticated else None), notes=notes)

        return Response({"detail": "rejected"}, status=status.HTTP_200_OK)
class RouteView(generics.RetrieveAPIView):
    queryset = Route.objects.all()
    serializer_class = RouteSerializer
class StepFareView(generics.ListCreateAPIView):
    serializer_class = StepFareSerializer
    def get_queryset(self):
        step_id = self.kwargs["step_id"]
        return StepFare.objects.filter(route_step_id=step_id)
    
from django.db.models import Q
    
class DestinationSearchView(generics.ListAPIView):
    serializer_class = PlaceSearchSerializer

    def get_queryset(self):
        query = self.request.query_params.get("q", "").strip()

        if not query:
            return Place.objects.none()

        return (
            Place.objects.filter(
                city__name__iexact="Abuja, NG"
            )
            .filter(
                Q(canonical_name__icontains=query) |
                Q(aliases__name__icontains=query)
            )
            .distinct()
        )
class StartingPlaceSearchView(generics.ListAPIView):
    serializer_class = PlaceSearchSerializer

    def get_queryset(self):
        destination_id = self.kwargs["destination_id"]
        query = self.request.query_params.get("q", "").strip()

        routes = Route.objects.filter(destination_id=destination_id)

        places = Place.objects.filter(
            outgoing_routes__in=routes
        )

        if query:
            places = places.filter(
                Q(canonical_name__icontains=query) |
                Q(aliases__name__icontains=query)
            )

            return places.distinct()
class RouteLookupView(generics.ListAPIView):
    serializer_class = RouteSerializer
    throttle_classes = [AnonRateThrottle, UserRateThrottle]

    def get_queryset(self):
        destination_id = self.request.query_params.get("destination")
        starting_place_id = self.request.query_params.get("start")

        if not destination_id or not starting_place_id:
            return Route.objects.none()

        return (
            Route.objects.filter(
                destination_id=destination_id,
                starting_places__id=starting_place_id
            )
            .prefetch_related("steps", "starting_places")
        )

class SubmitRouteView(generics.CreateAPIView):
    serializer_class = RouteSubmissionCreateSerializer
    throttle_classes = [AnonRateThrottle, UserRateThrottle]
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]
    def perform_create(self, serializer):
        serializer.save(submitted_by=self.request.user if self.request.user.is_authenticated else None)