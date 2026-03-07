#!/usr/bin/env python3  
""" >> security_hardening.py && echo SovereignForge Security Hardening Script >> security_hardening.py && echo """  
  
import os  
import sys  
import json  
import logging  
from pathlib import Path  
from datetime import datetime  
  
logger = logging.getLogger(__name__)  
  
def main():  
    """Apply security hardening measures"""  
    logging.basicConfig(level=logging.INFO)  
    logger.info("?? Applying security hardening...")  
  
    # Create secure directories  
    directories = ["certs", "secrets", "logs", "reports"]  
    for dir_name in directories:  
        dir_path = Path(dir_name)  
        dir_path.mkdir(exist_ok=True)  
        gitkeep = dir_path / ".gitkeep"  
        if not gitkeep.exists():  
            gitkeep.write_text("")  
  
    # Create .env.example  
    env_example = Path(".env.example")  
    if not env_example.exists():  
        env_content = """# Security Settings >> security_hardening.py && echo DEBUG=false >> security_hardening.py && echo SECRET_KEY=change_this_to_a_random_secret_key >> security_hardening.py && echo """  
        env_example.write_text(env_content)  
  
    print("? Security hardening completed")  
  
if __name__ == "__main__":  
    main() 
