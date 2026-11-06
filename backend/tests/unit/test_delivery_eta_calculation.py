import pytest
from datetime import datetime, timezone, timedelta

from app.models.delivery import DeliveryStatus
from app.services.delivery_eta import calculate_eta_components
from app.core.config import settings


def test_eta_preparation_elapsed_time_deduction():
    """Verify that elapsed preparation time is deducted correctly and capped at 0."""
    now = datetime(2026, 10, 13, 12, 0, 0, tzinfo=timezone.utc)
    
    # 1. 12 minutes expected (720s), 7 minutes elapsed (420s) -> 5 minutes remaining (300s)
    res1 = calculate_eta_components(
        delivery_status=DeliveryStatus.assigned,
        prep_expected_seconds=720,
        prep_elapsed_seconds=420,
        pickup_travel_seconds=240,
        dropoff_travel_seconds=600,
        source="osrm",
        now=now,
    )
    assert res1["breakdown"]["preparation_remaining_seconds"] == 300

    # 2. Preparation exceeded expected duration (800s elapsed > 720s expected) -> remaining is 0
    res2 = calculate_eta_components(
        delivery_status=DeliveryStatus.assigned,
        prep_expected_seconds=720,
        prep_elapsed_seconds=800,
        pickup_travel_seconds=240,
        dropoff_travel_seconds=600,
        source="osrm",
        now=now,
    )
    assert res2["breakdown"]["preparation_remaining_seconds"] == 0
    # Automatically explains delay
    assert "extra time" in res2["delay_explanation"].lower()


def test_eta_phase_buffer_inclusion_and_exclusion():
    """Verify that pickup buffers and prep are excluded once order is picked up."""
    now = datetime(2026, 10, 13, 12, 0, 0, tzinfo=timezone.utc)

    # A. Pending: Includes assignment wait, pickup buffer, dropoff travel, handoff buffer
    res_pending = calculate_eta_components(
        delivery_status=DeliveryStatus.pending,
        prep_expected_seconds=600,
        prep_elapsed_seconds=0,
        pickup_travel_seconds=0,
        dropoff_travel_seconds=720,
        source="osrm",
        now=now,
    )
    assert res_pending["breakdown"]["assignment_wait_seconds"] == settings.ETA_ASSIGNMENT_WAIT_BUFFER_SECONDS
    assert res_pending["breakdown"]["pickup_buffer_seconds"] == settings.ETA_PICKUP_BUFFER_SECONDS
    assert res_pending["breakdown"]["dropoff_travel_seconds"] == 720
    assert res_pending["breakdown"]["handoff_buffer_seconds"] == settings.ETA_DROPOFF_BUFFER_SECONDS
    assert res_pending["remaining_seconds"] == (
        600 + settings.ETA_ASSIGNMENT_WAIT_BUFFER_SECONDS + settings.ETA_PICKUP_BUFFER_SECONDS + 720 + settings.ETA_DROPOFF_BUFFER_SECONDS
    )

    # B. Assigned: Assignment wait is 0, pickup travel is included
    res_assigned = calculate_eta_components(
        delivery_status=DeliveryStatus.assigned,
        prep_expected_seconds=600,
        prep_elapsed_seconds=300,
        pickup_travel_seconds=360,
        dropoff_travel_seconds=720,
        source="osrm",
        now=now,
    )
    assert res_assigned["breakdown"]["assignment_wait_seconds"] == 0
    assert res_assigned["breakdown"]["pickup_travel_remaining_seconds"] == 360
    assert res_assigned["breakdown"]["preparation_remaining_seconds"] == 300
    assert res_assigned["breakdown"]["pickup_buffer_seconds"] == settings.ETA_PICKUP_BUFFER_SECONDS
    assert res_assigned["breakdown"]["dropoff_travel_seconds"] == 720
    assert res_assigned["breakdown"]["handoff_buffer_seconds"] == settings.ETA_DROPOFF_BUFFER_SECONDS

    # C. Out for Delivery: Prep remaining is 0, pickup travel is 0, pickup buffer is 0
    res_out = calculate_eta_components(
        delivery_status=DeliveryStatus.out_for_delivery,
        prep_expected_seconds=600,
        prep_elapsed_seconds=600,
        pickup_travel_seconds=360,
        dropoff_travel_seconds=500,
        source="osrm",
        now=now,
    )
    assert res_out["breakdown"]["preparation_remaining_seconds"] == 0
    assert res_out["breakdown"]["pickup_travel_remaining_seconds"] == 0
    assert res_out["breakdown"]["pickup_buffer_seconds"] == 0
    assert res_out["breakdown"]["dropoff_travel_seconds"] == 500
    assert res_out["breakdown"]["handoff_buffer_seconds"] == settings.ETA_DROPOFF_BUFFER_SECONDS
    assert res_out["remaining_seconds"] == 500 + settings.ETA_DROPOFF_BUFFER_SECONDS

    # D. Delivered: 0 remaining
    res_delivered = calculate_eta_components(
        delivery_status=DeliveryStatus.delivered,
        prep_expected_seconds=0,
        prep_elapsed_seconds=0,
        pickup_travel_seconds=0,
        dropoff_travel_seconds=0,
        source="osrm",
        now=now,
    )
    assert res_delivered["remaining_seconds"] == 0
    assert res_delivered["is_estimated"] is False


def test_eta_arrival_window_consistency():
    """Verify that arrival window is strictly ordered: earliest_at <= calculated_at + remaining <= latest_at."""
    now = datetime(2026, 10, 13, 12, 0, 0, tzinfo=timezone.utc)
    res = calculate_eta_components(
        delivery_status=DeliveryStatus.out_for_delivery,
        prep_expected_seconds=0,
        prep_elapsed_seconds=0,
        pickup_travel_seconds=0,
        dropoff_travel_seconds=600,
        source="osrm",
        now=now,
    )

    remaining_sec = res["remaining_seconds"]
    earliest_at = res["earliest_at"]
    latest_at = res["latest_at"]

    assert earliest_at <= now + timedelta(seconds=remaining_sec)
    assert now + timedelta(seconds=remaining_sec) <= latest_at
    assert earliest_at < latest_at
    assert res["is_estimated"] is True
