# SovereignForge Phase 2 Implementation Plan

## Executive Summary
Phase 2 addresses the 5 Red/Yellow priority components identified in the audit: WebSocket reconnect logic, PyTorch model loading, risk management, Docker/K8s infrastructure, and GPU training fixes. Total estimated effort: 8,500 tokens over 14 days.

## Critical Discovery: Source Code Missing
**Key Finding:** The SovereignForge source code is not present in the current workspace. Only artifacts exist:
- 11 trained ML models (`models/*.pkl`)
- Training reports (`reports/*.md`)
- Single log file (`arbitrage_detector.log`)

**Implication:** Phase 2 implementation requires either:
1. Locating the original source code repository
2. Rebuilding from scratch using the trained models as reference
3. Reverse-engineering functionality from logs and reports

## Component Priority & Implementation

### Priority 1: WebSocket Reconnect Logic (16 hours)
**Current Status:** Base WebSocket class exists but streaming loop lacks auto-reconnect
**Implementation:**
- Create `src/websocket/connection_manager.py` with exponential backoff
- Add `src/websocket/reconnect_handler.py` for health monitoring
- Modify `src/exchanges/base_exchange.py` for circuit breaker pattern
- Dependencies: `asyncio`, `websockets` library

**Testing:** Unit tests for reconnection scenarios, integration tests with mock disconnections

### Priority 2: PyTorch Model Loading (20 hours)
**Current Status:** Loading logic exists but fails for some models
**Implementation:**
- Fix model serialization in `src/models/model_manager.py`
- Add validation checks for all 7 pairs (BTC, ETH, XRP, XLM, HBAR, ALGO, ADA)
- Implement CPU fallback when GPU unavailable
- Dependencies: PyTorch CPU-only installation via conda

**Testing:** Model loading unit tests, validation integration tests

### Priority 3: GPU Training Fix (24 hours)
**Current Status:** PyTorch CPU install failed, blocking GPU training
**Implementation:**
- Create conda environment: `conda create -n sovereignforge python=3.11 pytorch torchvision torchaudio cpuonly -c pytorch`
- Modify `gpu_train.py` to use conda environment
- Add GPU memory monitoring and optimization
- Dependencies: Miniconda, CUDA drivers

**Testing:** Training pipeline integration tests, performance benchmarks

### Priority 4: Risk Management/Position Sizing (12 hours)
**Current Status:** Basic risk management exists but incomplete
**Implementation:**
- Enhance `src/risk/risk_manager.py` with stop-loss at 2% loss
- Add position sizing limits (5% of portfolio per trade)
- Implement circuit breakers for 10% daily loss limits
- Dependencies: NumPy, pandas

**Testing:** Risk calculation unit tests, position sizing integration tests

### Priority 5: Docker/K8s Infrastructure (28 hours)
**Current Status:** No containerization or orchestration exists
**Implementation:**
- Create `Dockerfile` with Alpine base, non-root user, GPU support
- Create `docker-compose.yml` for local development
- Create `k8s/` manifests for minikube deployment
- Add volume mounts for models/data persistence
- Dependencies: Docker Desktop, minikube, kubectl

**Testing:** Container build tests, deployment integration tests

## File Creation/Modification Matrix

| Component | Files to Create | Files to Modify | Dependencies to Add |
|-----------|-----------------|-----------------|-------------------|
| WebSocket Reconnect | `src/websocket/connection_manager.py`, `src/websocket/reconnect_handler.py` | `src/exchanges/base_exchange.py`, `src/config/websocket_config.py` | `websockets`, `asyncio` |
| PyTorch Model Loading | `src/models/model_validator.py` | `src/models/model_manager.py`, `src/inference/real_time_inference.py` | PyTorch (conda) |
| GPU Training | `scripts/setup_conda.sh` | `gpu_train.py`, `requirements-gpu.txt` | Miniconda, CUDA |
| Risk Management | `src/risk/stop_loss.py`, `src/risk/circuit_breaker.py` | `src/risk/risk_manager.py` | NumPy |
| Docker/K8s | `Dockerfile`, `docker-compose.yml`, `k8s/deployment.yaml`, `k8s/configmap.yaml` | N/A | Docker, Kubernetes |

