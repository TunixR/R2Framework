**Version:** 2.1  
**Date:** February 25, 2026  
**Document Type:** Requirements Document (Living)

**Implementation Checklist Legend:**
- `[x]` Implemented in repository
- `[ ]` Not implemented in repository
- Notes may call out **Partial** implementations and link to evidence (repo paths/endpoints).

---

## Executive Summary

The RPA Fallback Automation Recovery System is an intelligent, agent-based platform designed to automatically detect, diagnose, and resolve runtime failures in Robotic Process Automation (RPA) and other automation solutions. The system serves as a critical safety net that intercepts automation failures, analyzes their root causes, and either resolves them autonomously or provides detailed remediation guidance to human operators.

The platform leverages advanced AI agents organized in specialized agent types (see `database/agents/models.py:AgentType`) rather than static code modules. Agent definitions, prompts, tools, and sub-agent composition are configured in the database and are populated from JSON configuration (see `database/populators/agents.py` + `database/populators/agents.json`). When a robot/orchestrator encounters a failure, it submits the exception to the recovery system which persists the exception and invokes a configured GatewayAgent to decide what to do next.

Key capabilities include agent-driven execution with tool calling, trace logging (agent/tool/GUI), robot-key based authentication for robot submissions, and provider-router configuration for LLM backends. A full cockpit UI is not present in this repository; however, backend APIs exist for authentication, trace/exception retrieval, and artifact export.

The platform addresses critical business continuity needs by minimizing automation downtime, reducing manual intervention requirements, and providing unprecedented visibility into automation health and performance patterns.

---

## 1. Functional Requirements

### 1.1 Core System Architecture

#### 1.1.1 Gateway (Ingress + GatewayAgent)
- [x] **REQ-F-001**: The system SHALL implement a central gateway that receives error notifications from external RPA orchestrators and automation systems (Partial: WebSocket robot ingestion exists via `WS /recovery/robot_exception/ws` in `routers/recovery.py`.)
- [ ] **REQ-F-002**: The gateway SHALL parse and standardize incoming error data into a common format regardless of source system (Partial: raw JSON is persisted as `RobotException.exception_details` in `database/logging/models.py`; no enforced normalization schema.)
- [x] **REQ-F-003**: The gateway SHALL maintain a registry of available recovery modules and their capabilities
- [x] **REQ-F-004**: The gateway SHALL implement intelligent routing logic to select the most appropriate module(s) for each error type
- [x] **REQ-F-005**: The gateway SHALL support multiple concurrent error handling sessions
- [x] **REQ-F-006**: The gateway SHALL log all incoming errors and routing decisions for audit purposes
- [ ] **REQ-F-007**: The gateway SHALL implement fallback mechanisms when primary module selection fails (Not implemented as explicit gateway fallback policy.)

