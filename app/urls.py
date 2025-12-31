from django.urls import path
from .views import *

urlpatterns = [
    # list & detail (required if you use a ReadOnlyModelViewSet)
    path(
        "submissions/",
        RouteSubmissionViewSet.as_view({"get": "list"}),
        name="route-submission-list",
    ),
    path(
        "submissions/<int:pk>/",
        RouteSubmissionViewSet.as_view({"get": "retrieve"}),
        name="route-submission-detail",
    ),

    # custom detail actions
    path(
        "submissions/<int:pk>/approve/",
        RouteSubmissionViewSet.as_view({"post": "approve"}),
        name="route-submission-approve",
    ),
    path(
        "submissions/<int:pk>/reject/",
        RouteSubmissionViewSet.as_view({"post": "reject"}),
        name="route-submission-reject",
    ),
    path("routes/<int:pk>/", RouteView.as_view(), name="route-detail"),
    path("route-steps/<step_id>/fares/", StepFareView.as_view(), name="stepfare-detail"),
    path("search/destinations/",DestinationSearchView.as_view(), name="search-destinations"),
    path("search/destinations/<int:destination_id>/starting-places/",StartingPlaceSearchView.as_view(),name="search-starting-places"),
    path("routes/lookup/",RouteLookupView.as_view(),name="route-lookup"),
    path("submissions/submit-route", SubmitRouteView.as_view(), name="submit-route"),

]