## ADDED Requirements

### Requirement: Mock specialist tools registration
The system SHALL register mock specialist tools for each routing department at startup. The registered tool names SHALL be: `specialist_sales`, `specialist_billing`, `specialist_support`, `specialist_retention`. Each tool SHALL be registered via `ToolExecutor.register_tool()`.

#### Scenario: All specialist tools registered
- **WHEN** the application starts and initializes the ToolExecutor
- **THEN** the tools `specialist_sales`, `specialist_billing`, `specialist_support`, and `specialist_retention` SHALL be registered

#### Scenario: Specialist tool called by Coordinator
- **WHEN** the Coordinator calls `tool_executor.execute(tool_name="specialist_retention", args={"summary": "...", "history": [...]})`
- **THEN** the ToolExecutor SHALL find the registered tool and execute it

### Requirement: Mock specialist tool interface
Each mock specialist tool SHALL accept `summary` (str) and `history` (list of message dicts) as arguments. It SHALL return a complete `response.create` payload dict containing specialist instructions, conversation history, language detection, and triage steps. The Coordinator forwards this payload directly to the voice agent.

#### Scenario: Mock tool returns response.create payload
- **WHEN** `specialist_retention` is called with `summary="cancellation request"` and conversation history
- **THEN** it SHALL return a dict with `type="response.create"` and `response` containing `modalities: ["text", "audio"]`, `instructions` (specialist prompt with triage steps and history), and `temperature`

#### Scenario: Specialist instructions include triage steps
- **WHEN** a mock specialist tool generates its instructions
- **THEN** the instructions SHALL include: (1) department identity, (2) triage steps (acknowledge, ask clarifying questions, then transfer), (3) language instruction (respond in customer's language), (4) conversation history formatted as User/Assistant turns

#### Scenario: History embedded in instructions
- **WHEN** a mock specialist tool receives a non-empty history
- **THEN** the `instructions` field SHALL include a `Conversation history:` section with all turns formatted as `User: <text>` / `Assistant: <text>`

#### Scenario: Step-awareness from history
- **WHEN** the conversation history shows the assistant has already asked clarifying questions and the customer answered
- **THEN** the specialist instructions SHALL guide the model to proceed to the transfer step
- **WHEN** the conversation history shows no prior specialist interaction
- **THEN** the specialist instructions SHALL guide the model to acknowledge and ask clarifying questions
