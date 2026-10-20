#!/usr/bin/env python3
"""Root package execution entry point for gemini-integrated.

Allows executing the repository directory directly with Python:
    python3 gemini-integrated satellite
    python3 gemini-integrated
"""
import os
import runpy
import sys

repo_dir = os.path.dirname(os.path.abspath(__file__))
if repo_dir not in sys.path:
    sys.path.insert(0, repo_dir)

if __name__ == "__main__":
    runner_path = os.path.join(repo_dir, "gemini-integrated.py")
    runpy.run_path(runner_path, run_name="__main__")
