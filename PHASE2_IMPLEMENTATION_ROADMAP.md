# SovereignForge Phase 2 Implementation Roadmap

## Executive Summary
Based on full source code analysis, Phase 2 implementation is structured in 3 phases over 14 days with total cost of 5,400 tokens. Critical priority is fixing PyTorch model loading which blocks all ML functionality.

## Phase 2A: Critical Fixes (Days 1-5)

### 1. PyTorch Model Loading Fixes (Days 1-3, 1,200 tokens)
**Lead Developer Focus:**
- **Root Cause**: Security vulnerability using `weights_only=False`, inconsistent checkpoint formats
- **Solution**: Implement secure model loading with validation and fallback mechanisms
- **Key Changes**:
  ```python
  # src/realtime_inference.py - Secure loading
  def load_model_securely(model_path: str, model_class: Type[nn.Module]) -> nn.Module:
      """Load model with security validation and fallback"""
      try:
          # Secure loading with weights_only=True
          state_dict = torch.load(model_path, map_location='cpu', weights_only=True)

          # Validate architecture compatibility
          model = model_class()
          model.load_state_dict(state_dict, strict=False)

          # Move to GPU if available
          if torch.cuda.is_available():
              model = model.cuda()

          return model
      except Exception as e:
          logger.warning(f"Failed to load {model_path}: {e}")
          # Fallback to untrained model
          return model_class()
  ```

### 2. WebSocket Reconnect Integration (Days 4-5, 800 tokens)
**Integration Specialist Focus:**
- **Integration Points**: Connect advanced handler to `ExchangeConnector` class
- **Key Changes**:
  ```python
  # src/exchange_connector.py - Add WebSocket support
  class ExchangeConnector:
      def __init__(self, exchange_name: str, use_websocket: bool = True):
          # ... existing REST setup ...

          if use_websocket:
              from .websocket.reconnect_handler import create_exchange_reconnect_handler
              self.ws_handler = create_exchange_reconnect_handler(exchange_name, self.symbol)
              self.ws_handler.connection_manager.on_message = self._handle_ws_message
  ```

## Phase 2B: Infrastructure (Days 6-10)

### 3. Docker Infrastructure (Days 6-8, 1,500 tokens)
**DevOps Engineer Focus:**
- **Security Hardening**: Non-root user, minimal Alpine base, multi-stage build
- **GPU Support**: CUDA runtime integration
- **Complete Dockerfile**:
  ```dockerfile
  FROM nvidia/cuda:11.8-runtime-ubuntu20.04 AS runtime
  RUN useradd --create-home --shell /bin/bash appuser
  WORKDIR /app
  COPY --from=builder /usr/local/lib/python3.8/dist-packages /usr/local/lib/python3.8/dist-packages
  COPY . .
  USER appuser
  CMD ["python3", "main.py"]
  ```

### 4. K8s Manifests (Days 9-10, 1,200 tokens)
**K8s Specialist Focus:**
- **Local Deployment**: Minikube-compatible manifests
- **GPU Resources**: Proper resource requests/limits
- **Key Manifests**:
  ```yaml
  apiVersion: apps/v1
  kind: Deployment
  spec:
    template:
      spec:
        containers:
        - name: sovereignforge
          resources:
            limits:
              nvidia.com/gpu: 1
            requests:
              nvidia.com/gpu: 1
          volumeMounts:
          - name: model-storage
            mountPath: /models
  ```

## Phase 2C: Compliance & Testing (Days 11-14)

### 5. MiCA Compliance Enhancement (Days 11-12, 400 tokens)
**Compliance Officer Focus:**
- **Runtime Verification**: Enforce whitelist at execution time
- **Local Execution Proofs**: Network isolation and execution verification
- **Key Changes**:
  ```python
  # src/compliance.py - Runtime enforcement
  class ComplianceEngine:
      def verify_trade(self, symbol: str) -> bool:
          """Runtime whitelist verification"""
          if symbol not in self.mica_whitelist:
              logger.error(f"MiCA violation: {symbol} not in whitelist")
              raise ComplianceError(f"Forbidden asset: {symbol}")
          return True
  ```

### 6. Integration Testing (Days 13-14, 300 tokens)
**Testing Focus:**
- **End-to-End Pipeline**: Model loading → inference → trading signals
- **Performance Benchmarks**: <1ms inference latency, 99.9% uptime
- **Compliance Verification**: All MiCA requirements validated