## Implementation Sequence

### Week 1: Core Infrastructure (Days 1-5)
1. **Day 1:** Set up conda environment and PyTorch GPU support
2. **Day 2:** Implement WebSocket reconnect logic
3. **Day 3:** Fix PyTorch model loading for all 7 pairs
4. **Day 4:** Enhance risk management with stop-loss/circuit breakers
5. **Day 5:** Integration testing of core components

### Week 2: Containerization & Deployment (Days 6-10)
6. **Day 6:** Create hardened Dockerfile with security best practices
7. **Day 7:** Implement docker-compose for local development
8. **Day 8:** Create K8s manifests for production deployment
9. **Day 9:** Add health checks and monitoring
10. **Day 10:** Test containerized deployment

### Week 3: Testing & Optimization (Days 11-14)
11. **Day 11:** Implement comprehensive test suite
12. **Day 12:** Performance benchmarking and optimization
13. **Day 13:** End-to-end pipeline testing
14. **Day 14:** Documentation and go-live preparation

## Integration Testing Plan

### Unit Test Coverage (80% target)
- WebSocket reconnection logic
- Model loading validation
- Risk calculation accuracy
- Position sizing algorithms

### Integration Tests
- End-to-end arbitrage detection pipeline
- Real-time data streaming with reconnection
- GPU training workflow
- Alert system functionality

### Performance Benchmarks
- Model inference latency (< 100ms)
- Training time per pair (< 30 minutes)
- Memory usage (< 8GB GPU, < 4GB CPU)
- WebSocket reconnection time (< 5 seconds)

### Failure Scenario Tests
- Network disconnection recovery
- GPU memory exhaustion handling
- Exchange API rate limit management
- Model loading corruption recovery

## Deployment Checklist

### Pre-Deployment
- [ ] All unit tests passing (coverage > 80%)
- [ ] Integration tests successful
- [ ] Performance benchmarks met
- [ ] Security audit completed
- [ ] MiCA compliance verified
- [ ] Documentation updated

### Deployment
- [ ] Backup existing models/data
- [ ] Deploy containers to staging
- [ ] Run smoke tests (1 hour)
- [ ] Verify GPU resource allocation
- [ ] Check monitoring dashboards
- [ ] Validate network isolation

### Post-Deployment
- [ ] 24-hour stability monitoring
- [ ] Performance validation
- [ ] Alert system testing
- [ ] User acceptance testing
- [ ] Production handover

## Risk Mitigation Summary

### High-Risk Items
1. **Source Code Location:** Risk of losing original implementation
   - **Mitigation:** Search all drives, check backups, consider reconstruction from models/logs

2. **PyTorch GPU Compatibility:** Complex CUDA/driver dependencies
   - **Mitigation:** Test on multiple environments, provide CPU fallback, document setup procedures

3. **Exchange API Changes:** External dependency changes
   - **Mitigation:** Implement adapter pattern, comprehensive error handling, fallback strategies

### Medium-Risk Items
1. **K8s Local Deployment:** Complexity for single-user system
   - **Mitigation:** Start with Docker Compose, provide migration path to K8s

2. **Performance Regression:** New components may impact speed
   - **Mitigation:** Continuous benchmarking, performance budgets, optimization sprints

## Total Timeline: 14 days
## Total Token Estimate: 8,500 tokens

## Next Action Required
**URGENT:** Locate or reconstruct the SovereignForge source code to begin implementation. Without the source code, Phase 2 cannot proceed.

## Contact Information
For questions about this Phase 2 plan, refer to the audit findings in `PHASE2_AUDIT_REPORT.md`.

---
*Generated by SovereignForge Phase 2 Planning System - 2026-03-06*