from sqlmodel import Session, select

from database.logging.models import (
    RecoveryContext,
    RecoveryErroredActivity,
    RecoveryUiLogEntry,
    RobotException,
)


def test_recovery_context_links_to_robot_exception(session: Session):
    robot_exception = RobotException(exception_details={"message": "failed"})
    session.add(robot_exception)
    session.commit()
    session.refresh(robot_exception)

    recovery_context = RecoveryContext(
        task_name="Invoice Recovery",
        platform="uipath",
        os="windows",
        variables={"invoice_id": "INV-001"},
    )
    recovery_context.robot_exception = robot_exception
    session.add(recovery_context)
    session.commit()
    session.refresh(recovery_context)

    assert recovery_context.robot_exception_id == robot_exception.id
    assert recovery_context.robot_exception is not None
    assert recovery_context.robot_exception.id == robot_exception.id


def test_recovery_context_persists_normalized_payload_fields(session: Session):
    robot_exception = RobotException(exception_details={"message": "failed"})
    session.add(robot_exception)
    session.commit()
    session.refresh(robot_exception)

    recovery_context = RecoveryContext.from_payload(
        payload={
            "task_name": "Invoice Recovery",
            "platform": "uipath",
            "os": "windows",
            "variables": {"invoice_id": "INV-001"},
            "ui_log": [
                {
                    "case_id": 1,
                    "activity_id": 100,
                    "event_id": 10,
                    "event_name": "InvoiceOpened",
                    "activity_name": "OpenInvoice",
                    "action_type": "click",
                    "application": "SAP",
                    "input": "INV-001",
                    "ui_element_target": "Open Invoice",
                    "ui_group": "Invoice List",
                    "timestamp": "2026-04-17T10:00:00Z",
                    "previous_state": None,
                    "current_state": "opened",
                }
            ],
            "errored_act": {
                "case_id": 2,
                "activity_id": 200,
                "event_id": 20,
                "event_name": "SubmitFailed",
                "activity_name": "Submit",
                "action_type": "click",
                "application": "SAP",
                "input": None,
                "error_code": "E500",
                "error_description": "Submit button disabled",
            },
            "model": "<process id='invoice-recovery' />",
        },
    )
    recovery_context.robot_exception = robot_exception
    session.add(recovery_context)
    session.commit()

    stored_context = session.exec(
        select(RecoveryContext).where(RecoveryContext.id == recovery_context.id)
    ).one()
    assert stored_context.robot_exception_id == robot_exception.id
    assert stored_context.task_name == "Invoice Recovery"
    assert stored_context.platform == "uipath"
    assert stored_context.os == "windows"
    assert stored_context.variables == {"invoice_id": "INV-001"}
    assert len(stored_context.ui_log_entries) == 1
    assert stored_context.ui_log_entries[0].case_id == "1"
    assert stored_context.ui_log_entries[0].event_id == "10"
    assert stored_context.ui_log_entries[0].activity_id == "100"
    assert stored_context.ui_log_entries[0].previous_state is None
    assert stored_context.errored_activity is not None
    assert stored_context.errored_activity.case_id == "2"
    assert stored_context.errored_activity.event_id == "20"
    assert stored_context.errored_activity.activity_id == "200"
    assert stored_context.errored_activity.input is None
    assert stored_context.model == "<process id='invoice-recovery' />"


def test_recovery_context_to_payload_returns_normalized_shape():
    recovery_context = RecoveryContext(
        task_name="Invoice Recovery",
        platform="uipath",
        os="windows",
        variables={"invoice_id": "INV-001"},
        model="<process id='invoice-recovery' />",
    )
    recovery_context.ui_log_entries = [
        RecoveryUiLogEntry(
            position=0,
            case_id="CASE-1",
            activity_id=None,
            event_id="EVT-1",
            event_name="InvoiceOpened",
            activity_name=None,
            action_type="click",
            application=None,
            input=None,
            ui_element_target=None,
            ui_group=None,
            timestamp="2026-04-17T10:00:00Z",
            previous_state=None,
            current_state=None,
        )
    ]
    recovery_context.errored_activity = RecoveryErroredActivity(
        case_id="CASE-1",
        activity_id=None,
        event_id="EVT-2",
        event_name="SubmitFailed",
        activity_name=None,
        action_type="click",
        application=None,
        input=None,
        error_code="E500",
        error_description="Submit button disabled",
    )

    payload = recovery_context.model_dump()

    assert payload["task_name"] == "Invoice Recovery"
    assert payload["variables"]["invoice_id"] == "INV-001"
    assert payload["ui_log"][0]["case_id"] == "CASE-1"
    assert payload["ui_log"][0]["event_id"] == "EVT-1"
    assert payload["ui_log"][0]["activity_name"] is None
    assert payload["errored_act"]["case_id"] == "CASE-1"
    assert payload["errored_act"]["event_id"] == "EVT-2"
    assert payload["errored_act"]["input"] is None
    assert payload["model"] == "<process id='invoice-recovery' />"


def test_recovery_context_from_payload_accepts_nullable_fields() -> None:
    recovery_payload = {
        "task_name": "Invoice Recovery",
        "platform": "uipath",
        "os": "windows",
        "variables": {},
        "ui_log": [
            {
                "case_id": "CASE-1",
                "activity_id": None,
                "event_id": "EVT-1",
                "event_name": "InvoiceOpened",
                "activity_name": None,
                "action_type": "click",
                "application": None,
                "input": None,
                "ui_element_target": None,
                "ui_group": None,
                "timestamp": "2026-04-17T10:00:00Z",
                "previous_state": None,
                "current_state": None,
            }
        ],
        "errored_act": {
            "case_id": "CASE-1",
            "activity_id": None,
            "event_id": "EVT-2",
            "event_name": "SubmitFailed",
            "activity_name": None,
            "action_type": "click",
            "application": None,
            "input": None,
            "error_code": "E500",
            "error_description": "Submit button disabled",
        },
        "model": "<process id='invoice-recovery' />",
    }

    context = RecoveryContext.from_payload(payload=recovery_payload)

    assert context.ui_log_entries[0].activity_id is None
    assert context.ui_log_entries[0].activity_name is None
    assert context.ui_log_entries[0].application is None
    assert context.ui_log_entries[0].input is None
    assert context.errored_activity is not None
    assert context.errored_activity.activity_id is None
    assert context.errored_activity.activity_name is None
    assert context.errored_activity.application is None
    assert context.errored_activity.input is None
