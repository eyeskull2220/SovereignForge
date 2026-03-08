# SovereignForge Agent Operating Rules

## 🤖 Agent Workflow Standards

### **Session Start Protocol**
1. **Read WORKING.md** (2 seconds) - Current priorities, shipped features, broken items
2. **Run warm_start.py** (1.4 seconds) - Project state injection
3. **Check git status** - Branch, uncommitted changes, upstream sync
4. **Verify test command** - Ensure tests pass before changes

### **Context Preservation**
- **Update WORKING.md** after every major change
- **Document decisions** in session notes
- **Track blockers** and resolutions
- **Maintain guardrails** - never violate MiCA compliance

### **Code Quality Standards**
- **Async everywhere** - All I/O operations async
- **Type hints** - Full annotation coverage
- **Error handling** - Comprehensive try/catch with logging
- **Security first** - Non-root containers, secrets management
- **Performance** - GPU optimization, memory bounds

## 🚨 MiCA Compliance Guardrails (NEVER VIOLATE)

### **Strict Pair Enforcement**
**ALLOWED PAIRS ONLY:**
- XRP/USDC, XLM/USDC, HBAR/USDC, ALGO/USDC, ADA/USDC
- LINK/USDC, IOTA/USDC, XDC/USDC, ONDO/USDC, VET/USDC
- XRP/RLUSD, XLM/RLUSD, ADA/RLUSD

**FORBIDDEN PAIRS:**
- ❌ BTC/USDT, ETH/USDT, DOGE/USDT (not MiCA compliant)
- ❌ Any USDT pairs in personal deployment
- ❌ BTC/ETH in personal deployment (institutional only)

### **Personal Deployment Rules**
- **Local-only execution** - No external APIs, no custody
- **No public offering** - Individual use only
- **MiCA compliant assets** - Only listed pairs above
- **Data isolation** - Personal data stays local

### **Compliance Verification**
- **Scan all code** for USDT references before commit
- **Update configs** to use USDC/RLUSD only
- **Test compliance** with whitelist enforcement
- **Document violations** in WORKING.md

## 🔧 Development Workflow

### **Pre-Commit Checklist**
- [ ] Tests pass (`python -m pytest tests/ -v`)
- [ ] MiCA compliance verified (no USDT pairs)
- [ ] WORKING.md updated with changes
- [ ] Type hints complete
- [ ] Error handling comprehensive
- [ ] Security review passed

### **Commit Standards**
- **Small commits** - Single feature/fix per commit
- **Clear messages** - "feat:", "fix:", "perf:", "docs:"
- **Test included** - All changes tested
- **Documentation updated** - WORKING.md reflects changes

### **Session Management**
- **Warm start** every session - Use warm_start.py
- **Context injection** - Project state in first message
- **Progress tracking** - Update WORKING.md regularly
- **Blocker documentation** - Track and resolve issues

## 📊 Quality Metrics

### **Code Standards**
- **Test Coverage**: >70% (currently 74%)
- **Pylance Errors**: <50 (currently ~50)
- **Performance**: GPU optimized, memory bounded
- **Security**: Phase 5 personal security implemented

### **Architecture Standards**
- **Async/Await**: All I/O operations async
- **Type Safety**: Full type annotation
- **Error Recovery**: Circuit breakers, fallbacks
- **Scalability**: Horizontal scaling support

## 🚫 Forbidden Actions

### **MiCA Violations**
- Adding USDT pairs to any deployment
- Including BTC/ETH in personal deployment
- External API dependencies in personal mode
- Custody or trading execution features

### **Technical Violations**
- Synchronous I/O operations
- Missing type hints
- Inadequate error handling
- Security bypasses

### **Workflow Violations**
- Committing without tests
- Large commits with multiple features
- Not updating WORKING.md
- Violating guardrails

## 🎯 Agent Responsibilities

### **Primary Duties**
1. **MiCA Compliance** - Enforce whitelist strictly
2. **Code Quality** - Maintain standards and performance
3. **Context Management** - Preserve project state
4. **Testing** - Ensure reliability and coverage

### **Secondary Duties**
1. **Documentation** - Keep WORKING.md current
2. **Performance** - Optimize for production
3. **Security** - Implement Phase 5 measures
4. **Reliability** - Error handling and recovery

## 📝 Session Template

### **Start Session**
1. Read WORKING.md
2. Run warm_start.py
3. Check git status
4. Verify tests pass

### **During Session**
1. Update WORKING.md after changes
2. Test before commit
3. Document decisions
4. Track blockers

### **End Session**
1. Update WORKING.md with progress
2. Document blockers for next session
3. Ensure tests pass
4. Commit with clear message

## 🔄 Context Optimization

### **Warm Start Components**
- **Git State**: Branch, commits, uncommitted changes
- **Stack Detection**: Python, PyTorch, CUDA versions
- **Key Commands**: Test, build, dev commands
- **Project Structure**: Load-bearing config files
- **Recent Changes**: Last commits, open issues

### **Session Hooks**
- **Pre-session**: Context injection
- **Post-compaction**: State refresh
- **Error recovery**: Context restoration
- **Progress sync**: WORKING.md updates

## 📈 Success Metrics

### **Session Quality**
- **Context Preservation**: No degradation over long sessions
- **Compliance Adherence**: Zero MiCA violations
- **Test Coverage**: All changes tested
- **Documentation**: WORKING.md always current

### **Code Quality**
- **Performance**: GPU utilization >80%
- **Reliability**: <5% test failures
- **Security**: Phase 5 measures active
- **Maintainability**: Clear architecture, documentation