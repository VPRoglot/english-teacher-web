import pytest

from app.leads.models import LeadStatus
from app.leads.status import MANUAL_TARGETS, TRANSITIONS, can_transition


@pytest.mark.parametrize(
    ("current", "target"),
    [
        ("new", "contacted"),
        ("new", "trial_scheduled"),
        ("new", "rejected"),
        ("contacted", "trial_scheduled"),
        ("contacted", "rejected"),
        ("trial_scheduled", "converted"),
        ("trial_scheduled", "rejected"),
        ("trial_scheduled", "contacted"),
        ("rejected", "contacted"),
    ],
)
def test_allowed_transitions(current: str, target: str) -> None:
    assert can_transition(LeadStatus(current), LeadStatus(target))


@pytest.mark.parametrize(
    ("current", "target"),
    [
        ("new", "converted"),
        ("new", "new"),
        ("contacted", "contacted"),
        ("contacted", "converted"),
        ("rejected", "rejected"),
        ("rejected", "trial_scheduled"),
        ("converted", "contacted"),
        ("converted", "rejected"),
    ],
)
def test_forbidden_transitions(current: str, target: str) -> None:
    assert not can_transition(LeadStatus(current), LeadStatus(target))


def test_converted_is_terminal() -> None:
    assert TRANSITIONS[LeadStatus.CONVERTED] == frozenset()


def test_every_status_has_a_row() -> None:
    assert set(TRANSITIONS) == set(LeadStatus)


def test_manual_targets() -> None:
    assert {LeadStatus.CONTACTED, LeadStatus.REJECTED} == MANUAL_TARGETS
