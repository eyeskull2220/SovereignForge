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

## 🎯 Personal Use Optimizations (Phase 11)

### **Performance & Resource Optimization**
- **Memory Footprint Reduction**: Target <2GB RAM usage during normal operation
- **CPU Optimization**: Single-threaded mode for personal computers (12 cores → 1-2 cores)
- **Storage Efficiency**: Compressed data storage, automatic cleanup of old logs/data
- **Background Processing**: Non-critical tasks run asynchronously to reduce system load

### **Simplified Operation**
- **One-Click Start/Stop**: `./sovereignforge start/stop` commands
- **Status Dashboard**: Simple `./sovereignforge status` with key metrics
- **Auto-Recovery**: Automatic restart on failures with email notifications
- **Configuration Wizard**: Interactive setup for risk preferences and API keys

### **Enhanced Monitoring for Personal Use**
- **Essential Metrics Only**: P&L, active positions, daily performance, drawdown
- **Real-time Alerts**: Telegram notifications for trades, errors, and risk events
- **Health Dashboard**: Simple web interface showing system status
- **Performance History**: Daily P&L tracking with basic analytics

### **Data Management Improvements**
- **Automatic Backups**: Daily encrypted backups to local storage
- **Data Compression**: Reduce storage requirements by 60%
- **Log Rotation**: Automatic cleanup to prevent disk space issues
- **Export Functionality**: Easy data export for tax reporting

### **Error Handling & Troubleshooting**
- **User-Friendly Errors**: Clear error messages with suggested solutions
- **Auto-Diagnostics**: `./sovereignforge health` command for system diagnostics
- **Recovery Procedures**: Automated rollback on deployment failures
- **Support Resources**: Built-in troubleshooting guides and FAQs

## 🚀 Quick Start for Personal Use

### **Prerequisites**
- Python 3.8+ with pip
- 4GB RAM minimum, 8GB recommended
- 10GB free disk space
- Internet connection for market data

### **Installation**
```bash
# Clone repository
git clone https://github.com/eyeskull2220/SovereignForge.git
cd SovereignForge

# Run personal installer
./personal_deploy.sh

# Follow setup wizard
# System will be ready in ~10 minutes
```

### **Daily Operation**
```bash
# Start system
./sovereignforge start

# Check status
./sovereignforge status

# View dashboard (opens browser)
./sovereignforge dashboard

# Stop system
./sovereignforge stop
```

### **Configuration**
- **Risk Level**: Conservative (default), Moderate, Aggressive
- **Trading Pairs**: MiCA-compliant only (XRP, XLM, HBAR, ALGO, ADA, LINK, IOTA, XDC, ONDO, VET)
- **Position Size**: 0.1% to 2% of capital per trade
- **Alert Channels**: Telegram, Email, In-app notifications

## 📊 Personal Use Metrics

### **System Requirements**
- **CPU**: 2 cores minimum, 4 cores recommended
- **RAM**: 4GB minimum, 8GB recommended
- **Storage**: 10GB for system, plus data storage
- **Network**: 1Mbps minimum for market data

### **Performance Targets**
- **Startup Time**: <30 seconds
- **Memory Usage**: <2GB during normal operation
- **CPU Usage**: <20% average during trading
- **Response Time**: <100ms for dashboard interactions

### **Reliability Targets**
- **Uptime**: >99.5% during market hours
- **Data Accuracy**: 100% price feed validation
- **Error Recovery**: Automatic restart within 30 seconds
- **Backup Success**: 100% automated backup completion

## 🔧 Troubleshooting for Personal Use

### **Common Issues**
- **Port Conflicts**: Dashboard fails to start
  - Solution: Change port in config or stop conflicting service
- **Memory Issues**: System runs slow or crashes
  - Solution: Reduce position sizes or add more RAM
- **Network Issues**: Market data not updating
  - Solution: Check internet connection, restart data feeds
- **Permission Issues**: Files cannot be written
  - Solution: Run as administrator or check folder permissions

### **Support Resources**
- **Documentation**: `user_manual.md`, `troubleshooting_guide.md`
- **Logs**: Check `logs/` directory for detailed error information
- **Health Check**: Run `./sovereignforge health` for system diagnostics
- **Reset Option**: `./sovereignforge reset` for clean system restore

## 🎯 Future Personal Enhancements

### **Phase 12: Personal UX Polish**
- Mobile app companion for iOS/Android
- Voice commands for hands-free operation
- Advanced charting with technical indicators
- Portfolio rebalancing automation

### **Phase 13: Personal AI Assistant**
- Natural language queries ("How is my portfolio doing?")
- Automated strategy suggestions based on market conditions
- Risk assessment explanations in plain language
- Educational content and market insights

### **Phase 14: Personal Integration**
- Integration with personal finance tools (Mint, YNAB)
- Tax reporting automation for MiCA-compliant trades
- Multi-device synchronization
- Backup to personal cloud storage
