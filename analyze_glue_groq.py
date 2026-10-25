"""
Standalone Glue Compatibility Extraction & Grok/Groq AI Analysis Script.

Extracts:
- Glue Version & Runtime Python Version
- Worker Type & Worker Count
- Additional Python Libraries (--additional-python-modules)

Sends this specification to Groq (https://console.groq.com) OpenAI-compatible API
and generates an Incompatibility Error Percentage Report, Why Reason,
and Most Compatible Version recommendations.
"""
import os
import sys
import json
import argparse
from typing import Dict, Any, List
from dotenv import load_dotenv

# Load environment variables (.env file)
load_dotenv()

try:
    from backend.ai_analyzer import TerraformGlueParser
except ImportError:
    # If executed inside backend or standalone
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from backend.ai_analyzer import TerraformGlueParser


GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
DEFAULT_GROQ_MODEL = "llama-3.1-8b-instant"


def call_groq_ai(job_data: Dict[str, Any], api_key: str, model: str = DEFAULT_GROQ_MODEL) -> Dict[str, Any]:
    """
    Sends the extracted Terraform Glue job details to Groq AI
    using urllib to avoid external dependencies.
    """
    import urllib.request
    import urllib.error

    glue_ver = job_data.get("glue_version", "4.0")
    declared_python = job_data.get("python_version", "3")

    prompt = f"""You are an AWS Cloud Big Data and Glue Python runtime specialist with knowledge of all AWS Glue versions.
Analyze this AWS Glue Terraform Job configuration:

- Job Name: {job_data.get('job_name')}
- Glue Version: {glue_ver}
- Declared Python Version: {declared_python}
- Worker Type: {job_data.get('worker_type')} ({job_data.get('number_of_workers')} workers)
- Additional Python Modules: {job_data.get('additional_python_modules') or 'None'}

Evaluate compatibility issues (Python version mismatch, wheel binary/GLIBC issues, worker memory constraints for ML/heavy packages, deprecated worker types).

You MUST return a valid JSON response strictly following this JSON schema (no extra preamble or markdown code blocks):
{{
  "incompatibility_percentage": <integer from 0 to 100>,
  "risk_level": "<CRITICAL | HIGH | MEDIUM | LOW | SAFE>",
  "why_reason": "<Clear detailed explanation why this setup fails or causes runtime crashes/slowness>",
  "specific_conflicts": [
    "<Conflict description 1>",
    "<Conflict description 2>"
  ],
  "most_compatible_version": {{
    "recommended_glue_version": "<e.g., 4.0 or 5.0>",
    "recommended_python_version": "<e.g., 3.10 or 3.11>",
    "recommended_worker_type": "<e.g., G.1X or G.2X>",
    "compatible_packages_recommendation": "<Specific compatible library versions to pin>"
  }},
  "summary_advice": "<Actionable summary for the engineer>"
}}
"""

    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": "You are an automated AWS Glue Terraform analyzer. Always answer with strictly valid JSON matching the requested schema."
            },
            {
                "role": "user",
                "content": prompt
            }
        ],
        "temperature": 0.2,
        "response_format": {"type": "json_object"}
    }

    req = urllib.request.Request(
        GROQ_API_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key.strip()}",
            "Content-Type": "application/json",
            "User-Agent": "Glue-Compat-Analyzer/1.0"
        },
        method="POST"
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            resp_data = json.loads(resp.read().decode("utf-8"))
            content = resp_data["choices"][0]["message"]["content"]
            return json.loads(content)
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8")
        return {"error": f"Groq API HTTP Error {e.code}: {error_body}"}
    except Exception as e:
        return {"error": f"Failed to call Groq API: {str(e)}"}


def analyze_terraform_file(tf_file_path: str, api_key: str, model: str = DEFAULT_GROQ_MODEL):
    """
    Parses Terraform file, extracts Glue configs, calls Groq AI, and prints the report.
    """
    if not os.path.isfile(tf_file_path):
        print(f"❌ Error: File not found: {tf_file_path}")
        return

    with open(tf_file_path, "r", encoding="utf-8") as f:
        content = f.read()

    jobs = TerraformGlueParser.extract_glue_jobs(content, os.path.basename(tf_file_path))

    if not jobs:
        print(f"⚠️ No 'aws_glue_job' resources discovered in {tf_file_path}")
        return

    print(f"\n=======================================================")
    print(f" 🔍 Found {len(jobs)} Glue Job(s) in {os.path.basename(tf_file_path)}")
    print(f"=======================================================\n")

    for idx, job in enumerate(jobs, 1):
        print(f"--- [Job {idx}/{len(jobs)}]: {job.get('job_name')} ---")
        print(f"• Glue Version       : {job.get('glue_version')}")
        print(f"• Worker Type        : {job.get('worker_type')} ({job.get('number_of_workers')} workers)")
        print(f"• Python Modules     : {job.get('additional_python_modules') or 'None'}")
        print(f"\n🚀 Contacting Groq AI ({model}) for analysis...\n")

        report = call_groq_ai(job, api_key, model)

        if "error" in report:
            print(f"❌ Error from Groq AI: {report['error']}\n")
            continue

        pct = report.get("incompatibility_percentage", 0)
        risk = report.get("risk_level", "UNKNOWN")
        why = report.get("why_reason", "N/A")
        recom = report.get("most_compatible_version", {})

        print("================== ANALYSIS REPORT ==================")
        print(f"📊 INCOMPATIBILITY ERROR PERCENTAGE : {pct}% [{risk}]")
        print(f"\n💡 WHY REASON:")
        print(f"   {why}")

        conflicts = report.get("specific_conflicts", [])
        if conflicts:
            print(f"\n⚠️ SPECIFIC CONFLICTS:")
            for c in conflicts:
                print(f"   - {c}")

        print(f"\n✅ MOST COMPATIBLE VERSION RECOMMENDATION:")
        print(f"   • Recommended Glue Version   : {recom.get('recommended_glue_version')}")
        print(f"   • Recommended Python Version : {recom.get('recommended_python_version')}")
        print(f"   • Recommended Worker Type    : {recom.get('recommended_worker_type')}")
        print(f"   • Packages Recommendation    : {recom.get('compatible_packages_recommendation')}")

        if report.get("summary_advice"):
            print(f"\n📌 SUMMARY ADVICE:")
            print(f"   {report.get('summary_advice')}")
        print("=====================================================\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Analyze Terraform Glue jobs with Groq AI")
    parser.add_argument("tf_file", nargs="?", default="test_compatibility_issues.tf", help="Path to Terraform (.tf) file")
    parser.add_argument("--key", default=None, help="Groq API Key (or set GROQ_API_KEY in .env)")
    parser.add_argument("--model", default=None, help="Groq model (default: llama-3.3-70b-versatile)")

    args = parser.parse_args()

    api_key = args.key or os.getenv("GROQ_API_KEY")
    if not api_key:
        print("❌ Missing Groq API Key!")
        print("Please provide it via one of these options:")
        print("1. Set GROQ_API_KEY=gsk_... in your .env file")
        print("2. Pass --key gsk_... on the command line\n")
        print("Get your API key at: https://console.groq.com/keys")
        sys.exit(1)

    model = args.model or os.getenv("GROQ_MODEL") or DEFAULT_GROQ_MODEL
    analyze_terraform_file(args.tf_file, api_key, model)
