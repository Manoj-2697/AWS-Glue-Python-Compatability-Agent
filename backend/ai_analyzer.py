"""
AWS Glue Terraform AI Analyzer (Dual: Web API & CLI)
1. Extracts Glue & Python configurations from Terraform files
2. Queries Groq AI for incompatibility percentage, why reason, and optimal versions
3. Can be imported by web_app.py OR executed directly via CLI:
   python backend/ai_analyzer.py test_compatibility_issues.tf
"""
import os
import re
import sys
import json
import argparse
import urllib.request
import urllib.error
from typing import Dict, Any, List, Optional
from dotenv import load_dotenv

load_dotenv()

GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
DEFAULT_GROQ_MODEL = os.getenv("GROQ_MODEL", "qwen/qwen3.8-27b")


# =============================================================================
# 1. TERRAFORM GLUE EXTRACTOR
# =============================================================================
class TerraformGlueParser:
    @staticmethod
    def extract_glue_jobs(content: str, filename: str = "") -> List[Dict[str, Any]]:
        jobs = []
        for match in re.finditer(r'resource\s+"aws_glue_job"\s+"([^"]+)"\s*\{', content):
            res_id = match.group(1)
            start = match.end() - 1
            brace_count = 0
            end = -1
            for i in range(start, len(content)):
                if content[i] == '{':
                    brace_count += 1
                elif content[i] == '}':
                    brace_count -= 1
                    if brace_count == 0:
                        end = i
                        break
            if end != -1:
                body = content[start+1:end]
                jobs.append(TerraformGlueParser._parse_job(res_id, body, filename))
        return jobs

    @staticmethod
    def _parse_job(res_id: str, body: str, filename: str) -> Dict[str, Any]:
        name_m = re.search(r'name\s*=\s*["\']([^"\']+)["\']', body)
        glue_m = re.search(r'glue_version\s*=\s*["\']([^"\']+)["\']', body)
        worker_m = re.search(r'worker_type\s*=\s*["\']([^"\']+)["\']', body)
        workers_cnt_m = re.search(r'number_of_workers\s*=\s*([0-9]+)', body)

        # Python version from command block
        py_ver = "3"
        cmd_m = re.search(r'command\s*\{([^}]+)\}', body, re.DOTALL)
        if cmd_m:
            py_m = re.search(r'python_version\s*=\s*["\']([^"\']+)["\']', cmd_m.group(1))
            if py_m:
                py_ver = py_m.group(1)

        # Default arguments
        default_args = {}
        args_m = re.search(r'default_arguments\s*=\s*\{([^}]+)\}', body, re.DOTALL)
        if args_m:
            for line in args_m.group(1).splitlines():
                kv = re.match(r'["\']?([^"\'\s=]+)["\']?\s*=\s*["\']?([^"\']+)["\']?', line.strip())
                if kv and not line.strip().startswith(('#', '//')):
                    default_args[kv.group(1)] = kv.group(2).strip('"\'')

        return {
            "resource_id": res_id,
            "job_name": name_m.group(1) if name_m else res_id,
            "filename": filename,
            "glue_version": glue_m.group(1) if glue_m else "Unspecified",
            "worker_type": worker_m.group(1) if worker_m else "Unspecified",
            "number_of_workers": int(workers_cnt_m.group(1)) if workers_cnt_m else 2,
            "python_version": py_ver,
            "additional_python_modules": default_args.get("--additional-python-modules", "None"),
            "extra_py_files": default_args.get("--extra-py-files", "None")
        }


