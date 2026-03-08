#!/usr/bin/env python3
"""
Test script for Personal Security Manager
Tests local execution verification, data isolation, and MiCA compliance
"""

import os
import sys
import logging
import time
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.personal_security import (
    get_security_manager,
    verify_local_execution,
    check_security_status,
    perform_security_scan,
    create_secure_environment,
    PersonalSecurityManager
)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def test_local_execution_verification():
    """Test local execution verification"""
    logger.info("Testing local execution verification...")

    # Test direct function
    is_local = verify_local_execution()
    logger.info(f"Local execution verified: {is_local}")

    # Test via security manager
    security_manager = get_security_manager()
    proof = security_manager.verify_local_execution()

    logger.info(f"Network interfaces: {len(proof.network_interfaces)}")
    logger.info(f"External connections: {len(proof.external_connections)}")
    logger.info(f"Local execution proof: {proof.is_local_only}")

    assert proof.is_local_only == is_local, "Local execution verification mismatch"
    return proof.is_local_only

def test_resource_limits():
    """Test resource limit checking"""
    logger.info("Testing resource limits...")

    security_manager = get_security_manager()
    within_limits = security_manager.check_resource_limits()

    logger.info(f"Resource limits check: {'PASSED' if within_limits else 'FAILED'}")
    return within_limits

def test_data_access_validation():
    """Test data access validation"""
    logger.info("Testing data access validation...")

    security_manager = get_security_manager()

    # Test allowed path
    allowed_path = str(Path.home() / "SovereignForge" / "test.txt")
    allowed = security_manager.validate_data_access(allowed_path)
    logger.info(f"Allowed path validation: {'PASSED' if allowed else 'FAILED'}")

    # Test unauthorized path (system root)
    unauthorized_path = "/etc/passwd" if os.name != 'nt' else "C:\\Windows\\system32\\config"
    unauthorized = security_manager.validate_data_access(unauthorized_path)
    logger.info(f"Unauthorized path validation: {'PASSED' if not unauthorized else 'FAILED'}")

    # Test sensitive file
    sensitive_path = str(Path.home() / "SovereignForge" / "api_keys.json")
    sensitive = security_manager.validate_data_access(sensitive_path)
    logger.info(f"Sensitive file validation: {'PASSED' if not sensitive else 'FAILED'}")

    return allowed and not unauthorized and not sensitive

def test_secure_environment():
    """Test secure environment creation"""
    logger.info("Testing secure environment creation...")

    secure_env = create_secure_environment()

    required_vars = [
        "NO_EXTERNAL_NETWORK",
        "LOCAL_ONLY_EXECUTION",
        "MEMORY_LIMIT_GB",
        "CPU_LIMIT_PCT",
        "DATA_ISOLATION_ENABLED",
        "MODEL_INTEGRITY_CHECK"
    ]

    missing_vars = [var for var in required_vars if var not in secure_env]
    if missing_vars:
        logger.error(f"Missing environment variables: {missing_vars}")
        return False

    logger.info("Secure environment variables set correctly")
    return True

def test_mica_compliance():
    """Test MiCA compliance status"""
    logger.info("Testing MiCA compliance...")

    security_manager = get_security_manager()
    compliance_status = security_manager.get_mica_compliance_status()

    required_fields = [
        "personal_deployment",
        "no_custody",
        "no_public_offering",
        "local_execution_only",
        "data_isolation",
        "mica_compliant"
    ]

    missing_fields = [field for field in required_fields if field not in compliance_status]
    if missing_fields:
        logger.error(f"Missing MiCA compliance fields: {missing_fields}")
        return False

    logger.info(f"MiCA compliant: {compliance_status.get('mica_compliant', False)}")
    logger.info(f"Personal deployment: {compliance_status.get('personal_deployment', False)}")
    logger.info(f"No custody: {compliance_status.get('no_custody', False)}")

    return compliance_status.get('mica_compliant', False)

def test_security_scan():
    """Test comprehensive security scan"""
    logger.info("Testing comprehensive security scan...")

    scan_result = perform_security_scan()

    required_fields = [
        "timestamp",
        "local_execution_check",
        "resource_limits_check",
        "data_isolation_check",
        "violations_found",
        "security_status"
    ]

    missing_fields = [field for field in required_fields if field not in scan_result]
    if missing_fields:
        logger.error(f"Missing security scan fields: {missing_fields}")
        return False

    logger.info(f"Security scan status: {scan_result['security_status']}")
    logger.info(f"Violations found: {scan_result['violations_found']}")

    return scan_result['security_status'] in ['secure', 'warning']

def test_security_report():
    """Test security report generation"""
    logger.info("Testing security report generation...")

    security_report = check_security_status()

    required_sections = [
        "security_status",
        "local_execution_verified",
        "violations_count",
        "resource_limits",
        "data_isolation",
        "mica_compliance"
    ]

    missing_sections = [section for section in required_sections if section not in security_report]
    if missing_sections:
        logger.error(f"Missing security report sections: {missing_sections}")
        return False

    logger.info(f"Security status: {security_report['security_status']}")
    logger.info(f"Local execution verified: {security_report['local_execution_verified']}")
    logger.info(f"Violations count: {security_report['violations_count']}")

    return True

def run_all_tests():
    """Run all security tests"""
    logger.info("Starting Personal Security Manager tests...")

    # Use relaxed limits for development testing
    security_manager = PersonalSecurityManager(
        max_memory_usage_gb=32.0,  # Allow up to 32GB for development
        max_cpu_usage_pct=95.0     # Allow up to 95% CPU for development
    )

    # Override the global instance for testing
    global _security_manager
    _security_manager = security_manager

    tests = [
        ("Local Execution Verification", test_local_execution_verification),
        ("Resource Limits", test_resource_limits),
        ("Data Access Validation", test_data_access_validation),
        ("Secure Environment", test_secure_environment),
        ("MiCA Compliance", test_mica_compliance),
        ("Security Scan", test_security_scan),
        ("Security Report", test_security_report),
    ]

    results = []
    for test_name, test_func in tests:
        try:
            logger.info(f"\n--- Running {test_name} ---")
            result = test_func()
            results.append((test_name, result))
            logger.info(f"✅ {test_name}: {'PASSED' if result else 'FAILED'}")
        except Exception as e:
            logger.error(f"❌ {test_name}: ERROR - {e}")
            results.append((test_name, False))

    # Summary
    logger.info("\n" + "="*50)
    logger.info("PERSONAL SECURITY TEST SUMMARY")
    logger.info("="*50)

    passed = 0
    total = len(results)

    for test_name, result in results:
        status = "✅ PASSED" if result else "❌ FAILED"
        logger.info(f"{status}: {test_name}")
        if result:
            passed += 1

    logger.info(f"\nOverall: {passed}/{total} tests passed")

    if passed == total:
        logger.info("🎉 All personal security tests PASSED!")
        return True
    else:
        logger.warning(f"⚠️  {total - passed} tests failed")
        return False

if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)