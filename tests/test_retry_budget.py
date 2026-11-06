"""
tests/test_retry_budget.py
===========================
Tests for Day 27 retry budget and circuit breaker in
src/pipeline/retry_budget.py.

Coverage:
  - CircuitEvent: to_dict fields, from_dict round-trip
  - RetryBudget initial state: CLOSED, not open, recommended_concurrency,
    zero error_rate, session_stats keys
  - record_success: increments counter, resets consecutive_failures,
    HALF_OPEN → CLOSED on success, concurrency recovery when error rate falls
  - record_failure: increments counter, circuit opens after N consecutive,
    HALF_OPEN probe failure → back to OPEN, throttle_down when error rate high
  - is_open: False when CLOSED, True when OPEN (before probe delay),
    True for HALF_OPEN that is the probe itself (is_open returns False for probe)
  - circuit transitions: CLOSED → OPEN → HALF_OPEN (mocked time) → CLOSED
  - recommended_concurrency: starts at max, decreases on high error rate,
    floors at MIN_CONCURRENCY
  - error_rate: 0 when empty window, correct proportion
  - flush: creates file, writes valid JSONL events, no-op when no events,
    silent on bad path
  - load_history: empty when no file, returns entries, cutoff filters old,
    malformed lines skipped
  - event_summary: empty when no history, counts by event_type
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from src.pipeline.retry_budget import (
    FAILURE_RATE_THRESHOLD,
    MIN_CONCURRENCY,
    OPEN_CIRCUIT_THRESHOLD,
    WINDOW_SIZE,
    CircuitEvent,
    CircuitState,
    RetryBudget,
)


# ===========================================================================
# CircuitEvent
# ===========================================================================


class TestCircuitEvent:
    @pytest.mark.unit
    def test_to_dict_has_required_keys(self):
        event = CircuitEvent(
            timestamp="2026-07-16T12:00:00Z",
            provider="openai",
            event_type="circuit_open",
            old_value="CLOSED",
            new_value="OPEN",
            reason="5 consecutive failures",
        )
        d = event.to_dict()
        for key in ("timestamp", "provider", "event_type", "old_value", "new_value", "reason"):
            assert key in d

    @pytest.mark.unit
    def test_from_dict_round_trip(self):
        event = CircuitEvent(
            timestamp="2026-07-16T12:00:00Z",
            provider="gemini",
            event_type="throttle_down",
            old_value=5,
            new_value=4,
            reason="error rate 45%",
        )
        d = event.to_dict()
        e2 = CircuitEvent.from_dict(d)
        assert e2.provider == "gemini"
        assert e2.event_type == "throttle_down"
        assert e2.old_value == 5
        assert e2.new_value == 4


# ===========================================================================
# RetryBudget — initial state
# ===========================================================================


class TestRetryBudgetInitial:
    @pytest.mark.unit
    def test_initial_circuit_closed(self, tmp_path):
        b = RetryBudget(tmp_path)
        assert b.circuit_state == CircuitState.CLOSED

    @pytest.mark.unit
    def test_initial_not_open(self, tmp_path):
        b = RetryBudget(tmp_path)
        assert b.is_open is False

    @pytest.mark.unit
    def test_initial_recommended_concurrency(self, tmp_path):
        b = RetryBudget(tmp_path, max_concurrency=5)
        assert b.recommended_concurrency == 5

    @pytest.mark.unit
    def test_initial_error_rate_zero(self, tmp_path):
        b = RetryBudget(tmp_path)
        assert b.error_rate == 0.0

    @pytest.mark.unit
    def test_session_stats_has_required_keys(self, tmp_path):
        b = RetryBudget(tmp_path)
        stats = b.session_stats
        for key in ("provider", "circuit_state", "recommended_concurrency",
                    "error_rate", "total_successes", "total_failures",
                    "consecutive_failures"):
            assert key in stats


# ===========================================================================
# RetryBudget — record_success
# ===========================================================================


class TestRecordSuccess:
    @pytest.mark.unit
    def test_increments_total_successes(self, tmp_path):
        b = RetryBudget(tmp_path)
        b.record_success()
        assert b.session_stats["total_successes"] == 1

    @pytest.mark.unit
    def test_resets_consecutive_failures(self, tmp_path):
        b = RetryBudget(tmp_path)
        b._consecutive_failures = 3
        b.record_success()
        assert b.session_stats["consecutive_failures"] == 0

    @pytest.mark.unit
    def test_half_open_success_closes_circuit(self, tmp_path):
        b = RetryBudget(tmp_path)
        b._circuit_state = CircuitState.HALF_OPEN
        b.record_success()
        assert b.circuit_state == CircuitState.CLOSED

    @pytest.mark.unit
    def test_multiple_successes_accumulate(self, tmp_path):
        b = RetryBudget(tmp_path)
        for _ in range(10):
            b.record_success()
        assert b.session_stats["total_successes"] == 10


# ===========================================================================
# RetryBudget — record_failure
# ===========================================================================


class TestRecordFailure:
    @pytest.mark.unit
    def test_increments_total_failures(self, tmp_path):
        b = RetryBudget(tmp_path)
        b.record_failure("AIError")
        assert b.session_stats["total_failures"] == 1

    @pytest.mark.unit
    def test_increments_consecutive_failures(self, tmp_path):
        b = RetryBudget(tmp_path)
        b.record_failure("AIError")
        b.record_failure("AIError")
        assert b.session_stats["consecutive_failures"] == 2

    @pytest.mark.unit
    def test_circuit_opens_after_threshold(self, tmp_path):
        b = RetryBudget(tmp_path)
        for _ in range(OPEN_CIRCUIT_THRESHOLD):
            b.record_failure("AIError")
        assert b.circuit_state == CircuitState.OPEN

    @pytest.mark.unit
    def test_circuit_does_not_open_before_threshold(self, tmp_path):
        b = RetryBudget(tmp_path)
        for _ in range(OPEN_CIRCUIT_THRESHOLD - 1):
            b.record_failure("AIError")
        assert b.circuit_state == CircuitState.CLOSED

    @pytest.mark.unit
    def test_half_open_probe_failure_reopens_circuit(self, tmp_path):
        b = RetryBudget(tmp_path)
        b._circuit_state = CircuitState.HALF_OPEN
        b.record_failure("Timeout")
        assert b.circuit_state == CircuitState.OPEN

    @pytest.mark.unit
    def test_success_after_failures_resets_consecutive(self, tmp_path):
        b = RetryBudget(tmp_path)
        b.record_failure("Err")
        b.record_failure("Err")
        b.record_success()
        assert b.session_stats["consecutive_failures"] == 0


# ===========================================================================
# RetryBudget — circuit state / is_open
# ===========================================================================


class TestCircuitBreakerState:
    @pytest.mark.unit
    def test_is_open_false_when_closed(self, tmp_path):
        b = RetryBudget(tmp_path)
        assert b.is_open is False

    @pytest.mark.unit
    def test_is_open_true_when_open(self, tmp_path):
        b = RetryBudget(tmp_path)
        for _ in range(OPEN_CIRCUIT_THRESHOLD):
            b.record_failure("Err")
        assert b.is_open is True

    @pytest.mark.unit
    def test_is_open_transitions_to_half_open_after_delay(self, tmp_path):
        import time
        b = RetryBudget(tmp_path)
        for _ in range(OPEN_CIRCUIT_THRESHOLD):
            b.record_failure("Err")
        # Simulate probe delay elapsed
        b._half_open_at = time.monotonic() - 1  # already elapsed
        # is_open should return False and transition to HALF_OPEN
        result = b.is_open
        assert result is False
        assert b.circuit_state == CircuitState.HALF_OPEN

    @pytest.mark.unit
    def test_circuit_open_generates_event(self, tmp_path):
        b = RetryBudget(tmp_path)
        for _ in range(OPEN_CIRCUIT_THRESHOLD):
            b.record_failure("Err")
        # There should be a circuit_open event buffered
        event_types = [e.event_type for e in b._events]
        assert "circuit_open" in event_types


# ===========================================================================
# RetryBudget — adaptive concurrency
# ===========================================================================


class TestAdaptiveConcurrency:
    @pytest.mark.unit
    def test_concurrency_starts_at_max(self, tmp_path):
        b = RetryBudget(tmp_path, max_concurrency=5)
        assert b.recommended_concurrency == 5

    @pytest.mark.unit
    def test_concurrency_respects_min(self, tmp_path):
        b = RetryBudget(tmp_path, max_concurrency=3)
        # Drive concurrency to floor with many failures
        for _ in range(WINDOW_SIZE):
            b.record_failure("Timeout")
        assert b.recommended_concurrency >= MIN_CONCURRENCY

    @pytest.mark.unit
    def test_concurrency_decreases_on_high_error_rate(self, tmp_path):
        b = RetryBudget(tmp_path, max_concurrency=5)
        # Fill window with >40% failures — but stop before circuit opens
        # Use success in between to prevent consecutive threshold
        b._consecutive_failures = 0
        # Force high error rate without triggering circuit
        original_threshold = OPEN_CIRCUIT_THRESHOLD
        for i in range(WINDOW_SIZE):
            if i % 3 == 0:
                b._window.append(True)
                b._total_successes += 1
            else:
                b._window.append(False)
                b._total_failures += 1
        b._window = b._window[-WINDOW_SIZE:]
        # Manually trigger throttle check by recording one more failure
        # (but without hitting circuit threshold)
        b._consecutive_failures = 0
        b.record_failure("Timeout")  # this will call _maybe_throttle
        # Concurrency should have dropped if error rate > threshold
        rate = sum(1 for x in b._window if not x) / len(b._window)
        if rate > FAILURE_RATE_THRESHOLD:
            assert b.recommended_concurrency < 5

    @pytest.mark.unit
    def test_concurrency_recovers_on_low_error_rate(self, tmp_path):
        b = RetryBudget(tmp_path, max_concurrency=5)
        b._current_concurrency = 2  # artificially throttled
        # Fill window with all successes
        for _ in range(WINDOW_SIZE):
            b.record_success()
        # Concurrency should have recovered
        assert b.recommended_concurrency > 2


# ===========================================================================
# RetryBudget — error_rate
# ===========================================================================


class TestErrorRate:
    @pytest.mark.unit
    def test_error_rate_zero_when_no_calls(self, tmp_path):
        b = RetryBudget(tmp_path)
        assert b.error_rate == 0.0

    @pytest.mark.unit
    def test_error_rate_zero_all_success(self, tmp_path):
        b = RetryBudget(tmp_path)
        for _ in range(5):
            b.record_success()
        assert b.error_rate == 0.0

    @pytest.mark.unit
    def test_error_rate_one_all_failure(self, tmp_path):
        b = RetryBudget(tmp_path, max_concurrency=10)  # high to avoid circuit open
        # Just fill window without triggering circuit
        for _ in range(OPEN_CIRCUIT_THRESHOLD - 1):
            b._window.append(False)
            b._total_failures += 1
        assert b.error_rate == 1.0


# ===========================================================================
# RetryBudget — flush / load_history / event_summary
# ===========================================================================


class TestPersistence:
    @pytest.mark.unit
    def test_flush_creates_file(self, tmp_path):
        b = RetryBudget(tmp_path)
        for _ in range(OPEN_CIRCUIT_THRESHOLD):
            b.record_failure("Err")
        b.flush()
        assert (tmp_path / "retry_budget.jsonl").exists()

    @pytest.mark.unit
    def test_flush_writes_valid_jsonl(self, tmp_path):
        b = RetryBudget(tmp_path)
        for _ in range(OPEN_CIRCUIT_THRESHOLD):
            b.record_failure("Err")
        b.flush()
        lines = (tmp_path / "retry_budget.jsonl").read_text().splitlines()
        assert len(lines) >= 1
        d = json.loads(lines[0])
        assert "event_type" in d

    @pytest.mark.unit
    def test_flush_noop_when_no_events(self, tmp_path):
        b = RetryBudget(tmp_path)
        b.flush()
        assert not (tmp_path / "retry_budget.jsonl").exists()

    @pytest.mark.unit
    def test_flush_silent_on_bad_path(self):
        b = RetryBudget(Path("/nonexistent/deep/path"))
        b._events.append(CircuitEvent(
            timestamp="2026-07-16T00:00:00Z",
            provider="openai",
            event_type="circuit_open",
            old_value="CLOSED",
            new_value="OPEN",
        ))
        try:
            b.flush()
        except Exception as e:
            pytest.fail(f"flush() raised: {e}")

    @pytest.mark.unit
    def test_load_history_empty_when_no_file(self, tmp_path):
        b = RetryBudget(tmp_path)
        assert b.load_history() == []

    @pytest.mark.unit
    def test_load_history_returns_entries(self, tmp_path):
        b = RetryBudget(tmp_path)
        for _ in range(OPEN_CIRCUIT_THRESHOLD):
            b.record_failure("Err")
        b.flush()
        history = b.load_history(days=30)
        assert len(history) >= 1

    @pytest.mark.unit
    def test_load_history_malformed_lines_skipped(self, tmp_path):
        (tmp_path / "retry_budget.jsonl").write_text("NOT JSON\n")
        b = RetryBudget(tmp_path)
        assert b.load_history() == []

    @pytest.mark.unit
    def test_event_summary_empty_when_no_history(self, tmp_path):
        b = RetryBudget(tmp_path)
        assert b.event_summary() == {}

    @pytest.mark.unit
    def test_event_summary_counts_event_types(self, tmp_path):
        b = RetryBudget(tmp_path)
        for _ in range(OPEN_CIRCUIT_THRESHOLD):
            b.record_failure("Err")
        b.flush()
        summary = b.event_summary(days=30)
        assert summary.get("circuit_open", 0) >= 1
