"""
Pure AI Analysis Engine for AWS Glue Terraform Configurations
Extracts Glue & Python infrastructure details from Terraform HCL,
sends the details directly to Groq AI, and returns the response.
"""
import os
import re
import json
import urllib.request
import urllib.error
from typing import Dict, Any, List, Optional

GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
DEFAULT_GROQ_MODEL = "llama-3.1-8b-instant"


# =============================================================================
# 1. TERRAFORM GLUE HCL EXTRACTOR
# =============================================================================
class TerraformGlueParser:
    """Extracts aws_glue_job configurations and python arguments from Terraform files."""

    @staticmethod
    def extract_glue_jobs(content: str, filename: str = "") -> List[Dict[str, Any]]:
        jobs = []
        for match in re.finditer(r'resource\s+"aws_glue_job"\s+"([^"]+)"\s*\{', content):
            resource_name = match.group(1)
            start_index = match.end() - 1
            brace_count = 0
            end_index = -1
            for i in range(start_index, len(content)):
                if content[i] == '{':
                    brace_count += 1
                elif content[i] == '}':
                    brace_count -= 1
                    if brace_count == 0:
                        end_index = i
                        break
            if end_index != -1:
                block_content = content[start_index+1:end_index]
                jobs.append(TerraformGlueParser._parse_job_block(resource_name, block_content, filename))
        return jobs

    @staticmethod
    def _parse_job_block(res_id: str, body: str, filename: str) -> Dict[str, Any]:
        name_match = re.search(r'name\s*=\s*["\']([^"\']+)["\']', body)
        job_name = name_match.group(1) if name_match else res_id

        glue_ver_match = re.search(r'glue_version\s*=\s*["\']([^"\']+)["\']', body)
        glue_version = glue_ver_match.group(1) if glue_ver_match else "Unspecified"

        worker_match = re.search(r'worker_type\s*=\s*["\']([^"\']+)["\']', body)
        worker_type = worker_match.group(1) if worker_match else "Unspecified"

        workers_count_match = re.search(r'number_of_workers\s*=\s*([0-9]+)', body)
        number_of_workers = int(workers_count_match.group(1)) if workers_count_match else 2

        # Extract python version from command block
        command_match = re.search(r'command\s*\{([^}]+)\}', body, re.DOTALL)
        python_version = "3"
        script_location = None
        command_name = "glueetl"
        if command_match:
            cmd_body = command_match.group(1)
            py_match = re.search(r'python_version\s*=\s*["\']([^"\']+)["\']', cmd_body)
            if py_match:
                python_version = py_match.group(1)
            script_match = re.search(r'script_location\s*=\s*["\']([^"\']+)["\']', cmd_body)
            if script_match:
                script_location = script_match.group(1)
            cname_match = re.search(r'name\s*=\s*["\']([^"\']+)["\']', cmd_body)
            if cname_match:
                command_name = cname_match.group(1)

        # Extract default_arguments map
        default_args = {}
        args_match = re.search(r'default_arguments\s*=\s*\{([^}]+)\}', body, re.DOTALL)
        if args_match:
            args_block = args_match.group(1)
            for line in args_block.splitlines():
                line = line.strip()
                if not line or line.startswith("#") or line.startswith("//"):
                    continue
                arg_kv = re.match(r'["\']?([^"\'\s=]+)["\']?\s*=\s*["\']?([^"\']+)["\']?', line)
                if arg_kv:
                    k, v = arg_kv.group(1), arg_kv.group(2)
                    default_args[k] = v.strip('"\'')

        additional_py_modules = default_args.get("--additional-python-modules", "")
        extra_py_files = default_args.get("--extra-py-files", "")
        extra_jars = default_args.get("--extra-jars", "")

        return {
            "resource_id": res_id,
            "job_name": job_name,
            "filename": filename,
            "glue_version": glue_version,
            "worker_type": worker_type,
            "number_of_workers": number_of_workers,
            "command_name": command_name,
            "python_version": python_version,
            "script_location": script_location,
            "additional_python_modules": additional_py_modules or "None",
            "extra_py_files": extra_py_files or "None",
            "extra_jars": extra_jars or "None",
            "default_arguments": default_args
        }