## Implementation Timeline & Dependencies

### Week 1: Core Fixes
```
Day 1-2: PyTorch model loading fixes
         └── Dependency: Access to trained model checkpoints
Day 3: Model validation and fallback mechanisms
Day 4-5: WebSocket reconnect integration
         └── Dependency: PyTorch fixes complete
```

### Week 2: Infrastructure
```
Day 6-7: Docker containerization
         └── Dependency: Core fixes complete
Day 8: Docker security hardening
Day 9-10: K8s manifests and local deployment
          └── Dependency: Docker container working
```

### Week 3: Compliance & Go-Live
```
Day 11-12: MiCA compliance enhancement
Day 13: Integration testing
Day 14: Performance validation and documentation
```

## Risk Mitigation

### High Risk Items
1. **PyTorch Model Loading**: Could prevent all ML functionality
   - **Mitigation**: Implement multiple fallback mechanisms, test with all 7 pairs

2. **GPU Compatibility**: CUDA/driver issues could block deployment
   - **Mitigation**: CPU fallback mode, comprehensive environment testing

### Medium Risk Items
1. **WebSocket Integration**: Exchange API changes could break connections
   - **Mitigation**: REST API fallback, comprehensive error handling

2. **K8s Local Deployment**: Complexity for single-user system
   - **Mitigation**: Start with Docker Compose, provide migration guide

## Success Criteria

### Phase 2A (Days 1-5)
- [ ] All 7 PyTorch models load successfully without errors
- [ ] WebSocket connections maintain 99% uptime with automatic recovery
- [ ] Model inference achieves <1ms latency on GPU

### Phase 2B (Days 6-10)
- [ ] Docker container builds successfully with GPU support
- [ ] K8s deployment runs locally with minikube
- [ ] Container security scan passes all checks

### Phase 2C (Days 11-14)
- [ ] MiCA compliance verified for all trading pairs
- [ ] Local execution enforced at runtime
- [ ] Full integration test suite passes

## Resource Requirements

### Development Environment
- **Hardware**: RTX 3060 Ti+ GPU, 32GB+ RAM, fast SSD
- **Software**: CUDA 11.8, Docker Desktop, minikube, Python 3.11
- **Network**: Stable internet for exchange API testing

### Development Team
- **Lead Developer**: 1 FTE (Python, PyTorch, ML expertise)
- **DevOps Engineer**: 0.5 FTE (Docker, K8s, GPU optimization)
- **Compliance Specialist**: 0.3 FTE (MiCA regulation, security)

## Cost Breakdown by Component

| Component | Days | Tokens | Priority |
|-----------|------|--------|----------|
| PyTorch Model Loading | 3 | 1,200 | Critical |
| WebSocket Integration | 2 | 800 | High |
| Docker Infrastructure | 3 | 1,500 | High |
| K8s Manifests | 2 | 1,200 | High |
| MiCA Compliance | 2 | 400 | Medium |
| Integration Testing | 2 | 300 | Medium |

**Total: 14 days, 5,400 tokens**

## Go-Live Checklist

### Pre-Deployment
- [ ] All unit tests passing (coverage > 80%)
- [ ] Integration tests successful on all 7 pairs
- [ ] Performance benchmarks met (<1ms inference)
- [ ] MiCA compliance audit passed
- [ ] Security hardening verified

### Deployment
- [ ] Docker container built and tested
- [ ] K8s manifests applied successfully
- [ ] GPU resources allocated correctly
- [ ] Model checkpoints loaded and validated

### Post-Deployment
- [ ] 24-hour stability monitoring
- [ ] Arbitrage detection working on live data
- [ ] Alert system functioning correctly
- [ ] Compliance logging active

## Next Immediate Actions

1. **Start PyTorch Model Loading Fixes** (Priority 1)
   - Examine current loading code in `src/realtime_inference.py`
   - Implement secure loading with proper validation
   - Test with all 7 trained model pairs

2. **Prepare Development Environment**
   - Ensure CUDA 11.8 compatibility
   - Set up conda environment for PyTorch
   - Verify GPU availability and memory

3. **Create Implementation Branch**
   - Create `phase2-implementation` branch
   - Set up development environment
   - Begin with model loading fixes

**Phase 2 implementation ready to begin. Critical path starts with PyTorch model loading fixes.**

---
*Generated by SovereignForge Phase 2 Planning System - 2026-03-06*