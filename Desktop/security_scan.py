#!/usr/bin/env python3  
"""Security Scanner"""  
import os  
import sys  
import re  
from pathlib import Path  
  
def main():  
    print("?? Security Scan Started")  
    issues = []  
    # Check for missing certificates  
    cert_files = ["certs/server.crt", "certs/server.key"]  
    for cert_file in cert_files:  
        if not Path(cert_file).exists():  
            issues.append(f"Missing certificate: {cert_file}")  
    if issues:  
        print("?? Issues found:")  
        for issue in issues:  
            print(f"  - {issue}")  
        sys.exit(1)  
    else:  
        print("? No security issues found")  
  
if __name__ == "__main__":  
    main() 