#### 1.1.2 Recovery Agents
- [x] **REQ-F-008**: Each recovery module SHALL declare its input requirements, output capabilities, available tools, and supported error types (Inputs via `Argument`; tools via `AgentTool`/`SubAgent`; error-type via agent description)
- [x] **REQ-F-009**: Recovery Agents SHALL implement a standardized interface for communication with the gateway (Implemented via a uniform agent invocation interface `database/agents/models.py:Agent.__call__` and tool exposure `Agent.as_tool()`.)
- [x] **REQ-F-010**: Agents SHALL be capable of generating high-level execution plans for error resolution
- [x] **REQ-F-011**: Agents SHALL execute plans step-by-step with iterative decision-making after each step (Especialized agents like GUIAgent's custom flow)
- [x] **REQ-F-012**: Agents SHALL evaluate step completion status and determine next actions (continue, replan, escalate, or complete)
- [ ] **REQ-F-013**: Agents SHALL access and utilize the business knowledge base for context-aware problem solving 
- [ ] **REQ-F-014**: Agents SHALL escalate uncompletable tasks to human operators via the cockpit interface 
- [x] **REQ-F-015**: Agents SHALL provide detailed progress reporting throughout execution

### 1.2 Task Execution and Recovery

#### 1.2.1 Automation Task Completion
- [x] **REQ-F-016**: The system SHALL complete failed automation tasks using the original task context and available tools 
- [x] **REQ-F-017**: The system SHALL maintain state consistency when taking over from failed automations (Via websockets with Robots)
- [ ] **REQ-F-019**: The system SHALL validate successful task completion before marking resolution as complete
- [ ] **REQ-F-020**: The system SHALL provide rollback capabilities for failed recovery attempts

#### 1.2.2 Script Analysis and Repair
- [ ] **REQ-F-021**: When provided access to original automation scripts, the system SHALL analyze script structure and identify failure points
- [ ] **REQ-F-022**: The system SHALL determine if errors are one-time occurrences, recurring with known solutions, or recurring with unknown solutions
- [ ] **REQ-F-023**: For fixable scripts, the system SHALL generate and apply appropriate fixes automatically
- [ ] **REQ-F-024**: The system SHALL create backups of original scripts before applying any modifications
- [ ] **REQ-F-025**: The system SHALL validate script fixes through testing mechanisms where possible
- [ ] **REQ-F-026**: For unfixable scripts where solution is known, the system SHALL generate detailed repair recommendations for human operators

### 1.3 Knowledge Management

#### 1.3.1 Business Knowledge Base
- [ ] **REQ-F-027**: The system SHALL maintain a centralized business knowledge base containing proprietary application information
- [ ] **REQ-F-028**: The knowledge base SHALL store business process documentation and workflows
- [ ] **REQ-F-029**: The system SHALL support knowledge base updates and versioning
- [ ] **REQ-F-030**: Recovery modules SHALL query the knowledge base for context-specific information during problem resolution
- [ ] **REQ-F-031**: The system SHALL track knowledge base usage patterns and effectiveness

#### 1.3.2 Learning and Pattern Recognition
- [ ] **REQ-F-032**: The system SHALL analyze historical error patterns to improve future resolution strategies
- [ ] **REQ-F-033**: The system SHALL maintain a repository of successful resolution patterns for reuse
- [ ] **REQ-F-034**: The system SHALL identify recurring error types and suggest proactive fixes
- [ ] **REQ-F-035**: The system SHALL update module capabilities based on learned patterns

### 1.4 Cockpit Interface

#### 1.4.1 Authentication and Access Control
- [ ] **REQ-F-036**: The cockpit SHALL implement role-based authentication with distinct user roles (Administrator, Operator, Viewer)
- [ ] **REQ-F-037**: The cockpit SHALL support organization spaces with isolated users and data
- [ ] **REQ-F-038**: The cockpit SHALL enforce session timeout policies and automatic logout after inactivity
- [ ] **REQ-F-039**: The cockpit SHALL maintain user session audit logs including login/logout times and IP addresses
- [ ] **REQ-F-040**: The cockpit SHALL implement account lockout mechanisms after multiple failed authentication attempts
- [ ] **REQ-F-041**: The cockpit SHALL provide password complexity requirements and expiration policies
- [x] **REQ-F-042**: The cockpit SHALL support API key generation and management for programmatic access

#### 1.4.2 User Role Permissions
- [ ] **REQ-F-043**: Administrator role SHALL have full system access including module management, user administration, and system configuration
- [ ] **REQ-F-044**: Operator role SHALL have access to monitor sessions, handle escalations, approve fixes, and manage tools
- [ ] **REQ-F-045**: Viewer role SHALL have read-only access to dashboards, logs, and reports without modification capabilities
- [ ] **REQ-F-046**: Any user role SHALL have access to all audit logs, compliance reports, and historical data with export capabilities
- [ ] **REQ-F-048**: The cockpit SHALL enforce permission boundaries and prevent unauthorized access to restricted functions

#### 1.4.3 Monitoring and Oversight
- [ ] **REQ-F-049**: The cockpit SHALL provide real-time visibility into all active recovery sessions with live status updates
- [ ] **REQ-F-050**: The cockpit SHALL display detailed logs of agent actions, decision-making processes, and execution steps
- [ ] **REQ-F-051**: The cockpit SHALL categorize and display completed resolutions, failed attempts, and pending escalations
- [ ] **REQ-F-052**: The cockpit SHALL provide advanced search and filtering capabilities across historical data with date ranges, error types, and outcome filters
- [ ] **REQ-F-053**: The cockpit SHALL display system performance metrics including module response times, success rates, and resource utilization
- [ ] **REQ-F-054**: The cockpit SHALL provide customizable dashboards with drag-and-drop widgets for different user roles
- [ ] **REQ-F-055**: The cockpit SHALL support data export functionality for reports and analysis (CSV, PDF, Excel formats) 

#### 1.4.4 Logging and Audit Trail
- [ ] **REQ-F-056**: The cockpit SHALL provide hierarchical log viewing with expandable/collapsible detail levels
- [ ] **REQ-F-057**: The cockpit SHALL support log filtering by severity level, module, time range, and custom criteria
- [ ] **REQ-F-058**: The cockpit SHALL display real-time log streaming for active recovery sessions
- [ ] **REQ-F-059**: The cockpit SHALL provide log search functionality with keyword, regex, and contextual search capabilities
- [ ] **REQ-F-060**: The cockpit SHALL maintain immutable audit trails of all user actions and system events
- [ ] **REQ-F-061**: The cockpit SHALL provide log retention management with configurable archival policies
- [ ] **REQ-F-062**: The cockpit SHALL support log correlation across multiple modules and sessions

#### 1.4.5 Human Intervention Management
- [ ] **REQ-F-063**: The cockpit SHALL present escalated unresolvable errors in a prioritized queue with urgency indicators
- [ ] **REQ-F-064**: The cockpit SHALL display recommended fixes in a separate workflow section for human validation and implementation
- [ ] **REQ-F-065**: The cockpit SHALL allow human operators to approve, modify, or reject proposed fixes with mandatory comments
- [ ] **REQ-F-066**: The cockpit SHALL provide step-by-step guidance interfaces for human operators to complete escalated tasks manually
- [ ] **REQ-F-067**: The cockpit SHALL track human operator actions and outcomes for system learning and performance analysis
- [ ] **REQ-F-068**: The cockpit SHALL implement task assignment and routing to specific operators based on expertise or availability
- [ ] **REQ-F-069**: The cockpit SHALL provide collaboration tools for multiple operators to work on complex escalations
- [ ] **REQ-F-070**: The cockpit SHALL generate escalation reports with resolution times and operator performance metrics

#### 1.4.6 Module and System Management
- [ ] **REQ-F-072**: The cockpit SHALL allow administrators to enable/disable agents with immediate effect and rollback capability
- [ ] **REQ-F-073**: The cockpit SHALL display comprehensive routes status including health, performance metrics, and error rates
- [ ] **REQ-F-074**: The cockpit SHALL provide agent configuration management

#### 1.4.7 Tool Management
- [ ] **REQ-F-078**: The cockpit SHALL provide secure interfaces for disabling agent tools
- [ ] **REQ-F-079**: The cockpit SHALL allow administrators to configure granular tool access permissions for specific modules
- [ ] **REQ-F-080**: The cockpit SHALL implement tool validation
- [ ] **REQ-F-081**: The cockpit SHALL provide tool usage analytics and performance monitoring
- [ ] **REQ-F-083**: The cockpit SHALL implement tool approval workflows with administrator review and testing

#### 1.4.8 System Configuration and Administration
- [ ] **REQ-F-085**: The cockpit SHALL provide system-wide configuration management with environment-specific settings
- [ ] **REQ-F-086**: The cockpit SHALL implement configuration change approval workflows with impact analysis
- [ ] **REQ-F-087**: The cockpit SHALL provide backup and restore functionality for system configurations
- [ ] **REQ-F-088**: The cockpit SHALL support bulk operations for user management, module updates, and system maintenance
- [ ] **REQ-F-089**: The cockpit SHALL provide system health monitoring with automated alerts and threshold management
- [ ] **REQ-F-090**: The cockpit SHALL implement maintenance mode capabilities with user notification and graceful degradation

### 1.5 Integration and Communication

#### 1.5.1 External System Integration
- [x] **REQ-F-091**: The system SHALL integrate with major RPA orchestrators (UiPath, Automation Anywhere, Blue Prism, etc.) 
- [x] **REQ-F-093**: The system SHALL provide APIs for custom integrations with proprietary automation systems
- [x] **REQ-F-094**: The system SHALL support authentication methods for external system connections (X-ROBOT-KEY for robots; API keys for management APIs)
- [x] **REQ-F-095**: The system SHALL provide status callbacks to originating systems upon resolution completion

#### 1.5.2 Notification and Alerting
- [ ] **REQ-F-096**: The system SHALL send notifications to relevant stakeholders upon task completion or escalation
- [ ] **REQ-F-097**: The system SHALL support configurable notification channels
- [ ] **REQ-F-098**: The system SHALL provide SLA-based alerting for unresolved issues
- [ ] **REQ-F-099**: The system SHALL generate summary reports for management stakeholders

### 1.6 Framework Capabilities Present in Repository (new requirements)

#### 1.6.1 Robot Key Management (robot authentication)
- [x] **REQ-F-100**: The system SHALL support RobotKey issuance for authenticating robot submissions, returning the plaintext key only at creation time (Implemented: `POST /keys` in `routers/keys.py`; `RobotKeyCreated` response returns `key` once.)
- [x] **REQ-F-101**: The system SHALL store only a non-reversible hash of RobotKeys and display only masked keys thereafter (Implemented: `security/utils.py:robot_key_hash`; masked output in `routers/keys.py`.)
- [x] **REQ-F-102**: The system SHALL allow RobotKeys to be enabled/disabled and deleted (Implemented: `POST /keys/toggle/{key_id}`, `DELETE /keys/{key_id}` in `routers/keys.py`.)

#### 1.6.2 Robot Exception Ingestion and Persistence
- [x] **REQ-F-103**: The system SHALL accept robot exception submissions via WebSocket authenticated by RobotKey header `X-ROBOT-KEY` (Implemented: `WS /recovery/robot_exception/ws` in `routers/recovery.py`.)
- [x] **REQ-F-104**: The system SHALL persist each received exception payload for later inspection (Implemented: `database/logging/models.py:RobotException`.)
- [x] **REQ-F-105**: The system SHALL invoke a configured GatewayAgent for each persisted exception, passing `robot_exception_id` in invocation state (Implemented: `routers/recovery.py` + `database/agents/models.py`.)

#### 1.6.3 Agent/Tool/Provider Configuration APIs
- [x] **REQ-F-106**: The system SHALL provide CRUD APIs for Agents with admin enforcement (Implemented: `routers/agents.py`.)
- [x] **REQ-F-107**: The system SHALL provide listing APIs for Tools (Implemented: `routers/tools.py`; DB registry in `database/tools/models.py`.)
- [x] **REQ-F-108**: The system SHALL provide CRUD APIs for provider routers (LLM backends) with secret-safe public responses (Implemented: `routers/provider.py`; `database/provider/models.py:Router.model_dump` removes `api_key`.)

#### 1.6.4 Observability and Artifact Export
- [x] **REQ-F-109**: The system SHALL record agent execution traces, tool traces, and GUI traces linked to robot exceptions (Implemented: `database/logging/models.py` + hooks in `agent_tools/hooks.py`.)
- [x] **REQ-F-110**: The system SHALL expose authenticated APIs to retrieve traces and robot exceptions (Implemented: `routers/logging.py`.)
- [x] **REQ-F-111**: The system SHALL provide export of an agent trace as a markdown report (Implemented: `GET /logging/markdown/` in `routers/logging.py`.)
- [x] **REQ-F-112**: The system SHALL provide export of a UI event log as CSV alongside screenshots (Implemented: `GET /logging/ui_log/` returns ZIP in `routers/logging.py`; screenshots stored in S3 via `s3/utils.py` and `database/logging/models.py:GUITrace`.)

#### 1.6.5 Provider Routing (LLM backends)
- [x] **REQ-F-113**: The system SHALL support multiple LLM providers via a provider router abstraction configurable at runtime (Implemented: `database/provider/models.py:Router` with `provider_type` values `openai` and `openrouter`.)

#### 1.6.6 Tool Call Limits and Traceability
- [x] **REQ-F-114**: The system SHALL support per-agent limits on tool invocations and sub-agent invocations (Implemented: `database/agents/models.py:AgentTool.limit`, `database/agents/models.py:SubAgent.limit`, enforced by `agent_tools/hooks.py:LimitToolCounts`.)
- [x] **REQ-F-115**: The system SHALL log tool calls with inputs/outputs and success/failure for later inspection (Implemented: `database/logging/models.py:ToolTrace` via `agent_tools/hooks.py:ToolLoggingHook`.)



## 2. Non-Functional Requirements

### 2.1 Performance Requirements

#### 2.1.1 Response Time
- **REQ-NF-001**: The gateway SHALL acknowledge incoming error notifications within 5 seconds
- **REQ-NF-002**: Module selection and routing SHALL complete within 30 seconds of error receipt
- **REQ-NF-003**: The cockpit interface SHALL load and display current status within 3 seconds
- **REQ-NF-004**: Knowledge base queries SHALL return results within 2 seconds

#### 2.1.2 Throughput
- **REQ-NF-005**: The system SHALL handle at least 1000 concurrent error resolution sessions
- **REQ-NF-006**: The gateway SHALL process at least 100 error notifications per second
- **REQ-NF-007**: The system SHALL support at least 50 concurrent cockpit users

#### 2.1.3 Scalability
- **REQ-NF-008**: The system SHALL support horizontal scaling of recovery modules
- **REQ-NF-009**: The system SHALL handle increasing knowledge base sizes without performance degradation
- **REQ-NF-010**: The system architecture SHALL support auto-scaling based on workload demands

### 2.2 Reliability and Availability

#### 2.2.1 Availability
- **REQ-NF-011**: The system SHALL maintain 99.9% uptime availability
- **REQ-NF-012**: The system SHALL implement failover mechanisms for critical components
- **REQ-NF-013**: Planned maintenance windows SHALL not exceed 4 hours per month

#### 2.2.2 Fault Tolerance
- **REQ-NF-014**: The system SHALL continue operating with up to 25% of recovery modules unavailable
- **REQ-NF-015**: The system SHALL implement circuit breakers for external system integrations
- **REQ-NF-016**: The system SHALL gracefully handle network interruptions and connection timeouts

#### 2.2.3 Data Integrity
- **REQ-NF-017**: The system SHALL implement ACID-compliant transaction handling
- **REQ-NF-018**: The system SHALL maintain data consistency across distributed components
- **REQ-NF-019**: The system SHALL implement automated backup and recovery procedures

### 2.3 Security Requirements

#### 2.3.1 Authentication and Authorization
- [ ] **REQ-NF-020**: The system SHALL implement multi-factor authentication for cockpit access
- [x] **REQ-NF-021**: The system SHALL support role-based access control (RBAC) with granular permissions
- [ ] **REQ-NF-022**: The system SHALL integrate with enterprise identity management systems (LDAP, SAML, OAuth)
- [x] **REQ-NF-023**: The system SHALL implement API key management for external system integrations

#### 2.3.2 Data Protection
- [ ] **REQ-NF-024**: The system SHALL encrypt all data at rest
- [ ] **REQ-NF-025**: The system SHALL encrypt all data in transit
- [x] **REQ-NF-026**: The system SHALL implement data masking for sensitive information in logs and displays
- [ ] **REQ-NF-027**: The system SHALL comply with GDPR, HIPAA, and SOX requirements where applicable

#### 2.3.3 Audit and Compliance
- [ ] **REQ-NF-028**: The system SHALL maintain comprehensive audit logs of all user actions and system events
- [ ] **REQ-NF-029**: The system SHALL implement log integrity protection and tamper detection
- [ ] **REQ-NF-030**: The system SHALL support compliance reporting and audit trail generation

### 2.4 Maintainability and Modularity

#### 2.4.1 Modular Design
- [x] **REQ-NF-031**: Recovery agents SHALL be independently deployable without system downtime (Data driven)

#### 2.4.2 Monitoring and Diagnostics
- [ ] **REQ-NF-035**: The system SHALL implement comprehensive logging with configurable log levels 
- [ ] **REQ-NF-036**: The system SHALL provide health check endpoints for all components
- [x] **REQ-NF-037**: The system SHALL integrate with enterprise monitoring tools (Prometheus, Grafana, etc.)
- [x] **REQ-NF-038**: The system SHALL provide distributed tracing capabilities for debugging

#### 2.4.3 Configuration Management
- [x] **REQ-NF-039**: The system SHALL support externalized configuration management
- [ ] **REQ-NF-040**: Configuration changes SHALL be applied without system restarts where possible
- [ ] **REQ-NF-041**: The system SHALL implement configuration validation and rollback capabilities

### 2.5 Compatibility Requirements

#### 2.5.1 Integration Compatibility
- [ ] **REQ-NF-042**: The system SHALL maintain API compatibility with RPA platforms for at least 2 major versions
- [ ] **REQ-NF-043**: The system SHALL support standard protocols (REST, SOAP, GraphQL) for integrations

---

## 3. System Constraints

### 3.1 Business Constraints
- The system must minimize disruption to existing automation workflows during implementation
- The system must provide clear ROI metrics and cost justification capabilities
- The system must support gradual rollout and pilot implementations

### 3.2 Operational Constraints
- The system must operate within existing enterprise security and compliance frameworks
- The system must integrate with existing monitoring and alerting infrastructure
- The system must support 24/7 operations with minimal human oversight requirements

---

## 4. Assumptions and Dependencies

### 4.1 Assumptions
- RPA orchestrators can be configured to send error notifications to external systems
- Organizations have documented business processes and application knowledge that can be digitized
- Human operators will be available for escalated issues during business hours
- External systems provide sufficient error context for meaningful analysis

### 4.2 Dependencies
- AI/ML model availability and licensing for agent capabilities
- Integration APIs from RPA platform vendors
- Enterprise infrastructure services (databases, messaging, monitoring)
- Third-party tools and services that agents may need to utilize

---

## 5. Glossary

**Agent**: An AI-powered software component capable of autonomous decision-making and task execution
**Cockpit**: The centralized user interface for monitoring, managing, and controlling the recovery system
**Gateway**: The central routing component that receives errors and delegates them to appropriate modules
**Module (obsolete)**: In earlier designs, a specialized component designed to handle specific types of automation errors. In this repository, this maps to database-configured **Agents** (AgentType) plus tools/sub-agents and data-driven composition.
**Recovery Session**: An active instance of error resolution from initiation to completion or escalation
**RPA Orchestrator**: The central management platform that controls and monitors RPA robots
