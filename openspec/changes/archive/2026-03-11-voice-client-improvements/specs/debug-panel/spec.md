## MODIFIED Requirements

### Requirement: Turn timeline specialist row rendering
The debug panel SHALL render the specialist processing row (delegate stages) starting at a dynamic horizontal offset that aligns with the `route_result` event's position in the main timeline. The specialist row SHALL visually fork from the `route_result` stage, not from the far left of the timeline.

#### Scenario: Specialist stages fork from route_result
- **WHEN** a turn includes specialist stages (`is_delegate: true`) following a `route_result` event
- **THEN** the specialist row SHALL begin rendering at the same horizontal position where `route_result` ends in the main timeline row

#### Scenario: Direct route has no specialist row
- **WHEN** a turn has `route_type="direct"` with no specialist stages
- **THEN** no specialist row SHALL be rendered

#### Scenario: Timeline resizes correctly
- **WHEN** the browser window is resized while the debug panel displays a specialist timeline
- **THEN** the specialist row offset SHALL adjust to maintain alignment with `route_result`
