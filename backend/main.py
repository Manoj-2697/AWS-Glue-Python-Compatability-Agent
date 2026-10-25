"""
FastAPI Server for AWS Glue Terraform AI Analyzer
Provides endpoints for GitHub authentication, repository listing,
Terraform scanning, and intelligent Glue & Python compatibility analysis
with Grok (xAI) LLM integration and inefficiency scoring.
"""
from fastapi import FastAPI, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import os
import sys
from dotenv import load_dotenv

# Load .env variables if present
load_dotenv()

# Ensure parent directory is in sys.path so backend package imports work
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

try:
    from backend.glue_specs import GLUE_SPECS
    from backend.tf_parser import TerraformGlueParser
    from backend.analyzer import GlueAIAnalyzer
    from backend.github_service import GitHubService
    from backend.groq_service import GroqAnalysisService
    from backend.sample_data import SAMPLE_REPOSITORIES, SAMPLE_GLUE_TERRAFORM
except ImportError:
    from glue_specs import GLUE_SPECS
    from tf_parser import TerraformGlueParser
    from analyzer import GlueAIAnalyzer
    from github_service import GitHubService
    from groq_service import GroqAnalysisService
    from sample_data import SAMPLE_REPOSITORIES, SAMPLE_GLUE_TERRAFORM

app = FastAPI(
    title="AWS Glue Terraform AI Analyzer API",
    description="Intelligent Analyzer for AWS Glue Terraform Code, Worker Types, Python Version & Cross-Package Compatibility with Grok AI",
    version="2.0.0"
)

# Enable CORS for local and web client integration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Request Models
class GitHubAuthRequest(BaseModel):
    token: str

class RepoAnalysisRequest(BaseModel):
    owner: str
    repo: str
    default_branch: Optional[str] = "main"
    token: Optional[str] = None
    is_demo: Optional[bool] = False
    grok_api_key: Optional[str] = None
    use_grok: Optional[bool] = False

class DirectHclAnalysisRequest(BaseModel):
    hcl_content: str
    filename: Optional[str] = "main.tf"
    grok_api_key: Optional[str] = None
    use_grok: Optional[bool] = False

class GrokSingleAnalysisRequest(BaseModel):
    job: Dict[str, Any]
    grok_api_key: Optional[str] = None

# Endpoints
@app.get("/api/health")
def health():
    grok_configured = bool(os.getenv("GROK_API_KEY") or os.getenv("XAI_API_KEY"))
    return {
        "status": "ok",
        "service": "AWS Glue Terraform AI Engine",
        "engine": "FastAPI + Python 3.12",
        "grok_configured": grok_configured
    }

@app.get("/api/specs")
def get_glue_specs():
    """Returns official AWS Glue versions, worker specifications, and pre-installed dependencies."""
    return GLUE_SPECS

@app.post("/api/github/authenticate")
async def github_authenticate(req: GitHubAuthRequest):
    """Verifies GitHub token connectivity and fetches user details."""
    token = req.token.strip()
    if not token:
        raise HTTPException(status_code=400, detail="Personal Access Token cannot be empty")
    
    # Check for demo mode trigger
    if token.lower() in ["demo", "demo-token", "test"]:
        return {
            "authenticated": True,
            "demo_mode": True,
            "user": {
                "login": "octocat-devops",
                "name": "OctoCat Cloud Architect",
                "avatar_url": "https://avatars.githubusercontent.com/u/583231?v=4",
                "public_repos": 14,
                "total_private_repos": 8,
                "html_url": "https://github.com/octocat"
            }
        }

    gh = GitHubService(token)
    profile = await gh.verify_user()
    if not profile.get("valid"):
        raise HTTPException(status_code=401, detail=profile.get("error", "Authentication failed"))
    
    return {
        "authenticated": True,
        "demo_mode": False,
        "user": profile
    }

@app.get("/api/github/repositories")
async def get_repositories(token: Optional[str] = None, demo: Optional[bool] = False):
    """Lists repositories accessible to the token or returns demo repositories."""
    if demo or not token or token.lower() in ["demo", "demo-token", "test"]:
        return {
            "source": "demo_environment",
            "repositories": [
                {
                    "id": r["id"],
                    "name": r["name"],
                    "full_name": r["full_name"],
                    "owner": r["owner"],
                    "private": r["private"],
                    "description": r["description"],
                    "default_branch": r["default_branch"],
                    "updated_at": r["updated_at"],
                    "language": r["language"]
                }
                for r in SAMPLE_REPOSITORIES
            ]
        }

    gh = GitHubService(token)
    try:
        repos = await gh.list_repositories()
        return {"source": "live_github", "repositories": repos}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/analyze/repository")
