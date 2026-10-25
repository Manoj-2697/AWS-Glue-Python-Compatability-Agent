"""
Application entry point for running from the root workspace directory.
"""
import sys
import os

# Set working directory to project root
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

from backend.main import app
import uvicorn

if __name__ == "__main__":
    print("=======================================================")
    print("  ⚡ AWS Glue Terraform AI Analyzer is Starting...    ")
    print("  👉 Open http://127.0.0.1:8000 in your browser       ")
    print("=======================================================")
    uvicorn.run(app, host="127.0.0.1", port=8000)