# =============================================================================
# 2. GROQ AI ANALYSIS CLIENT
# =============================================================================
class GlueAIAnalyzer:
    """Sends extracted Terraform Glue parameters to Groq AI and parses the structured response."""

    @classmethod
    async def analyze_job(
        cls,
        job: Dict[str, Any],
        grok_api_key: Optional[str] = None,
        use_grok: bool = False
    ) -> Dict[str, Any]:
        api_key = grok_api_key or os.getenv("GROQ_API_KEY")
        if not api_key:
            return {
                "job_name": job.get("job_name"),
                "file": job.get("filename"),
                "glue_version": job.get("glue_version"),
                "worker_type": job.get("worker_type"),
                "python_version": job.get("python_version"),
                "additional_python_modules": job.get("additional_python_modules"),
                "verdict": "ERROR",
                "inefficiency_score": 0,
                "ai_summary": "Missing GROQ_API_KEY. Please provide it in .env or the UI.",
                "packages_analysis": [],
                "groq_analysis": {"available": False, "error": "No API key provided"}
            }

        model = os.getenv("GROQ_MODEL") or DEFAULT_GROQ_MODEL

        prompt = f"""You are an AWS Glue and Python compatibility specialist with full knowledge of AWS Glue documentation and versions (1.0 to 5.0).
Analyze this AWS Glue Terraform Job configuration:

- Job Name: {job.get('job_name')}
- Terraform File: {job.get('filename')}
- Glue Version: {job.get('glue_version')}
- Declared Python Version: {job.get('python_version')}
- Worker Type: {job.get('worker_type')} ({job.get('number_of_workers')} workers)
- Additional Python Modules (--additional-python-modules): {job.get('additional_python_modules')}
- Extra Py Files: {job.get('extra_py_files')}

Evaluate compatibility issues (Python runtime incompatibilities, PyPI wheel build/GLIBC issues, worker memory constraints, deprecated worker types, package collisions).

Respond strictly in valid JSON matching this schema:
{{
  "incompatibility_percentage": <integer 0-100>,
  "verdict": "<HEALTHY | WARNINGS FOUND | ACTION REQUIRED - INCOMPATIBILITY DETECTED>",
  "executive_summary": "<Short executive summary paragraph>",
  "recommended_version": {{
    "glue_version": "<e.g. 5.0>",
    "python_version": "<e.g. 3.11>",
    "worker_type": "<e.g. G.1X or G.2X>",
    "rationale": "<Short reason why this version is best>"
  }},
  "packages_analysis": [
    {{
      "package": "<package_name>",
      "status": "<pass | fail | warning>",
      "what_is_issue": "<What is the issue>",
      "why_not_compatible": "<Why it is not compatible>",
      "why_suggested_version": "<Why the recommended Glue/Python version resolves this>",
      "error_if_proceed": "<Exact runtime error or crash if engineer proceeds as-is>"
    }}
  ]
}}
"""

        payload = {
            "model": model,
            "messages": [
                {
                    "role": "system",
                    "content": "You are an automated AWS Glue Terraform analyzer. Output strictly valid JSON matching the requested schema."
                },
                {"role": "user", "content": prompt}
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
                "User-Agent": "Glue-Compat-AI/1.0"
            },
            method="POST"
        )

        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                resp_data = json.loads(resp.read().decode("utf-8"))
                content = resp_data["choices"][0]["message"]["content"]
                parsed = json.loads(content)

                incompatibility = parsed.get("incompatibility_percentage", 0)
                recom = parsed.get("recommended_version", {})
                packages = parsed.get("packages_analysis", [])

                # Map packages to library_checks format for frontend compatibility
                library_checks = []
                for p in packages:
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
                    "worker_status": "compatible" if incompatibility < 50 else "warning",
                    "overall_compatible": incompatibility == 0,
                    "verdict": parsed.get("verdict", "ACTION REQUIRED - INCOMPATIBILITY DETECTED"),
                    "inefficiency_score": incompatibility,
                    "health_score": 100 - incompatibility,
                    "recommended_version": recom,
                    "ai_executive_summary": parsed.get("executive_summary", ""),
                    "library_checks": library_checks,
                    "groq_analysis": {"available": True, "analysis": parsed.get("executive_summary")}
                }
        except urllib.error.HTTPError as e:
            err_msg = e.read().decode("utf-8")
            return {
                "job_name": job.get("job_name"),
                "file": job.get("filename"),
                "verdict": "ERROR",
                "inefficiency_score": 0,
                "ai_executive_summary": f"Groq API HTTP Error {e.code}: {err_msg}",
                "library_checks": [],
                "groq_analysis": {"available": False, "error": err_msg}
            }
        except Exception as e:
            return {
                "job_name": job.get("job_name"),
                "file": job.get("filename"),
                "verdict": "ERROR",
                "inefficiency_score": 0,
                "ai_executive_summary": f"Failed to connect to Groq AI: {str(e)}",
                "library_checks": [],
                "groq_analysis": {"available": False, "error": str(e)}
            }
