# User Acceptance Test Plan

**Version**: 1.0  
**Date**: December 11, 2024  
**System**: ClaudeVN Emergent Workflow Platform  
**Status**: Ready for UAT

---

## Executive Summary

This document provides a comprehensive test plan for user acceptance testing of ClaudeVN's emergent workflow system. The system has completed 6 weeks of implementation and is ready for real-world validation.

**Key Capabilities Being Tested:**
- ✅ Emergent workflow creation from business goals
- ✅ Conversation-driven activity facilitation
- ✅ Automatic blocker detection and resolution
- ✅ Self-correction through consistency checking
- ✅ Process map evolution and tracking
- ✅ Result synthesis and goal assessment

---

## Test Environment

### Services Required
All three services must be running:

| Service | Port | URL | Purpose |
|---------|------|-----|---------|
| Marketplace | 8001 | http://localhost:8001 | Agent discovery |
| Serving | 8002 | http://localhost:8002 | Orchestration hub |
| Compute | 8003 | http://localhost:8003 | Agent execution |

### Starting Services
```bash
# Start all services
./start_all.sh

# Verify health
./status.sh

# Check individual services
curl http://localhost:8001/health
curl http://localhost:8002/api/v1/health
curl http://localhost:8003/api/v1/health
```

### Test Data Requirements
- Access to test user accounts
- Sample business goals (provided below)
- API access credentials (if authentication enabled)

---

## Automated Test Execution

### Quick Test Run
```bash
# Run all automated tests
./run_all_tests.sh
```

### Test Phases
The automated test suite runs in 5 phases:

1. **Service Health Checks** - Verify all services are running
2. **API Integration Tests** - Test individual service endpoints
3. **System Integration Tests** - Test cross-service communication
4. **User Acceptance Tests** - Test end-to-end scenarios
5. **Unit Tests** - Validate Week 1-6 implementation

**Expected Duration**: 5-10 minutes  
**Expected Pass Rate**: 100%

### Manual Test Execution
If you want to run specific test suites:

```bash
# API Integration Tests
python3 -m pytest compute/test_api_integration.py -v
python3 -m pytest serving/tests/test_api_integration.py -v
python3 -m pytest marketplace/tests/test_api_integration.py -v

# System Integration
python3 -m pytest tests/test_system_integration.py -v

# User Scenarios
python3 -m pytest tests/test_user_scenarios.py -v

# Week 1-6 Unit Tests
python3 -m pytest compute/test_conversation_loop.py -v
python3 -m pytest compute/test_blocker_creates_activity.py -v
python3 -m pytest compute/test_consistency_detection.py -v
python3 -m pytest compute/test_map_evolution.py -v
python3 -m pytest compute/test_result_synthesis.py -v
python3 -m pytest compute/test_complete_emergent_workflow.py -v
```

---

## Manual UAT Scenarios

### Scenario 1: Data Analysis Goal ⭐ **Priority: High**

**User Story**: As a business analyst, I want to submit an analytical goal and receive insights.

**Steps**:
1. Open API client (Postman, curl, or UI if available)
2. Create a new session with goal: "Analyze customer retention and recommend strategies"
3. Observe process map creation
4. Monitor activity progress
5. Review synthesized results

**Expected Outcome**:
- ✅ Session created successfully
- ✅ Process map generated with 3+ activities
- ✅ Activities show clear goals and dependencies
- ✅ Status updates reflect progress
- ✅ Final results include recommendations

**API Calls**:
```bash
# Create session
curl -X POST http://localhost:8002/api/v1/sessions \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "uat-retention-001",
    "goal": "Analyze customer retention and recommend strategies",
    "user_id": "analyst-001"
  }'

# Create process map
curl -X POST http://localhost:8002/api/v1/process-maps/sessions/uat-retention-001/map \
  -H "Content-Type: application/json" \
  -d '{
    "business_goal": "Analyze customer retention and recommend strategies"
  }'

# Check progress
curl http://localhost:8002/api/v1/process-maps/sessions/uat-retention-001/map/progress
```

**Acceptance Criteria**:
- [ ] Session created in < 2 seconds
- [ ] Process map created with valid structure
- [ ] Activities have clear, actionable goals
- [ ] Progress endpoint returns meaningful data
- [ ] No errors in logs

---

### Scenario 2: Blocker Detection ⭐ **Priority: High**

**User Story**: As a data engineer, when my work is blocked, the system should automatically create resolution activities.

**Steps**:
1. Create session with goal requiring database access
2. System creates activity for data extraction
3. Activity detects blocker: "Need database credentials"
4. System automatically creates "Obtain credentials" activity
5. Verify original activity depends on blocker resolution

