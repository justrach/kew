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
    # Clear the dist folder
    run_cmd("rm -rf dist/*")
    
    # Build
    run_cmd("python -m build")
    
    # Install locally in development mode
    run_cmd("uv pip install -e .")
    
    # Run tests against installed package
    run_cmd("pytest --cov=kew")
    
    # Upload to PyPI/TestPyPI if tests pass
    if "--production" in sys.argv:
        run_cmd("twine upload dist/*")
    else:
        run_cmd("twine upload --repository kew dist/*")
if __name__ == "__main__":
    main()