# -*- coding: utf-8 -*-
"""
Creates the official repository ZIP backup including the full .git directory
for the assessment submission form, strictly excluding .env, caches, and test DBs.
"""

import os
import sys
import zipfile

def create_repo_zip():
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    parent_dir = os.path.dirname(base_dir)
    output_zip = os.path.join(parent_dir, "sewasetu-assistant.zip")

    exclude_dirs = {".pytest_cache", "__pycache__", "venv", ".venv"}
    exclude_files = {".env", "test_local.db"}
    exclude_exts = {".pyc", ".pyo", ".log"}

    print(f"Creating repository backup from: {base_dir}")
    print(f"Target archive: {output_zip}")

    count = 0
    git_count = 0

    with zipfile.ZipFile(output_zip, "w", zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(base_dir):
            dirs[:] = [d for d in dirs if d not in exclude_dirs]
            for file in files:
                if file in exclude_files:
                    continue
                if any(file.endswith(ext) for ext in exclude_exts):
                    continue

                full_path = os.path.join(root, file)
                rel_path = os.path.relpath(full_path, base_dir)
                arc_name = os.path.join("sewasetu-assistant", rel_path).replace("\\", "/")

                zipf.write(full_path, arc_name)
                count += 1
                if ".git" in arc_name:
                    git_count += 1

    zip_size = os.path.getsize(output_zip)
    print("=" * 60)
    print("REPOSITORY ZIP CREATED SUCCESSFULLY")
    print(f"Archive Path : {output_zip}")
    print(f"Total Files  : {count}")
    print(f"Git Files    : {git_count}")
    print(f"Archive Size : {zip_size:,} bytes ({zip_size / (1024*1024):.2f} MB)")
    print("=" * 60)
    return output_zip

if __name__ == "__main__":
    create_repo_zip()
