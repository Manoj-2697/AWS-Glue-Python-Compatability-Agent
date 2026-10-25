"""
Web Application Server for AWS Glue AI Analyzer
Hosts the FastAPI REST API, handles routes, and serves the static frontend.
"""
import os
import sys
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from dotenv import load_dotenv

# Load .env
load_dotenv()

# Path configuration
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

from backend.github_auth import GitHubService
from backend.ai_analyzer import TerraformGlueParser, GlueAIAnalyzer

app = FastAPI(
    title="AWS Glue Terraform AI Analyzer API",
    description="Intelligent Analyzer for AWS Glue Terraform Code, Worker Types, Python Versions & Cross-Package Compatibility",
    version="2.0.0"
)

# CORS Middleware
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

class GroqSingleAnalysisRequest(BaseModel):
    job: Dict[str, Any]
    grok_api_key: Optional[str] = None


# Endpoints
@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "service": "AWS Glue Terraform AI Engine",
        "groq_configured": bool(os.getenv("GROQ_API_KEY"))
    }

@app.get("/api/specs")
def get_glue_specs():
    return GLUE_SPECS

@app.post("/api/github/authenticate")
async def github_authenticate(req: GitHubAuthRequest):
    token = req.token.strip()
    if not token:
        raise HTTPException(status_code=400, detail="Personal Access Token cannot be empty")
    
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
async def get_repositories(token: Optional[str] = None):
    if not token:
        raise HTTPException(status_code=400, detail="Missing GitHub token")
    gh = GitHubService(token)
    try:
        repos = await gh.list_repositories()
        return {"source": "live_github", "repositories": repos}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/analyze/repository")
async def analyze_repository(req: RepoAnalysisRequest):
    owner = req.owner
    repo = req.repo
    token = req.token
    groq_key = req.grok_api_key or os.getenv("GROQ_API_KEY")
    use_groq = bool(req.use_grok or groq_key)

    if not token:
        raise HTTPException(status_code=400, detail="GitHub Token is required to scan repository")

    scanned_files = []
    discovered_jobs = []

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
            "message": "No 'aws_glue_job' resources found in scanned Terraform files."
        }

    analyzed_jobs = []
    for job in discovered_jobs:
        analysis_result = await GlueAIAnalyzer.analyze_job(
            job=job,
            grok_api_key=groq_key,
            use_grok=use_groq
        )
        analyzed_jobs.append(analysis_result)

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
    content = req.hcl_content
    filename = req.filename or "pasted_main.tf"
    jobs = TerraformGlueParser.extract_glue_jobs(content, filename=filename)

    if not jobs:
        return {
            "glue_jobs_count": 0,
            "jobs_analysis": [],
            "message": "No 'aws_glue_job' blocks found in provided HCL."
        }

    groq_key = req.grok_api_key or os.getenv("GROQ_API_KEY")
    use_groq = bool(req.use_grok or groq_key)

    analyzed_jobs = []
    for job in jobs:
        result = await GlueAIAnalyzer.analyze_job(
            job=job,
            grok_api_key=groq_key,
            use_grok=use_groq
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
async def analyze_with_groq_endpoint(req: GroqSingleAnalysisRequest):
    groq_key = req.grok_api_key or os.getenv("GROQ_API_KEY")
    result = await GlueAIAnalyzer.analyze_job(
        job=req.job,
        grok_api_key=groq_key,
        use_grok=True
    )
    return result

# Mount static frontend directory
frontend_dir = os.path.join(os.path.dirname(__file__), "..", "frontend")
if os.path.exists(frontend_dir):
    app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.web_app:app", host="127.0.0.1", port=8000, reload=True)
