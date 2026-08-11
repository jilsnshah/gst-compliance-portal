from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import HTTPException, status as http_status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.enums import (
    CA_ROLES,
    CLIENT_STATUS_LABELS,
    RETURN_LABELS,
    TRACK_STATES,
    AuditAction,
    CaseStatus,
    ClientVisibleStatus,
    NotificationType,
    ReturnStatus as S,
    ReturnType,
    Role,
    client_status_for,
    is_terminal,
    track_key,
)
from app.models import ComplianceCase, Employee, ReturnItem, StatusTransition, User
from app.services import audit, notifications

CLIENT_OR_CA = {Role.CLIENT, Role.CA_EMPLOYEE, Role.CA_ADMIN}
CA_ONLY = set(CA_ROLES)
ADMIN_ONLY = {Role.CA_ADMIN}

# The whole status machine lives here as data. Adding a return type never means
# adding transition logic -- GSTR-1, PR reconciliation and GSTR-3B share this.
ALLOWED_TRANSITIONS = {
    S.AWAITING_CLIENT_DATA: {
        S.CLIENT_DATA_SUBMITTED: CLIENT_OR_CA,
    },
    S.CLIENT_DATA_SUBMITTED: {
        S.UNDER_CA_REVIEW: CA_ONLY,
        S.AWAITING_CLIENT_DATA: CA_ONLY,  # ask for a different file
    },
    S.UNDER_CA_REVIEW: {
        # Queries, re-uploads and re-reviews all happen without leaving this
        # state -- only the CA's sign-off moves it on.
        S.VERIFIED: CA_ONLY,
        S.AWAITING_PAYMENT: CA_ONLY,  # GSTR-3B: challan issued
        S.AWAITING_CLIENT_DATA: CA_ONLY,
    },
    S.AWAITING_PAYMENT: {
        # The client's own confirmation is what clears this.
        S.VERIFIED: CLIENT_OR_CA,
        S.UNDER_CA_REVIEW: CA_ONLY,  # challan withdrawn / figures reworked
    },
    S.VERIFIED: {
        S.FILED: CA_ONLY,
        S.UNDER_CA_REVIEW: CA_ONLY,  # reopen
    },
    S.FILED: {
        S.UNDER_CA_REVIEW: ADMIN_ONLY,  # reopen a filed return
    },
}

def progress_for(return_type, status) -> int:
    """Position within this track's own chain, so GSTR-3B is not reported as
    half done the moment its month opens."""
    states = TRACK_STATES[track_key(return_type)]
    index = states.index(S(status))
    return round(100 * index / (len(states) - 1))


# Dashboard buckets for the CA "today's work" panel. "waiting_on_client" is not
# a status -- it is UNDER_CA_REVIEW with an unanswered query, resolved by the
# dashboard query itself.
WORK_BUCKETS = {
    "awaiting_data": [S.AWAITING_CLIENT_DATA],
    "to_review": [S.CLIENT_DATA_SUBMITTED, S.UNDER_CA_REVIEW],
    "awaiting_payment": [S.AWAITING_PAYMENT],
    "ready_to_file": [S.VERIFIED],
    "done": [S.FILED],
}


def client_visible_status(
    return_type, internal: S, waiting_on_client: bool = False
) -> ClientVisibleStatus:
    return client_status_for(return_type, internal, waiting_on_client)


def allowed_next(return_type, current: S, role: Role) -> list:
    """Filtered by the track: GSTR-1 is never AWAITING_PAYMENT, the purchase
    reconciliation is never FILED."""
    allowed_states = set(TRACK_STATES[track_key(return_type)])
    options = ALLOWED_TRANSITIONS.get(S(current), {})
    return [
        s.value
        for s, roles in options.items()
        if Role(role) in roles and s in allowed_states
    ]