async def analyze_repository(req: RepoAnalysisRequest):
    """
    Connects to GitHub repository, discovers all .tf files, extracts aws_glue_job
    resources, and runs AI Cross-Compatibility, inefficiency scoring & recommendations.
    """
    owner = req.owner
    repo = req.repo
    token = req.token
    is_demo = req.is_demo or (token and token.lower() in ["demo", "demo-token", "test"]) or not token
    grok_key = req.grok_api_key or os.getenv("GROK_API_KEY")
    use_grok = bool(req.use_grok or grok_key)

    scanned_files = []
    discovered_jobs = []

    if is_demo:
        # Match from demo database
        matching_repo = next((r for r in SAMPLE_REPOSITORIES if r["name"] == repo or r["full_name"] == f"{owner}/{repo}"), None)
        if not matching_repo:
            matching_repo = SAMPLE_REPOSITORIES[0]
        
        sample_files = matching_repo.get("sample_files", {"main.tf": SAMPLE_GLUE_TERRAFORM})
        for fpath, fcontent in sample_files.items():
            scanned_files.append({"path": fpath, "size": len(fcontent)})
            jobs = TerraformGlueParser.extract_glue_jobs(fcontent, filename=fpath)
            discovered_jobs.extend(jobs)
    else:
        gh = GitHubService(token)
        try:
            tf_files = await gh.find_terraform_files(owner, repo, req.default_branch or "main")
            for file_info in tf_files:
                fpath = file_info["path"]
                scanned_files.append({"path": fpath, "size": file_info.get("size", 0)})
                fcontent = await gh.get_file_content(owner, repo, fpath)
                jobs = TerraformGlueParser.extract_glue_jobs(fcontent, filename=fpath)
                discovered_jobs.extend(jobs)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error reading repository files: {str(e)}")

    if not discovered_jobs:
        return {
            "repository": f"{owner}/{repo}",
            "scanned_tf_files_count": len(scanned_files),
            "scanned_files": scanned_files,
            "glue_jobs_count": 0,
            "jobs_analysis": [],
            "message": "No 'aws_glue_job' resources found in the scanned Terraform files."
        }

    # Run AI Analysis for each detected Glue Job
    analyzed_jobs = []
    for job in discovered_jobs:
        analysis_result = await GlueAIAnalyzer.analyze_job(
            job=job,
            grok_api_key=grok_key,
            use_grok=use_grok
        )
        analyzed_jobs.append(analysis_result)

    # Compute overall repo health summary and average inefficiency
    total_jobs = len(analyzed_jobs)
    healthy_count = sum(1 for j in analyzed_jobs if j["verdict"] == "HEALTHY")
    warning_count = sum(1 for j in analyzed_jobs if "WARNINGS" in j["verdict"])
    action_required_count = sum(1 for j in analyzed_jobs if "ACTION REQUIRED" in j["verdict"])
    avg_inefficiency = round(sum(j["inefficiency_score"] for j in analyzed_jobs) / total_jobs, 1) if total_jobs > 0 else 0

    return {
        "repository": f"{owner}/{repo}",
        "scanned_tf_files_count": len(scanned_files),
        "scanned_files": scanned_files,
        "glue_jobs_count": total_jobs,
        "summary": {
            "total_jobs": total_jobs,
            "healthy": healthy_count,
            "warnings": warning_count,
            "action_required": action_required_count,
            "average_inefficiency_score": avg_inefficiency
        },
        "jobs_analysis": analyzed_jobs
    }

@app.post("/api/analyze/direct-hcl")
async def analyze_direct_hcl(req: DirectHclAnalysisRequest):
    """Allows instant direct pasting and analysis of Terraform Glue HCL code."""
    content = req.hcl_content
    filename = req.filename or "pasted_main.tf"
    jobs = TerraformGlueParser.extract_glue_jobs(content, filename=filename)

    if not jobs:
        return {
            "glue_jobs_count": 0,
            "jobs_analysis": [],
            "message": "No 'aws_glue_job' blocks found in provided HCL."
        }

    grok_key = req.grok_api_key or os.getenv("GROK_API_KEY")
    use_grok = bool(req.use_grok or grok_key)

    analyzed_jobs = []
    for job in jobs:
        result = await GlueAIAnalyzer.analyze_job(
            job=job,
            grok_api_key=grok_key,
            use_grok=use_grok
        )
        analyzed_jobs.append(result)

    total_jobs = len(analyzed_jobs)
    avg_inefficiency = round(sum(j["inefficiency_score"] for j in analyzed_jobs) / total_jobs, 1) if total_jobs > 0 else 0

    return {
        "glue_jobs_count": len(analyzed_jobs),
        "average_inefficiency_score": avg_inefficiency,
        "jobs_analysis": analyzed_jobs
    }

@app.post("/api/analyze/groq")
@app.post("/api/analyze/grok")
async def analyze_with_groq_endpoint(req: GrokSingleAnalysisRequest):
    """Directly triggers Groq AI reasoning for a single analyzed Glue job."""
    groq_key = req.grok_api_key or os.getenv("GROQ_API_KEY") or os.getenv("GROK_API_KEY")
    if not groq_key:
        raise HTTPException(
            status_code=400,
            detail="Groq API Key is required. Please provide it in the request or configure GROQ_API_KEY in .env."
        )

    job = req.job
    rule_metrics = {
        "inefficiency_score": job.get("inefficiency_score", 0),
        "health_score": job.get("health_score", 100),
        "critical_issues": [c["notes"] for c in job.get("library_checks", []) if c.get("status") == "fail"],
        "worker_warnings": job.get("worker_warnings", []),
        "recommended_glue_version": job.get("recommended_version", {}).get("glue_version", "5.0"),
        "recommended_python_version": job.get("recommended_version", {}).get("python_version", "3.11")
    }

    result = await GroqAnalysisService.analyze_with_groq(
        job_details=job,
        rule_based_metrics=rule_metrics,
        api_key=groq_key
    )

    if not result.get("available"):
        raise HTTPException(status_code=502, detail=result.get("error", "Groq API call failed"))

    return result

# Mount static frontend directory
frontend_dir = os.path.join(os.path.dirname(__file__), "..", "frontend")
if os.path.exists(frontend_dir):
    app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host="127.0.0.1", port=8000, reload=True)