**Expected Outcome**:
- ✅ Blocker detected during facilitation
- ✅ Resolution activity created automatically
- ✅ Dependency updated (original depends on resolution)
- ✅ Process map version incremented
- ✅ Map evolution tracked

**Test Goal**: "Extract sales data from production database"

**Acceptance Criteria**:
- [ ] Blocker detection occurs automatically
- [ ] New activity created without manual intervention
- [ ] Dependencies correctly established
- [ ] Map version increments (v1 → v2)
- [ ] Evolution history captured with reasoning

---

### Scenario 3: Contradiction Resolution ⭐ **Priority: High**

**User Story**: As an analyst, when results contradict, the system should reconcile them.

**Steps**:
1. Create session with goal: "Calculate customer retention rate"
2. System creates multiple analysis activities
3. Activities produce contradictory outputs (65% vs 70%)
4. System detects contradiction
5. Reconciliation activity created automatically
6. Final consensus reached

**Expected Outcome**:
- ✅ Multiple activities complete with outputs
- ✅ Contradiction detected automatically
- ✅ Reconciliation activity created
- ✅ Consensus output produced
- ✅ Both original activities marked for revisit

**Acceptance Criteria**:
- [ ] Consistency check runs automatically
- [ ] Contradictions identified correctly
- [ ] Reconciliation activity has proper dependencies
- [ ] Final output resolves contradiction
- [ ] All steps recorded in map history

---

### Scenario 4: Complex Multi-Agent Goal ⭐ **Priority: Medium**

**User Story**: As an ML engineer, I want the system to coordinate multiple specialists for complex goals.

**Steps**:
1. Submit goal: "Build and deploy customer churn prediction model"
2. System creates multi-stage pipeline
3. Activities assigned to appropriate agents
4. Dependencies form logical execution graph
5. Progress tracked through all stages

**Expected Outcome**:
- ✅ 5+ activities created
- ✅ Clear dependency chain established
- ✅ Each activity has specific, achievable goal
- ✅ Different agent types involved
- ✅ Pipeline can execute in correct order

**Acceptance Criteria**:
- [ ] Complex goal decomposed into logical steps
- [ ] Dependencies prevent out-of-order execution
- [ ] Agent capabilities matched to activity needs
- [ ] Progress tracking shows pipeline flow
- [ ] All activities eventually completable

---

### Scenario 5: Error Recovery ⭐ **Priority: Medium**

**User Story**: As any user, I expect the system to handle errors gracefully.

**Steps**:
1. Submit invalid requests (missing fields, bad IDs)
2. Verify proper error messages returned
3. Confirm session/map not corrupted
4. Successfully complete valid request after errors
5. Check system remained stable

**Expected Outcome**:
- ✅ Invalid requests return 4xx errors
- ✅ Error messages are clear and helpful
- ✅ System state not corrupted
- ✅ Subsequent valid requests succeed
- ✅ No service crashes or restarts

**Acceptance Criteria**:
- [ ] 404 for non-existent resources
- [ ] 422 for validation errors
- [ ] Error messages include helpful details
- [ ] Services remain healthy after errors
- [ ] Valid requests succeed after errors

---

### Scenario 6: Complete User Journey ⭐ **Priority: High**

**User Story**: As a business executive, I want to submit a goal and receive actionable results.

**Steps**:
1. Login/authenticate (if required)
2. Submit business goal
3. View generated process map
4. Monitor real-time progress
5. Review intermediate results
6. Receive final deliverable
7. Assess goal achievement

**Expected Outcome**:
- ✅ Smooth end-to-end experience
- ✅ Clear visibility into process
- ✅ Real-time updates on progress
- ✅ Useful intermediate outputs
- ✅ Final deliverable meets goal

**Sample Goal**: "Identify top 3 revenue opportunities for Q4"

**Acceptance Criteria**:
- [ ] Goal submission is intuitive
- [ ] Process map is understandable
- [ ] Progress updates are meaningful
- [ ] Results are actionable
- [ ] Total time to completion is reasonable

---

## Test Data

### Sample Business Goals

**Simple Goals** (good for initial testing):
- "Calculate average order value for last quarter"
- "List top 10 customers by revenue"
- "Summarize customer feedback from surveys"

**Medium Complexity Goals**:
- "Analyze customer retention and recommend strategies"
- "Identify factors contributing to churn"
- "Compare Q3 vs Q4 sales performance"

**Complex Goals** (test multi-agent coordination):
- "Build and deploy customer churn prediction model"
- "Design and implement A/B test for pricing strategy"
- "Create comprehensive market analysis and expansion plan"

---

## Success Criteria

