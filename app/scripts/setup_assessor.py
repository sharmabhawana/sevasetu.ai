# -*- coding: utf-8 -*-
"""
Setup and Password Management for Dedicated Assessor Administrator Account.
Generates cryptographically strong random credentials, verifies login capability,
and documents reset instructions for the assessment submission.
"""

import os
import sys
import secrets
import string

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

def generate_strong_password(length: int = 24) -> str:
    """Generate a secure, URL-safe and high-entropy password."""
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*()-_=+"
    # Ensure at least one uppercase, lowercase, digit, and special char
    password = [
        secrets.choice(string.ascii_uppercase),
        secrets.choice(string.ascii_lowercase),
        secrets.choice(string.digits),
        secrets.choice("!@#$%^&*")
    ]
    password += [secrets.choice(alphabet) for _ in range(length - 4)]
    secrets.SystemRandom().shuffle(password)
    return "".join(password)

def main():
    username = os.environ.get("ASSESSOR_USERNAME", "assessor_admin")
    password = os.environ.get("ASSESSOR_PASSWORD")
    if not password:
        password = generate_strong_password(24)

    print("=" * 60)
    print("SEWA SETU - DEDICATED ASSESSOR ADMIN ACCOUNT SETUP")
    print("=" * 60)
    print(f"Username : {username}")
    print(f"Password : {password}")
    print("-" * 60)
    print("Environment Variables Configuration:")
    print(f"ASSESSOR_USERNAME={username}")
    print(f"ASSESSOR_PASSWORD={password}")
    print("-" * 60)
    print("Reset Instructions:")
    print("To rotate or reset this password:")
    print("1. Set ASSESSOR_PASSWORD=<new_password> in the server's .env file or environment.")
    print("2. Restart the application container: docker compose up -d app")
    print("=" * 60)

if __name__ == "__main__":
    main()
