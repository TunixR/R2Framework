"""Telemetry names shared by spans and log events.

Keys follow the OpenTelemetry naming rules: lowercase, dot-separated
namespaces, ``snake_case`` within a component. Standard semantic-convention
keys are reused where one exists; the rest live under project namespaces
(``recovery.*``, ``gui.*``, ``agent.*``). Dashboards and saved queries depend
on these strings, so change them here and in OBSERVABILITY.md together.
"""

# --- Standard semantic conventions -------------------------------------------

CLIENT_ADDRESS = "client.address"
ERROR_TYPE = "error.type"
EXCEPTION_MESSAGE = "exception.message"
EXCEPTION_STACKTRACE = "exception.stacktrace"
GEN_AI_USAGE_INPUT_TOKENS = "gen_ai.usage.input_tokens"
GEN_AI_USAGE_OUTPUT_TOKENS = "gen_ai.usage.output_tokens"
HTTP_REQUEST_METHOD = "http.request.method"
HTTP_RESPONSE_STATUS_CODE = "http.response.status_code"
URL_PATH = "url.path"
# Promoted to the OTel LogRecord ``event_name`` field by the logging handler.
OTEL_EVENT_NAME = "otel.event.name"

# --- Project attributes ------------------------------------------------------

REQUEST_ID = "request.id"
REQUEST_INVALID_FIELDS = "request.invalid_fields"

ROBOT_KEY_ID = "robot_key.id"

RECOVERY_ID = "recovery.id"
RECOVERY_OUTCOME = "recovery.outcome"
RECOVERY_SUCCESS = "recovery.success"
RECOVERY_TASK_NAME = "recovery.task_name"
RECOVERY_PLATFORM = "recovery.platform"
RECOVERY_OS = "recovery.os"
RECOVERY_PROCESS_MODEL = "recovery.process_model"
RECOVERY_PAYLOAD_SIZE = "recovery.payload.size"
RECOVERY_PAYLOAD_UI_LOG_COUNT = "recovery.payload.ui_log_count"
RECOVERY_PAYLOAD_HAS_ERRORED_ACTIVITY = "recovery.payload.has_errored_activity"
RECOVERY_PAYLOAD_INVALID_FIELDS = "recovery.payload.invalid_fields"

AGENT_ID = "agent.id"
AGENT_TRACE_ID = "agent_trace.id"
AGENT_COST = "agent.cost"

GUI_TASK_NAME = "gui.task.name"
GUI_TASK_PROCESS_MODEL = "gui.task.process_model"
GUI_TASK_UI_LOG_COUNT = "gui.task.ui_log_count"
GUI_TASK_HAS_ERRORED_ACTIVITY = "gui.task.has_errored_activity"
GUI_TASK_ITERATIONS = "gui.task.iterations"
GUI_TASK_MAX_ACTIONS = "gui.task.max_actions"
GUI_TASK_OUTCOME = "gui.task.outcome"
GUI_ACTION_ITERATION = "gui.action.iteration"
GUI_ACTION_TYPE = "gui.action.type"
GUI_ACTION_SUCCESS = "gui.action.success"
GUI_SCREENSHOT_WIDTH = "gui.screenshot.width"
GUI_SCREENSHOT_HEIGHT = "gui.screenshot.height"
GUI_SCREENSHOT_SIZE = "gui.screenshot.size"

# --- Span names --------------------------------------------------------------

SPAN_RECOVERY_TURN = "recovery.turn"
SPAN_RECOVERY_PERSIST = "recovery.persist"
SPAN_RECOVERY_EVAL = "recovery.eval"
SPAN_GUI_ACTION = "gui.action"
SPAN_GUI_SCREENSHOT = "gui.screenshot"

# --- Log event names ---------------------------------------------------------
# Only things that are not already a span: rejections, recovered failures,
# misconfiguration and accounting records.

EVENT_HTTP_SERVER_ERROR = "http.server_error"
EVENT_HTTP_CLIENT_ERROR = "http.client_error"
EVENT_HTTP_VALIDATION_FAILED = "http.validation_failed"
EVENT_HTTP_UNHANDLED_EXCEPTION = "http.unhandled_exception"

EVENT_RECOVERY_AUTH_FAILED = "recovery.auth_failed"
EVENT_RECOVERY_KEEP_ALIVE_FAILED = "recovery.keep_alive_failed"
EVENT_RECOVERY_NO_GATEWAY_AGENT = "recovery.no_gateway_agent"
EVENT_RECOVERY_PAYLOAD_INVALID = "recovery.payload_invalid"
EVENT_RECOVERY_TURN_FAILED = "recovery.turn_failed"
EVENT_RECOVERY_EVAL_INVALID = "recovery.eval_invalid"

EVENT_GUI_ACTION_RETRY = "gui.action_retry"
EVENT_GUI_MAX_ACTIONS_EXCEEDED = "gui.max_actions_exceeded"

EVENT_AGENT_USAGE = "agent.usage"
