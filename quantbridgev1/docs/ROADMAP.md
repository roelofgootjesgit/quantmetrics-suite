# QuantBridge v1 Roadmap

## Milestone A - Mock Abstraction

- [x] canonical broker contract
- [x] cTrader broker adapter
- [x] symbol registry
- [x] error taxonomy
- [x] smoke tests in mock mode

## Milestone B - Real cTrader Demo Execution

- [ ] cTrader Open API auth and session lifecycle
- [ ] account selection and state fetch
- [ ] price endpoint wiring
- [ ] market order submit
- [ ] open trade fetch
- [ ] close trade
- [ ] structured logs with request_id

## Milestone C - Reconciliation and Restart Safety

- [ ] persist last known broker state snapshot
- [ ] sync_positions after restart
- [ ] duplicate detection by client_order_ref
- [ ] desync detector and recovery actions

## Milestone D - Prop Risk Above Broker Layer

- [ ] daily drawdown blocking
- [ ] max open risk at account level
- [ ] pause and quarantine account states
- [ ] challenge vs funded risk profiles

## Milestone E - Multi-Account Scaling

- [ ] account-aware routing
- [ ] fanout execution modes
- [ ] failover policy
- [ ] account health scheduler
