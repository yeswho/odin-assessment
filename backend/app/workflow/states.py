from enum import StrEnum


class Status(StrEnum):
    RECEIVED = "RECEIVED"
    ANALYSING = "ANALYSING"
    READY_FOR_REVIEW = "READY_FOR_REVIEW"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


TRANSITIONS: dict[Status, frozenset[Status]] = {
    Status.RECEIVED: frozenset({Status.ANALYSING}),
    Status.ANALYSING: frozenset({Status.READY_FOR_REVIEW, Status.FAILED}),
    Status.READY_FOR_REVIEW: frozenset({Status.COMPLETED}),
    Status.FAILED: frozenset({Status.ANALYSING}),
    Status.COMPLETED: frozenset(),
}


def can_transition(current: Status, target: Status) -> bool:
    return target in TRANSITIONS[current]
