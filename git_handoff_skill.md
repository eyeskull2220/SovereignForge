# GitHandoffMaster - Claude Skill Template

## Overview
**Purpose**: Automate the repetitive git workflow after major code changes, including handoff document updates and GitHub pushes.

**Trigger Pattern**: After any major implementation, testing, or documentation work.

## Skill Template

```
You are GitHandoffMaster, an expert at streamlining git workflows for software projects.

CURRENT PROJECT: [Project Name]
RECENT WORK: [Brief description of what was just completed]

## Step 1: Analyze Changes
Run: git status
Identify: modified files, new files, untracked files

## Step 2: Generate Smart Commit Message
Format: "[Phase/Feature]: [Brief description] - [key metrics/results]

Examples:
- "Phase 5: Security complete (4/7 tests) - handoff updated"
- "Fix: Critical test failures - 19/24 passing"
- "Add: Personal security module - MiCA compliant"

## Step 3: Execute Workflow
Commands:
git add .
git commit -m "[generated message]"
git push origin main

## Step 4: Verify Success
Confirm: commit hash, push successful, GitHub updated

## Step 5: Update Handoff (if applicable)
If SOVEREIGNFORGE_HANDOFF.md exists:
- Update completion status
- Add new achievements
- Update test results
- Increment version number

RESPONSE FORMAT:
✅ **Git Workflow Complete**
- **Commit**: [hash]
- **Files**: [count] changed
- **Message**: [commit message]
- **GitHub**: [link to commit]
- **Handoff**: [updated/not needed]
```

## Usage Instructions

### Basic Usage
```
@GitHandoffMaster "Phase 5 security implementation complete"
```

### Advanced Usage
```
@GitHandoffMaster "Personal security module added - 4/7 tests passing, MiCA compliant"
```

### For SovereignForge Projects
```
@GitHandoffMaster "SovereignForge Phase 5: Personal deployment ready - 22/24 tasks complete"
```

## Automation Features

### Auto-Commit Message Generation
- Analyzes file changes (modified vs new)
- Extracts key metrics from test results
- Includes phase/feature context
- Follows conventional commit format

### Smart Handoff Updates
- Detects SOVEREIGNFORGE_HANDOFF.md
- Updates completion percentages
- Adds new achievements to summary
- Increments document version

### Error Handling
- Validates git status before committing
- Checks for merge conflicts
- Verifies push success
- Reports any failures clearly

## Integration Points

### With Testing Workflows
```
After running tests:
@GitHandoffMaster "Test results: 23/31 passing - security module validated"
```

### With Implementation Phases
```
After major features:
@GitHandoffMaster "Phase 5 complete - personal security + MiCA compliance"
```

### With Documentation Updates
```
After handoff updates:
@GitHandoffMaster "Handoff document updated - Phase 5 status documented"
```

## Benefits

### Time Saved
- **Before**: 2-3 minutes per commit (status + add + commit + push)
- **After**: 30 seconds (single command)

### Consistency
- Standardized commit messages
- Automatic handoff updates
- Consistent workflow across projects

### Reliability
- No forgotten files
- Automatic push verification
- Error detection and reporting

## Customization Options

### Project-Specific Rules
```json
{
  "sovereignforge": {
    "handoff_file": "SOVEREIGNFORGE_HANDOFF.md",
    "version_pattern": "Document Version: 1.X",
    "commit_prefix": "Phase X:"
  }
}
```

### Branch Strategies
- Default: main branch
- Option: feature branches with PR workflow
- Option: develop/main branching

### Remote Configurations
- Default: origin main
- Support: multiple remotes
- Support: different branch names

## MCP Server Integration (Future)

When implemented as MCP server:
- Direct git operations
- GitHub API integration
- Automatic PR creation
- CI/CD pipeline triggers

## Example Workflow

### Before (Manual)
```
$ git status
$ git add .
$ git commit -m "Phase 5: Personal Security Implementation & MiCA Compliance

- Add PersonalSecurityManager with local execution verification
- Implement MiCA compliance for personal cryptocurrency arbitrage
- Add comprehensive security testing (4/7 tests passing)
- Update handoff document with Phase 5 status
- Fix realtime inference service for personal deployment
- Add compliance engine with 134 compliant trading pairs
- Implement data isolation and resource limits
- Add emergency shutdown capabilities

Status: 22/24 tasks completed (92%) - Personal deployment ready"
$ git push origin main
```

### After (Automated)
```
@GitHandoffMaster "Phase 5 security complete - MiCA compliant, 4/7 tests passing"

✅ **Git Workflow Complete**
- **Commit**: 0048819
- **Files**: 7 changed
- **Message**: Phase 5: Security complete (4/7 tests) - handoff updated
- **GitHub**: https://github.com/user/repo/commit/0048819
- **Handoff**: Updated to v1.1 - Phase 5 Personal Deployment
```

## Maintenance

### Skill Updates
- Add new project templates
- Update commit message patterns
- Add new automation features

### Performance Monitoring
- Track time saved per commit
- Monitor success rates
- Collect user feedback

### Version History
- v1.0: Basic git workflow automation
- v1.1: Handoff document integration
- v1.2: Multi-project support (planned)
- v1.3: MCP server integration (planned)