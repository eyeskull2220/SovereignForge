"""
SovereignForge v1 - Bug Reporting and Fix System
CEO-led bug reporting workflow with agent validation and implementation
"""

import logging
from typing import Dict, List, Optional
from datetime import datetime
from enum import Enum
from pydantic import BaseModel
from database import get_database

logging.basicConfig(level=logging.INFO)

class BugSeverity(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

class BugStatus(Enum):
    REPORTED = "reported"
    UNDER_REVIEW = "under_review"
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    VALIDATED = "validated"
    IMPLEMENTED = "implemented"
    RESOLVED = "resolved"
    CLOSED = "closed"

class BugReport(BaseModel):
    """Bug report data model"""
    id: Optional[int] = None
    title: str
    description: str
    severity: BugSeverity
    component: str
    reporter: str
    status: BugStatus = BugStatus.REPORTED
    assigned_agent: Optional[str] = None
    ceo_review: Optional[str] = None
    validation_notes: Optional[str] = None
    fix_description: Optional[str] = None
    created_at: datetime = datetime.utcnow()
    updated_at: datetime = datetime.utcnow()

class BugReportingSystem:
    """CEO-led bug reporting and fixing system"""

    def __init__(self):
        self.db = get_database()
        logging.info("Bug reporting system initialized")

    def report_bug(self, title: str, description: str, severity: BugSeverity,
                  component: str, reporter: str) -> int:
        """Report a new bug - sends to CEO for review"""
        bug = BugReport(
            title=title,
            description=description,
            severity=severity,
            component=component,
            reporter=reporter
        )

        # Store in database
        bug_id = self._store_bug_report(bug)

        # Notify CEO
        self._notify_ceo_bug_reported(bug_id, bug)

        logging.info(f"Bug reported: {bug_id} - {title}")
        return bug_id

    def ceo_review_bug(self, bug_id: int, review_notes: str, assign_to_agent: str) -> bool:
        """CEO reviews bug and assigns to agent"""
        bug = self._get_bug_report(bug_id)
        if not bug:
            logging.error(f"Bug {bug_id} not found")
            return False

        bug.ceo_review = review_notes
        bug.assigned_agent = assign_to_agent
        bug.status = BugStatus.ASSIGNED
        bug.updated_at = datetime.utcnow()

        self._update_bug_report(bug)

        # Notify assigned agent
        self._notify_agent_bug_assigned(bug_id, bug)

        logging.info(f"CEO assigned bug {bug_id} to {assign_to_agent}")
        return True

    def agent_submit_fix(self, bug_id: int, agent_name: str, fix_description: str) -> bool:
        """Agent submits proposed fix for validation"""
        bug = self._get_bug_report(bug_id)
        if not bug or bug.assigned_agent != agent_name:
            logging.error(f"Bug {bug_id} not assigned to {agent_name}")
            return False

        bug.fix_description = fix_description
        bug.status = BugStatus.VALIDATED  # Ready for validation
        bug.updated_at = datetime.utcnow()

        self._update_bug_report(bug)

        # Notify CEO for validation
        self._notify_ceo_fix_ready(bug_id, bug)

        logging.info(f"Agent {agent_name} submitted fix for bug {bug_id}")
        return True

    def ceo_validate_fix(self, bug_id: int, validation_notes: str, approved: bool) -> bool:
        """CEO validates the proposed fix"""
        bug = self._get_bug_report(bug_id)
        if not bug:
            logging.error(f"Bug {bug_id} not found")
            return False

        bug.validation_notes = validation_notes
        bug.updated_at = datetime.utcnow()

        if approved:
            bug.status = BugStatus.IMPLEMENTED
            # Notify agent to implement
            self._notify_agent_implement_fix(bug_id, bug)
        else:
            bug.status = BugStatus.ASSIGNED  # Send back for revision
            self._notify_agent_fix_rejected(bug_id, bug)

        self._update_bug_report(bug)

        logging.info(f"CEO {'approved' if approved else 'rejected'} fix for bug {bug_id}")
        return True

    def agent_implement_fix(self, bug_id: int, agent_name: str) -> bool:
        """Agent confirms fix implementation"""
        bug = self._get_bug_report(bug_id)
        if not bug or bug.assigned_agent != agent_name:
            logging.error(f"Bug {bug_id} not assigned to {agent_name}")
            return False

        bug.status = BugStatus.RESOLVED
        bug.updated_at = datetime.utcnow()

        self._update_bug_report(bug)

        # Notify CEO of completion
        self._notify_ceo_fix_implemented(bug_id, bug)

        logging.info(f"Agent {agent_name} implemented fix for bug {bug_id}")
        return True

    def ceo_close_bug(self, bug_id: int) -> bool:
        """CEO closes the resolved bug"""
        bug = self._get_bug_report(bug_id)
        if not bug:
            logging.error(f"Bug {bug_id} not found")
            return False

        bug.status = BugStatus.CLOSED
        bug.updated_at = datetime.utcnow()

        self._update_bug_report(bug)

        logging.info(f"CEO closed bug {bug_id}")
        return True

    def get_bug_reports(self, status_filter: Optional[BugStatus] = None) -> List[BugReport]:
        """Get bug reports, optionally filtered by status"""
        session = self.db.get_session()
        try:
            query = session.query(BugReport)
            if status_filter:
                query = query.filter_by(status=status_filter)
            return query.order_by(BugReport.created_at.desc()).all()
        finally:
            session.close()

    def get_bug_stats(self) -> Dict:
        """Get bug statistics"""
        session = self.db.get_session()
        try:
            total = session.query(BugReport).count()
            open_bugs = session.query(BugReport).filter(
                BugReport.status.in_([
                    BugStatus.REPORTED, BugStatus.UNDER_REVIEW,
                    BugStatus.ASSIGNED, BugStatus.IN_PROGRESS
                ])
            ).count()

            by_severity = {}
            for severity in BugSeverity:
                count = session.query(BugReport).filter_by(severity=severity).count()
                by_severity[severity.value] = count

            return {
                "total_bugs": total,
                "open_bugs": open_bugs,
                "closed_bugs": total - open_bugs,
                "by_severity": by_severity
            }
        finally:
            session.close()

    def _store_bug_report(self, bug: BugReport) -> int:
        """Store bug report in database"""
        session = self.db.get_session()
        try:
            session.add(bug)
            session.commit()
            return bug.id
        finally:
            session.close()

    def _update_bug_report(self, bug: BugReport):
        """Update bug report in database"""
        session = self.db.get_session()
        try:
            session.merge(bug)
            session.commit()
        finally:
            session.close()

    def _get_bug_report(self, bug_id: int) -> Optional[BugReport]:
        """Get bug report from database"""
        session = self.db.get_session()
        try:
            return session.query(BugReport).filter_by(id=bug_id).first()
        finally:
            session.close()

    def _notify_ceo_bug_reported(self, bug_id: int, bug: BugReport):
        """Notify CEO of new bug report"""
        logging.info(f"NOTIFICATION: New bug reported to CEO - ID: {bug_id}, Title: {bug.title}, Severity: {bug.severity.value}")

    def _notify_agent_bug_assigned(self, bug_id: int, bug: BugReport):
        """Notify agent of bug assignment"""
        logging.info(f"NOTIFICATION: Bug {bug_id} assigned to {bug.assigned_agent} - {bug.title}")

    def _notify_ceo_fix_ready(self, bug_id: int, bug: BugReport):
        """Notify CEO that fix is ready for validation"""
        logging.info(f"NOTIFICATION: Fix ready for CEO validation - Bug {bug_id}: {bug.title}")

    def _notify_agent_implement_fix(self, bug_id: int, bug: BugReport):
        """Notify agent to implement approved fix"""
        logging.info(f"NOTIFICATION: Fix approved for implementation - Bug {bug_id} assigned to {bug.assigned_agent}")

    def _notify_agent_fix_rejected(self, bug_id: int, bug: BugReport):
        """Notify agent that fix was rejected"""
        logging.info(f"NOTIFICATION: Fix rejected for Bug {bug_id} - {bug.validation_notes}")

    def _notify_ceo_fix_implemented(self, bug_id: int, bug: BugReport):
        """Notify CEO that fix has been implemented"""
        logging.info(f"NOTIFICATION: Fix implemented for Bug {bug_id} - Ready for CEO closure")

# Global bug reporting system instance
bug_system = None

def init_bug_reporting() -> BugReportingSystem:
    """Initialize global bug reporting system"""
    global bug_system
    if bug_system is None:
        bug_system = BugReportingSystem()
    return bug_system

def get_bug_system() -> BugReportingSystem:
    """Get global bug reporting system"""
    global bug_system
    if bug_system is None:
        raise RuntimeError("Bug reporting system not initialized. Call init_bug_reporting() first.")
    return bug_system

# Convenience functions for easy bug reporting
def report_bug(title: str, description: str, severity: str = "medium",
              component: str = "general", reporter: str = "system") -> int:
    """Convenience function to report a bug"""
    system = get_bug_system()
    severity_enum = BugSeverity(severity.lower())
    return system.report_bug(title, description, severity_enum, component, reporter)

def get_open_bugs() -> List[BugReport]:
    """Get all open bugs"""
    system = get_bug_system()
    return system.get_bug_reports()

def get_bug_statistics() -> Dict:
    """Get bug statistics"""
    system = get_bug_system()
    return system.get_bug_stats()