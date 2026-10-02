"""What each role may do on a Patient Queue visit (Task 6d, D3).

ONE MAPPING: queue status x role -> the actions allowed. Three things read it, so the
buttons and the server rules cannot drift apart: the queue draws exactly these actions
(models/appointments.py attach_actions()); the server checks it before it does any of
them (routes/appointment_views.py); and the status lists the SQL rules use (where a
visit can be marked as left, where its service can be corrected) are read off it.
It says what a role is ALLOWED to do on a status. Whether it fits this one visit right
now is a second question, answered from the visit: the room must be free to Start, a
visit with a diagnosis cannot be marked as left, Undo is for the day it was set, and a
service that needs the Doctor is sent to him instead of being completed.

Roles are the canonical names of utils/roles.py normalize_role(). The Administrator and
the Barangay Official are in no row: they only view.
"""
from models.doctor_worklist import WAITING_FOR_DOCTOR
from utils.roles import normalize_role

WAITING = "Waiting"
IN_CONSULTATION = "In Consultation"
COMPLETED = "Completed"
LEFT = "Left before being seen"

# The actions.
START = "start"                      # bring a waiting patient in
OPEN_INTAKE = "open_intake"          # write up the visit in progress (Record Consultation)
SEND_TO_DOCTOR = "send_to_doctor"    # send the visit in progress to the Doctor
MARK_COMPLETED = "mark_completed"    # close the visit in progress (a service with no Doctor)
SEE_PATIENT = "see_patient"          # the Doctor sees a visit waiting for him
MARK_LEFT = "mark_left"              # left before being seen
UNDO_LEFT = "undo_left"              # same-day undo of the above
CHANGE_SERVICE = "change_service"    # correct the visit's service

ACTIONS = (START, OPEN_INTAKE, SEND_TO_DOCTOR, MARK_COMPLETED, SEE_PATIENT,
           MARK_LEFT, UNDO_LEFT, CHANGE_SERVICE)

DOCTOR, STAFF = "doctor", "health staff"

# status -> role -> actions. A status or a role that is not here has no action.
QUEUE_ACTIONS = {
    WAITING: {
        STAFF: (START, MARK_LEFT, CHANGE_SERVICE),
        DOCTOR: (START, MARK_LEFT, CHANGE_SERVICE),
    },
    IN_CONSULTATION: {
        STAFF: (OPEN_INTAKE, SEND_TO_DOCTOR, MARK_COMPLETED, MARK_LEFT, CHANGE_SERVICE),
        DOCTOR: (OPEN_INTAKE, SEND_TO_DOCTOR, MARK_COMPLETED, MARK_LEFT, CHANGE_SERVICE),
    },
    WAITING_FOR_DOCTOR: {
        STAFF: (MARK_LEFT, CHANGE_SERVICE),
        DOCTOR: (SEE_PATIENT, MARK_LEFT, CHANGE_SERVICE),
    },
    # Finished: view only.
    COMPLETED: {},
    # View only, plus the same-day undo.
    LEFT: {
        STAFF: (UNDO_LEFT,),
        DOCTOR: (UNDO_LEFT,),
    },
}

# The statuses the queue screen is made of, in the order its legend lists them.
LEGEND_STATUSES = (WAITING, IN_CONSULTATION, WAITING_FOR_DOCTOR, COMPLETED, LEFT)

# Saving a consultation record for a visit is allowed from these statuses, each under
# its own action: Staff and the Doctor take the intake of the visit in progress, and
# the Doctor sees a visit that is waiting for him.
RECORD_ACTION_BY_STATUS = {
    IN_CONSULTATION: OPEN_INTAKE,
    WAITING_FOR_DOCTOR: SEE_PATIENT,
}


def allowed_actions(role, status):
    """The actions this role may do on a visit with this status. A tuple, maybe empty."""
    return QUEUE_ACTIONS.get(status, {}).get(normalize_role(role), ())


def action_allowed(role, status, action):
    """Whether this role may do this action on a visit with this status."""
    return action in allowed_actions(role, status)


def statuses_allowing(action):
    """The statuses on which any role may do this action."""
    return tuple(
        status for status, by_role in QUEUE_ACTIONS.items()
        if any(action in actions for actions in by_role.values())
    )