### System-Level Acceptance
- [ ] All automated tests pass (40+ tests)
- [ ] No critical bugs or crashes
- [ ] Performance meets expectations (< 5s response times)
- [ ] All services remain stable during testing
- [ ] Error handling is robust

### Feature-Level Acceptance
- [ ] **Emergent Workflows**: Goals create dynamic process maps
- [ ] **Conversation Loops**: Multi-turn agent interactions work
- [ ] **Blocker Handling**: Automatic resolution activity creation
- [ ] **Consistency Checking**: Contradictions detected and reconciled
- [ ] **Map Evolution**: Version tracking and history maintained
- [ ] **Result Synthesis**: Outputs aggregated into deliverables
- [ ] **Goal Assessment**: System knows when work is complete

### User Experience Acceptance
- [ ] System is intuitive for non-technical users
- [ ] Error messages are clear and actionable
- [ ] Progress visibility is adequate
- [ ] Results meet business needs
- [ ] Documentation is sufficient

---

## Known Limitations

### Current Implementation
- **No UI**: API-only interaction (UI in development)
- **Mock LLM**: Using mock responses for testing (real LLM integration optional)
- **Single Compute Instance**: Multi-instance load balancing not fully tested
- **Manual Facilitation**: Some workflows require manual triggering

### Out of Scope for UAT
- Production deployment and scaling
- Advanced security and authentication
- Multi-tenant isolation
- Performance optimization for large datasets
- Real-time WebSocket UI updates (partial implementation)

---

## Issue Reporting

### Bug Report Template
```markdown
**Issue Title**: [Brief description]

**Severity**: Critical / High / Medium / Low

**Scenario**: [Which UAT scenario]

**Steps to Reproduce**:
1. Step 1
2. Step 2
3. Step 3

**Expected Behavior**:
[What should happen]

**Actual Behavior**:
[What actually happened]

**Logs/Screenshots**:
[Attach relevant information]

**Environment**:
- Services running: [Marketplace/Serving/Compute]
- Test type: [Automated/Manual]
- Session ID: [If applicable]
```

### Where to Report
- Create GitHub issue in repository
- Tag with `uat` and appropriate severity
- Include session IDs and timestamps
- Attach logs from `compute/logs/`, `serving/logs/`, `marketplace/logs/`

---

## Test Results Documentation

### Test Execution Log
After each test run, document:

| Date | Tester | Scenario | Result | Notes |
|------|--------|----------|--------|-------|
| YYYY-MM-DD | Name | Scenario # | Pass/Fail | Any observations |

### Final UAT Sign-Off

**UAT Completed By**: ___________________  
**Date**: ___________________  
**Overall Result**: Pass / Fail / Pass with Reservations

**Comments**:
```
[Tester feedback and observations]
```

**Recommendation**:
- [ ] Approve for production
- [ ] Approve with minor fixes
- [ ] Requires major revisions
- [ ] Not ready for production

---

## Next Steps After UAT

### If Tests Pass
1. Document any minor issues found
2. Plan production deployment
3. Prepare user training materials
4. Set up monitoring and alerts
5. Schedule production cutover

### If Tests Fail
1. Prioritize critical issues
2. Implement fixes
3. Re-test affected scenarios
4. Update documentation
5. Schedule UAT re-run

---

## Support Contacts

**Technical Issues**:
- Check logs: `./status.sh`
- Review documentation: `docs/`
- GitHub issues for bug reports

**Test Questions**:
- Review this document
- Check API documentation
- Refer to Week 6 implementation summary

---

## Appendix: Quick Reference

### Essential Commands
```bash
# Start everything
./start_all.sh

# Run all tests
./run_all_tests.sh

# Check status
./status.sh

# Stop everything
./stop_all.sh

# View logs
tail -f compute/logs/compute.log
tail -f serving/logs/serving.log
tail -f marketplace/logs/marketplace.log
```

### API Endpoints Quick Reference
```bash
# Health checks
curl http://localhost:8001/health
curl http://localhost:8002/api/v1/health
curl http://localhost:8003/api/v1/health

# Create session
curl -X POST http://localhost:8002/api/v1/sessions -H "Content-Type: application/json" \
  -d '{"session_id":"test-001","goal":"Test goal"}'

# Get session
curl http://localhost:8002/api/v1/sessions/test-001

# Create process map
curl -X POST http://localhost:8002/api/v1/process-maps/sessions/test-001/map \
  -H "Content-Type: application/json" -d '{"business_goal":"Test"}'

# Get process map
curl http://localhost:8002/api/v1/process-maps/sessions/test-001/map

# List agents
curl http://localhost:8003/api/v1/agents
curl http://localhost:8001/api/v1/agents
```

---

**Document Version History**:
- v1.0 (2024-12-11): Initial UAT plan created
