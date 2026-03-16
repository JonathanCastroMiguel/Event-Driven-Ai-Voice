## MODIFIED Requirements

### Requirement: Mock specialist tool interface
Each mock specialist tool SHALL accept `summary` (str) and `history` (list of message dicts) as arguments. It SHALL return a complete `response.create` payload dict containing specialist instructions, conversation history, language detection, and triage steps. The Coordinator forwards this payload directly to the voice agent.

Each specialist tool SHALL have its own dedicated prompt with department-specific triage examples. The prompts SHALL NOT share a single template function. Department names SHALL appear only in English in the prompt text; the model SHALL translate department names dynamically based on the conversation language.

The triage examples SHALL be non-prescriptive — they guide the model on the type of clarifying questions to ask, but the model SHALL adapt them to the actual customer request.

#### Scenario: Mock tool returns response.create payload
- **WHEN** `specialist_retention` is called with `summary="cancellation request"` and conversation history
- **THEN** it SHALL return a dict with `type="response.create"` and `response` containing `modalities: ["text", "audio"]`, `instructions` (specialist prompt with triage steps and history), and `temperature`

#### Scenario: Per-department prompt differentiation
- **WHEN** `specialist_sales` generates its instructions
- **THEN** the instructions SHALL include sales-specific triage examples (e.g., current plan, desired features, budget)
- **WHEN** `specialist_billing` generates its instructions
- **THEN** the instructions SHALL include billing-specific triage examples (e.g., invoice number, charge date, amount)
- **WHEN** `specialist_support` generates its instructions
- **THEN** the instructions SHALL include support-specific triage examples (e.g., device/service affected, error messages, when it started)
- **WHEN** `specialist_retention` generates its instructions
- **THEN** the instructions SHALL include retention-specific triage examples (e.g., reason for leaving, how long as customer, what would change their mind)

#### Scenario: No hardcoded non-English department labels
- **WHEN** any specialist tool generates its instructions
- **THEN** the instructions text SHALL NOT contain hardcoded translations like "ventas", "facturación", "soporte técnico", or "retención"
- **AND** the instructions SHALL instruct the model to translate the department name to match the customer's language

#### Scenario: Specialist instructions include triage steps
- **WHEN** a mock specialist tool generates its instructions
- **THEN** the instructions SHALL include: (1) department identity in English, (2) department-specific triage examples, (3) triage steps (acknowledge, ask clarifying questions, then transfer), (4) language instruction (respond and translate department names in the customer's language), (5) conversation history formatted as User/Assistant turns

#### Scenario: History embedded in instructions
- **WHEN** a mock specialist tool receives a non-empty history
- **THEN** the `instructions` field SHALL include a `Conversation history:` section with all turns formatted as `User: <text>` / `Assistant: <text>`

#### Scenario: Step-awareness from history
- **WHEN** the conversation history shows the assistant has already asked clarifying questions and the customer answered
- **THEN** the specialist instructions SHALL guide the model to proceed to the transfer step
- **WHEN** the conversation history shows no prior specialist interaction
- **THEN** the specialist instructions SHALL guide the model to acknowledge and ask clarifying questions