# =============================================================================
# 2. GROQ AI COMPATIBILITY ANALYZER
# =============================================================================
class GlueAIAnalyzer:
    @classmethod
    def query_groq(cls, job: Dict[str, Any], api_key: str, model: str = DEFAULT_GROQ_MODEL) -> Dict[str, Any]:
        prompt = f"""You are an AWS Glue and Python compatibility specialist.
Analyze this AWS Glue Terraform Job configuration:
- Job Name: {job.get('job_name')}
- Glue Version: {job.get('glue_version')}
- Declared Python Version: {job.get('python_version')}
- Worker Type: {job.get('worker_type')} ({job.get('number_of_workers')} workers)
- Additional Python Modules: {job.get('additional_python_modules')}

Evaluate compatibility issues (Python version mismatch, wheel/GLIBC issues, worker memory constraints).

Respond strictly in valid JSON matching this schema:
{{
  "incompatibility_percentage": <integer 0-100>,
  "verdict": "<HEALTHY | WARNINGS FOUND | ACTION REQUIRED - INCOMPATIBILITY DETECTED>",
  "executive_summary": "<Short executive summary paragraph on why this fails or succeeds>",
  "recommended_version": {{
    "glue_version": "<e.g. 5.0>",
    "python_version": "<e.g. 3.11>",
    "worker_type": "<e.g. G.1X or G.2X>",
    "rationale": "<Reason why this recommended version is best>"
  }},
  "packages_analysis": [
    {{
      "package": "<package_name>",
      "status": "<pass | fail | warning>",
      "what_is_issue": "<What is the issue>",
      "why_not_compatible": "<Why it is not compatible>",
      "why_suggested_version": "<Why the recommended version resolves this>",
      "error_if_proceed": "<Exact runtime crash or error if engineer proceeds>"
    }}
  ]
}}"""

        req = urllib.request.Request(
            GROQ_API_URL,
            data=json.dumps({
                "model": model,
                "messages": [
                    {"role": "system", "content": "You are an automated AWS Glue analyzer. Output strictly valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.2
            }).encode("utf-8"),
            headers={"Authorization": f"Bearer {api_key.strip()}", "Content-Type": "application/json", "User-Agent": "Glue-Compat/1.0"},
            method="POST"
        )

        import time
        max_retries = 3
        for attempt in range(max_retries):
            try:
                with urllib.request.urlopen(req, timeout=30) as resp:
                    content = json.loads(resp.read().decode("utf-8"))["choices"][0]["message"]["content"]
                    match = re.search(r'\{.*\}', content, re.DOTALL)
                    return json.loads(match.group(0) if match else content)
            except urllib.error.HTTPError as e:
                if e.code == 429 and attempt < max_retries - 1:
                    time.sleep(3 * (attempt + 1))
                    continue
                raise

    @classmethod
    async def analyze_job(cls, job: Dict[str, Any], grok_api_key: Optional[str] = None, use_grok: bool = False) -> Dict[str, Any]:
        """Method called by FastAPI web server."""
        api_key = grok_api_key or os.getenv("GROQ_API_KEY")
        if not api_key:
            return {"job_name": job.get("job_name"), "file": job.get("filename"), "verdict": "ERROR", "inefficiency_score": 0, "ai_executive_summary": "Missing GROQ_API_KEY in .env", "library_checks": []}

        try:
            parsed = cls.query_groq(job, api_key, os.getenv("GROQ_MODEL", DEFAULT_GROQ_MODEL))
            pct = parsed.get("incompatibility_percentage", 0)

            # Map packages to library checks for the web UI
            library_checks = []
            for p in parsed.get("packages_analysis", []):
                library_checks.append({
                    "raw": p.get("package", ""),
                    "package": p.get("package", ""),
                    "status": p.get("status", "pass"),
                    "requires_python": "Evaluated by AI",
                    "pypi_latest": "Available via AI",
                    "issue_summary": {
                        "is_issue": p.get("status") in ["fail", "warning"],
                        "what_is_issue": p.get("what_is_issue", "N/A"),
                        "why_not_compatible": p.get("why_not_compatible", "N/A"),
                        "why_suggested_version": p.get("why_suggested_version", "N/A"),
                        "error_if_proceed": p.get("error_if_proceed", "N/A")
                    }
                })

            return {
                "job_name": job.get("job_name"),
                "resource_id": job.get("resource_id"),
                "file": job.get("filename"),
                "glue_version": job.get("glue_version"),
                "runtime_python": job.get("python_version"),
                "worker_type": job.get("worker_type"),
                "worker_status": "compatible" if pct < 50 else "warning",
                "overall_compatible": pct == 0,
                "verdict": parsed.get("verdict", "ACTION REQUIRED - INCOMPATIBILITY DETECTED"),
                "inefficiency_score": pct,
                "health_score": 100 - pct,
                "recommended_version": parsed.get("recommended_version", {}),
                "ai_executive_summary": parsed.get("executive_summary", ""),
                "library_checks": library_checks
            }
        except Exception as e:
            return {"job_name": job.get("job_name"), "file": job.get("filename"), "verdict": "ERROR", "inefficiency_score": 0, "ai_executive_summary": f"Groq Error: {str(e)}", "library_checks": []}


# =============================================================================
# 3. DIRECT CLI RUNNER
# =============================================================================
def run_cli():
    parser = argparse.ArgumentParser(description="Analyze Terraform Glue jobs with Groq AI")
    parser.add_argument("tf_file", nargs="?", default="test_compatibility_issues.tf", help="Path to Terraform (.tf) file")
    parser.add_argument("--key", default=None, help="Groq API Key (or set GROQ_API_KEY in .env)")
    parser.add_argument("--model", default=None, help="Groq model (default: qwen/qwen3.8-27b)")
    args = parser.parse_args()

    api_key = args.key or os.getenv("GROQ_API_KEY")
    if not api_key:
        print("❌ Error: Missing Groq API Key! Please set GROQ_API_KEY in .env or pass --key")
        sys.exit(1)

    if not os.path.isfile(args.tf_file):
        print(f"❌ Error: File not found: {args.tf_file}")
        sys.exit(1)

    with open(args.tf_file, "r", encoding="utf-8") as f:
        jobs = TerraformGlueParser.extract_glue_jobs(f.read(), os.path.basename(args.tf_file))

    model = args.model or os.getenv("GROQ_MODEL", DEFAULT_GROQ_MODEL)
    print(f"\n⚡ Found {len(jobs)} Glue Job(s) in {args.tf_file}. Analyzing with Groq AI ({model})...\n")

    for idx, job in enumerate(jobs, 1):
        print(f"=== [Job {idx}/{len(jobs)}]: {job.get('job_name')} ===")
        print(f"• Glue Version   : {job.get('glue_version')}")
        print(f"• Worker Type    : {job.get('worker_type')}")
        print(f"• Python Modules : {job.get('additional_python_modules')}")
        try:
            report = GlueAIAnalyzer.query_groq(job, api_key, model)
            print(f"📊 INCOMPATIBILITY: {report.get('incompatibility_percentage', 0)}% [{report.get('verdict')}]")
            print(f"💡 SUMMARY        : {report.get('executive_summary')}")
            recom = report.get('recommended_version', {})
            print(f"✅ TARGET VERSION : Glue {recom.get('glue_version')} (Python {recom.get('python_version')}) | Worker: {recom.get('worker_type')}")
            print(f"   Rationale      : {recom.get('rationale')}")
            packages = report.get('packages_analysis', [])
            if packages:
                print("\n📦 PACKAGES BREAKDOWN:")
                for p in packages:
                    if p.get('status') in ['fail', 'warning']:
                        print(f"   - {p.get('package')}: {p.get('what_is_issue')}")
                        print(f"     Crash Risk: {p.get('error_if_proceed')}")
        except Exception as e:
            print(f"❌ Error: {e}")
        print("=" * 60 + "\n")


if __name__ == "__main__":
    run_cli()