# Exactly what is outstanding, per track and per state. One source of truth so
# the API error and the text shown on screen can never disagree.
PREREQ_TEXT = {
    ("GSTR1", S.AWAITING_CLIENT_DATA): "GSTR-1 is still waiting for the client's sales data",
    ("GSTR1", S.CLIENT_DATA_SUBMITTED): "GSTR-1 data has arrived but nobody has reviewed it",
    ("GSTR1", S.UNDER_CA_REVIEW): "GSTR-1 is still under review",
    ("GSTR1", S.VERIFIED): "GSTR-1 is signed off but has not been filed yet",
    ("PR_RECON", S.AWAITING_CLIENT_DATA): "the Purchase Register has not been uploaded",
    ("PR_RECON", S.CLIENT_DATA_SUBMITTED): "the reconciliation has not been started",
    ("PR_RECON", S.UNDER_CA_REVIEW): "the reconciliation has not been finalised",
}


def pending_prerequisites(items) -> list:
    """Which of GSTR-1 / reconciliation still block GSTR-3B, in plain words."""
    pending = []
    for i in items:
        key = track_key(i.return_type)
        if key == "GSTR3B" or is_terminal(i.return_type, i.status):
            continue
        pending.append(PREREQ_TEXT.get((key, S(i.status)), f"{key} is not finished"))
    return pending


def client_gate_reason(items, item) -> Optional[str]:
    """Why this track is not the client's problem yet.

    Sequencing is real: the Purchase Register is only asked for once GSTR-1 is
    filed, and GSTR-3B only after the reconciliation. Without this the client is
    told "Your turn" for a step that cannot sensibly start, and the dashboard
    card and the stepper end up disagreeing about the same month.
    """
    key = track_key(item.return_type)
    if key == "PR_RECON":
        gstr1 = next((i for i in items if track_key(i.return_type) == "GSTR1"), None)
        if gstr1 is not None and not is_terminal(gstr1.return_type, gstr1.status):
            return "Starts once GSTR-1 is filed"
        return None
    if key == "GSTR3B" and pending_prerequisites(items):
        return "Starts once GSTR-1 and the reconciliation are finished"
    return None


def _prerequisites_ok(db: Session, item: ReturnItem, target: S) -> Optional[str]:
    """GSTR-3B may not be signed off or filed until GSTR-1 is filed and the
    reconciliation is finalised. Returns a reason string when blocked."""
    if item.return_type != ReturnType.GSTR3B:
        return None
    # Collecting and reviewing the client's own 3B figures is fine at any time;
    # only issuing a challan, signing off or filing needs the others finished.
    if target in (S.AWAITING_CLIENT_DATA, S.CLIENT_DATA_SUBMITTED, S.UNDER_CA_REVIEW):
        return None
    siblings = db.execute(
        select(ReturnItem).where(
            ReturnItem.case_id == item.case_id,
            ReturnItem.return_type.in_([ReturnType.GSTR1, ReturnType.PR_RECON]),
        )
    ).scalars().all()
    pending = pending_prerequisites(siblings)
    if pending:
        return "GSTR-3B cannot move on because " + ", and ".join(pending)
    return None


