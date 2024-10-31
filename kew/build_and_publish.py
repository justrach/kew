#!/usr/bin/env python3

import subprocess
import sys

def run_cmd(cmd):
    print(f"Running: {cmd}")
    result = subprocess.run(cmd, shell=True)
    if result.returncode != 0:
        print(f"Error running: {cmd}")
        sys.exit(1)

def main():
    # Run tests
    run_cmd("pytest --cov=kew")
    
    # Build
    run_cmd("python -m build")
    
    # Upload to PyPI/TestPyPI
    if "--production" in sys.argv:
        run_cmd("twine upload dist/*")
    else:
        run_cmd("twine upload --repository kew dist/*")

if __name__ == "__main__":
    main()