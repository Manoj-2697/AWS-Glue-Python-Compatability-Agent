"""
Groq AI Service Integration for Deep Glue & Python Compatibility Analysis
Uses Groq API (https://api.groq.com/openai/v1/chat/completions) with OpenAI-compatible chat completions.
"""
import os
import json
import urllib.request
import urllib.error
from typing import Dict, Any, Optional

GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
DEFAULT_GROQ_MODEL = "llama-3.3-70b-versatile"


class GroqAnalysisService:
    """Invokes Groq LLM for architectural, compatibility, and efficiency scoring analysis."""

    @classmethod
    async def analyze_with_groq(
        cls,
        job_details: Dict[str, Any],
        rule_based_metrics: Dict[str, Any],
        api_key: Optional[str] = None,
        model: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Sends Glue Job specification and compatibility findings to Groq AI.
        Returns AI reasoning, incompatibility percentage, why reason, and recommendations.
        """
        key = api_key or os.getenv("GROQ_API_KEY") or os.getenv("GROK_API_KEY")
        if not key:
            return {
                "available": False,
                "error": "No Groq API Key configured. Set GROQ_API_KEY in .env or provide it in the UI.",
                "analysis": None
            }

        selected_model = model or os.getenv("GROQ_MODEL") or DEFAULT_GROQ_MODEL

        system_prompt = (
            "You are an expert AWS Cloud Infrastructure and Big Data Architect specializing in AWS Glue, "
            "PySpark, worker types, and Python packaging runtimes. "
            "Analyze the provided AWS Glue job configuration from Terraform and the rule-based compatibility findings. "
            "Provide insightful, high-value advice on why it is inefficient, pinpoint Python version / wheel conflicts, "
            "and suggest optimal Glue & Python version migrations with specific adjustments."
        )

        user_content = f"""
Terraform Glue Job Name: {job_details.get('job_name')}
Terraform File: {job_details.get('filename', job_details.get('file', 'main.tf'))}
Configured Glue Version: {job_details.get('glue_version')}
Runtime Python Version: {job_details.get('declared_python_version') or job_details.get('runtime_python', 'Default')}
Worker Type: {job_details.get('worker_type')} ({job_details.get('number_of_workers', 2)} workers)
Additional Python Modules: {job_details.get('additional_python_modules_raw') or job_details.get('default_arguments', {}).get('--additional-python-modules', 'None')}

Rule-Based Compatibility Findings:
- Inefficiency Score: {rule_based_metrics.get('inefficiency_score', 0)}%
- Health Score: {rule_based_metrics.get('health_score', 100)}%
- Critical Conflicts: {rule_based_metrics.get('critical_issues', [])}
- Worker Advisories: {rule_based_metrics.get('worker_warnings', [])}
- Recommended Version: {rule_based_metrics.get('recommended_glue_version')} (Python {rule_based_metrics.get('recommended_python_version')})

Please provide:
1. Executive Architectural Assessment & Incompatibility Reason (Why this setup fails or is suboptimal).
2. Deep Dive on Python Compatibility & Packaging Conflicts (PyPI requirements, C-extensions, Amazon Linux wheel issues).
3. Groq's Recommended Best Version & Configurations (Glue version, Python runtime, worker type, and package specs).
4. Immediate Remediation Action Steps.
"""

        payload = {
            "model": selected_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content}
            ],
            "temperature": 0.2,
            "max_tokens": 1200
        }

        req = urllib.request.Request(
            GROQ_API_URL,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {key.strip()}",
                "Content-Type": "application/json",
                "User-Agent": "Glue-Compat-Groq-Agent/1.0"
            },
            method="POST"
        )

        try:
            # Run synchronously using standard library urllib to avoid httpx version discrepancies
            with urllib.request.urlopen(req, timeout=30) as resp:
                resp_data = json.loads(resp.read().decode("utf-8"))
                ai_text = resp_data.get("choices", [{}])[0].get("message", {}).get("content", "")
                return {
                    "available": True,
                    "model": selected_model,
                    "analysis": ai_text,
                    "error": None
                }
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8")
            return {
                "available": False,
                "error": f"Groq API returned HTTP {e.code}: {err_body}",
                "analysis": None
            }
        except Exception as e:
            return {
                "available": False,
                "error": f"Failed to connect to Groq API: {str(e)}",
                "analysis": None
            }