def transition(
    db: Session,
    user: User,
    item: ReturnItem,
    to_status: S,
    note: Optional[str] = None,
    override: bool = False,
) -> ReturnItem:
    """The only legal way to change a ReturnItem status. Writes the transition
    row, the audit entry and the notification in the caller's transaction."""
    to_status = S(to_status)
    current = S(item.status)

    if to_status == current:
        return item

    if to_status not in TRACK_STATES[track_key(item.return_type)]:
        raise HTTPException(
            http_status.HTTP_409_CONFLICT,
            f"{track_key(item.return_type)} never enters {to_status.value}",
        )

    options = ALLOWED_TRANSITIONS.get(current, {})
    if to_status not in options:
        raise HTTPException(
            http_status.HTTP_409_CONFLICT,
            f"Illegal transition {current.value} -> {to_status.value}",
        )
    if Role(user.role) not in options[to_status]:
        raise HTTPException(
            http_status.HTTP_403_FORBIDDEN,
            f"Role {user.role} may not move {current.value} -> {to_status.value}",
        )

    blocked = _prerequisites_ok(db, item, to_status)
    if blocked:
        if not (override and Role(user.role) == Role.CA_ADMIN):
            raise HTTPException(http_status.HTTP_409_CONFLICT, blocked)
        audit.record(
            db,
            user,
            AuditAction.OVERRIDE,
            "ReturnItem",
            f"Admin overrode prerequisite check: {blocked}",
            target_id=item.id,
            case_id=item.case_id,
        )

    item.status = to_status
    item.updated_at = datetime.utcnow()
    if to_status == S.UNDER_CA_REVIEW:
        _claim_review(db, user, item)
    db.add(
        StatusTransition(
            return_item_id=item.id,
            from_status=current,
            to_status=to_status,
            actor_user_id=user.id,
            note=note,
        )
    )

    case = db.get(ComplianceCase, item.case_id)
    audit.record(
        db,
        user,
        AuditAction.STATUS_CHANGE,
        "ReturnItem",
        f"{item.return_type.value if hasattr(item.return_type, 'value') else item.return_type}: "
        f"{current.value} -> {to_status.value}",
        target_id=item.id,
        client_id=case.client_id,
        case_id=case.id,
        meta={"from": current.value, "to": to_status.value, "note": note},
    )
    # Two audiences, two wordings. CA staff want the internal hop; the client
    # only wants to hear when *their* view of it changes, in their own words --
    # UNDER_CA_REVIEW -> VERIFIED is still "with your CA team" and is not news.
    label = RETURN_LABELS[ReturnType(item.return_type)]
    notifications.notify(
        db,
        NotificationType.STATUS_CHANGED,
        title=f"{label}: {current.value.replace('_', ' ').title()} \u2192 "
              f"{to_status.value.replace('_', ' ').title()}",
        body=note or "",
        case=case,
        return_item=item,
        to_ca=True,
        exclude_user_id=user.id,
    )
    was = client_visible_status(item.return_type, current)
    now = client_visible_status(item.return_type, to_status)
    if now != was:
        notifications.notify(
            db,
            NotificationType.STATUS_CHANGED,
            title=f"{label} \u2014 {CLIENT_STATUS_LABELS[now]}",
            body=note or "",
            case=case,
            return_item=item,
            to_client=True,
            exclude_user_id=user.id,
        )

    _roll_up_case(db, case)
    return item


def _claim_review(db: Session, user: User, item: ReturnItem) -> None:
    """Starting a review records who actually picked the work up. The item also
    moves onto that person unless someone has deliberately assigned it, which
    is tracked by a flag rather than inferred -- an explicit assignment back to
    the GSTIN's default owner is indistinguishable from it by value alone."""
    item.review_started_by_user_id = user.id
    item.review_started_at = datetime.utcnow()

    if user.employee and not item.assignment_is_explicit:
        item.assigned_employee_id = user.employee.id


def _roll_up_case(db: Session, case: ComplianceCase) -> None:
    items = db.execute(
        select(ReturnItem).where(ReturnItem.case_id == case.id)
    ).scalars().all()
    if not items:
        return
    if all(is_terminal(i.return_type, i.status) for i in items):
        case.status = CaseStatus.COMPLETED
        case.completed_at = case.completed_at or datetime.utcnow()
    else:
        case.status = CaseStatus.IN_PROGRESS
        case.completed_at = None


def ensure_review_started(db: Session, user: User, item: ReturnItem) -> None:
    """Convenience used by CA actions: pull a submitted item into review."""
    if S(item.status) == S.CLIENT_DATA_SUBMITTED:
        transition(db, user, item, S.UNDER_CA_REVIEW, note="Review started")


def mark_data_submitted(db: Session, user: User, item: ReturnItem, note: str = "") -> None:
    """Called after a client-supplied document version lands. Only the very
    first upload moves the status; every later version is just a new version
    while the stage stays UNDER_CA_REVIEW."""
    if S(item.status) == S.AWAITING_CLIENT_DATA:
        transition(db, user, item, S.CLIENT_DATA_SUBMITTED, note=note)


def default_employee_for(db: Session, case: ComplianceCase) -> Optional[int]:
    from app.models import GSTRegistration

    entity = db.get(Entity, case.entity_id)
    if entity and entity.assigned_employee_id:
        return entity.assigned_employee_id
    emp = db.execute(select(Employee).limit(1)).scalars().first()
    return emp.id if emp else None
