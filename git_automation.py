#!/usr/bin/env python3
"""
SovereignForge Git Automation Script
Automates git operations with intelligent commit messages and status reporting
"""

import subprocess
import os
import sys
from pathlib import Path
from datetime import datetime
import json

class GitAutomation:
    """Git automation with intelligent commit messages"""

    def __init__(self, repo_path="."):
        self.repo_path = Path(repo_path)
        self.status_info = {}

    def run_command(self, cmd, capture_output=True):
        """Run a git command and return result"""
        try:
            result = subprocess.run(
                cmd,
                shell=True,
                cwd=self.repo_path,
                capture_output=capture_output,
                text=True,
                check=True
            )
            return result.stdout.strip() if capture_output else ""
        except subprocess.CalledProcessError as e:
            print(f"Git command failed: {cmd}")
            print(f"Error: {e.stderr}")
            return None
        except UnicodeEncodeError:
            # Handle Windows encoding issues
            print("Encoding issue detected, retrying with ASCII-safe output...")
            return None

    def get_status(self):
        """Get comprehensive git status"""
        print("[INFO] Checking git status...")

        # Get basic status
        status = self.run_command("git status --porcelain")
        if status is None:
            return False

        # Get branch info
        branch = self.run_command("git branch --show-current")
        if branch is None:
            return False

        # Get recent commits
        recent_commits = self.run_command("git log --oneline -5")
        if recent_commits is None:
            recent_commits = "No commits yet"

        # Get diff stats
        diff_stats = self.run_command("git diff --stat")
        if diff_stats is None:
            diff_stats = "No changes"

        # Get staged changes
        staged = self.run_command("git diff --cached --stat")
        if staged is None:
            staged = "No staged changes"

        self.status_info = {
            'branch': branch,
            'status': status,
            'recent_commits': recent_commits,
            'diff_stats': diff_stats,
            'staged': staged,
            'has_changes': len(status.strip()) > 0
        }

        return True

    def analyze_changes(self):
        """Analyze what types of changes were made"""
        if not self.status_info.get('has_changes'):
            return "No changes to commit"

        status = self.status_info['status']

        change_types = {
            'added': [],
            'modified': [],
            'deleted': [],
            'renamed': []
        }

        for line in status.split('\n'):
            if not line.strip():
                continue

            status_code = line[:2]
            filename = line[3:]

            if status_code in ['A ', 'AM', 'A?']:
                change_types['added'].append(filename)
            elif status_code in ['M ', 'MM']:
                change_types['modified'].append(filename)
            elif status_code in ['D ', 'DM']:
                change_types['deleted'].append(filename)
            elif status_code in ['R ', 'RM']:
                change_types['renamed'].append(filename)

        return change_types

    def generate_commit_message(self, change_types):
        """Generate intelligent commit message based on changes"""
        if not self.status_info.get('has_changes'):
            return None

        # Categorize changes
        has_tests = any('test' in f.lower() or f.startswith('tests/') for f in change_types['added'] + change_types['modified'])
        has_models = any('model' in f.lower() or f.endswith('.pth') or f.endswith('.json') for f in change_types['added'] + change_types['modified'])
        has_config = any('config' in f.lower() or f.endswith('.json') or f.endswith('.yaml') for f in change_types['added'] + change_types['modified'])
        has_docs = any(f.endswith('.md') or 'readme' in f.lower() for f in change_types['added'] + change_types['modified'])
        has_renames = len(change_types['renamed']) > 0

        # Generate message based on change types
        if has_renames and 'usdt' in str(change_types['renamed']).lower():
            return "feat: rename model files from USDT to USDC for MiCA compliance"

        if has_tests and len(change_types['modified']) == 0:
            return "test: fix failing tests and improve test coverage"

        if has_models and not has_tests:
            return "feat: update model files and metadata"

        if has_docs and len(change_types['modified']) <= 2:
            return "docs: update documentation and project status"

        if has_config:
            return "config: update configuration files and settings"

        # Generic messages
        if len(change_types['added']) > len(change_types['modified']):
            return "feat: add new functionality and components"
        elif len(change_types['modified']) > 0:
            return "refactor: update existing code and improve functionality"
        else:
            return "chore: maintenance and cleanup"

    def stage_changes(self):
        """Stage all changes"""
        print("[INFO] Staging changes...")
        result = self.run_command("git add .")
        return result is not None

    def commit_changes(self, message):
        """Commit changes with message"""
        print(f"[INFO] Committing with message: {message}")
        result = self.run_command(f'git commit -m "{message}"')
        return result is not None

    def show_summary(self):
        """Show summary of changes"""
        print("\n[INFO] Git Status Summary:")
        print(f"Branch: {self.status_info.get('branch', 'unknown')}")
        print(f"Has Changes: {self.status_info.get('has_changes', False)}")

        if self.status_info.get('has_changes'):
            change_types = self.analyze_changes()
            print(f"Added: {len(change_types['added'])} files")
            print(f"Modified: {len(change_types['modified'])} files")
            print(f"Deleted: {len(change_types['deleted'])} files")
            print(f"Renamed: {len(change_types['renamed'])} files")

    def run_automation(self):
        """Run the complete git automation workflow"""
        print("[INFO] SovereignForge Git Automation Starting...\n")

        # Get status
        if not self.get_status():
            print("[ERROR] Failed to get git status")
            return False

        # Show summary
        self.show_summary()

        # Check for changes
        if not self.status_info.get('has_changes'):
            print("[SUCCESS] No changes to commit")
            return True

        # Analyze changes and generate message
        change_types = self.analyze_changes()
        commit_message = self.generate_commit_message(change_types)

        if not commit_message:
            print("[ERROR] Could not generate commit message")
            return False

        print(f"\n[INFO] Generated commit message: {commit_message}")

        # Stage changes
        if not self.stage_changes():
            print("[ERROR] Failed to stage changes")
            return False

        # Commit changes
        if not self.commit_changes(commit_message):
            print("[ERROR] Failed to commit changes")
            return False

        print("[SUCCESS] Successfully committed changes!")
        return True

def main():
    """Main entry point"""
    automation = GitAutomation()

    if len(sys.argv) > 1:
        if sys.argv[1] == "--status":
            automation.get_status()
            automation.show_summary()
            return
        elif sys.argv[1] == "--dry-run":
            automation.get_status()
            automation.show_summary()
            change_types = automation.analyze_changes()
            message = automation.generate_commit_message(change_types)
            if message:
                print(f"\n[INFO] Would commit with: {message}")
            return

    # Run full automation
    success = automation.run_automation()
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()