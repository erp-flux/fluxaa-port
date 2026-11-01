from django.urls import path

from . import views

app_name = "api"
C = "calls/<str:reference>/"

urlpatterns = [
    path("me/", views.MeView.as_view(), name="me"),
    path("vessels/", views.VesselView.as_view(), name="vessels"),
    path("calls/", views.CallListView.as_view(), name="calls"),
    path(C, views.CallDetailView.as_view(), name="call"),
    path(C + "actions/<str:action>/", views.CallActionView.as_view(), name="call-action"),
    path(C + "tasks/", views.TaskListView.as_view(), name="tasks"),
    path(C + "tasks/<int:task_id>/<str:action>/", views.TaskActionView.as_view(), name="task-action"),
    path(C + "milestones/", views.MilestoneListView.as_view(), name="milestones"),
    path(C + "milestones/<int:milestone_id>/countersign/", views.MilestoneCountersignView.as_view(), name="countersign"),
    path(C + "requests/", views.RequestListView.as_view(), name="requests"),
    path(C + "requests/<int:request_id>/<str:action>/", views.RequestActionView.as_view(), name="request-action"),
    path(C + "stages/", views.StageListView.as_view(), name="stages"),
    path(C + "stages/<int:stage_id>/cancel/", views.StageCancelView.as_view(), name="stage-cancel"),
    path(C + "forms/", views.FormListView.as_view(), name="forms"),
    path(C + "forms/<str:code>/", views.FormView.as_view(), name="form"),
    path(C + "documents/", views.DocumentListView.as_view(), name="documents"),
    path(C + "documents/<int:document_id>/download/", views.DocumentDownloadView.as_view(), name="document-download"),
    path(C + "documents/<int:document_id>/sign/", views.DocumentSignView.as_view(), name="document-sign"),
    path(C + "measurements/", views.MeasurementListView.as_view(), name="measurements"),
    path(C + "measurements/<int:measurement_id>/values/", views.MeasurementValueView.as_view(), name="measurement-values"),
    path(C + "pumping-log/", views.PumpingLogView.as_view(), name="pumping-log"),
    path(C + "disputes/", views.DisputeListView.as_view(), name="disputes"),
    path(C + "disputes/<int:dispute_id>/<str:action>/", views.DisputeActionView.as_view(), name="dispute-action"),
    path(C + "threads/", views.ThreadListView.as_view(), name="threads"),
    path(C + "threads/<int:thread_id>/messages/", views.ThreadMessageView.as_view(), name="thread-messages"),
    path(C + "journal/", views.JournalView.as_view(), name="journal"),
    path(C + "export/", views.ExportView.as_view(), name="export"),
    path(C + "sync/", views.SyncView.as_view(), name="sync"),
    path(C + "field-bundle/", views.FieldBundleView.as_view(), name="field-bundle"),
    path(C + "secure-deposit/", views.SecureDepositView.as_view(), name="secure-deposit"),
    path("dashboard/", views.DashboardView.as_view(), name="dashboard"),
    path("ais/", views.AisView.as_view(), name="ais"),
    path("ais/positions/", views.AisPositionsView.as_view(), name="ais_positions"),
    path("verify/<str:code>/", views.VerifyView.as_view(), name="verify"),
    path("secure/items/", views.SecureItemListView.as_view(), name="secure-items"),
    path("secure/items/<str:reference>/", views.SecureItemView.as_view(), name="secure-item"),
]
