"""
GitHub API integration service for authentication, repository listing,
and recursive scanning of Terraform (.tf) files.
"""
import httpx
from typing import List, Dict, Any, Optional

class GitHubService:
    def __init__(self, token: str):
        self.token = token.strip()
        self.headers = {
            "Accept": "application/vnd.github.v3+json",
            "Authorization": f"token {self.token}",
            "User-Agent": "AWS-Glue-Terraform-AI-Analyzer"
        }

    async def verify_user(self) -> Dict[str, Any]:
        """Validates token and returns current authenticated user profile."""
        url = "https://api.github.com/user"
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, headers=self.headers)
            if resp.status_code == 200:
                data = resp.json()
                return {
                    "valid": True,
                    "login": data.get("login"),
                    "name": data.get("name") or data.get("login"),
                    "avatar_url": data.get("avatar_url"),
                    "public_repos": data.get("public_repos"),
                    "total_private_repos": data.get("total_private_repos", 0),
                    "html_url": data.get("html_url")
                }
            else:
                return {
                    "valid": False,
                    "error": f"GitHub returned status {resp.status_code}: {resp.text}"
                }

    async def list_repositories(self, per_page: int = 100) -> List[Dict[str, Any]]:
        """Lists repositories accessible to the user (owned, org, collaborations)."""
        url = "https://api.github.com/user/repos"
        params = {
            "per_page": per_page,
            "sort": "updated",
            "affiliation": "owner,collaborator,organization_member"
        }
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(url, headers=self.headers, params=params)
            if resp.status_code == 200:
                repos = resp.json()
                return [
                    {
                        "id": r["id"],
                        "name": r["name"],
                        "full_name": r["full_name"],
                        "owner": r["owner"]["login"],
                        "private": r["private"],
                        "description": r.get("description"),
                        "default_branch": r.get("default_branch", "main"),
                        "updated_at": r.get("updated_at"),
                        "html_url": r.get("html_url"),
                        "language": r.get("language")
                    }
                    for r in repos
                ]
            else:
                raise Exception(f"Failed to fetch repositories: {resp.text}")

    async def find_terraform_files(self, owner: str, repo: str, default_branch: str = "main") -> List[Dict[str, Any]]:
        """Fetches Git Tree recursively to locate all .tf files in the repository."""
        # 1. Get branch commit sha to retrieve tree
        url = f"https://api.github.com/repos/{owner}/{repo}/git/trees/{default_branch}?recursive=1"
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.get(url, headers=self.headers)
            if resp.status_code != 200:
                # Try master if main failed
                if default_branch == "main":
                    url_master = f"https://api.github.com/repos/{owner}/{repo}/git/trees/master?recursive=1"
                    resp = await client.get(url_master, headers=self.headers)
                
                if resp.status_code != 200:
                    raise Exception(f"Failed to load repository tree: {resp.text}")

            data = resp.json()
            tree = data.get("tree", [])
            tf_files = []
            for item in tree:
                path = item.get("path", "")
                if item.get("type") == "blob" and path.endswith(".tf"):
                    tf_files.append({
                        "path": path,
                        "sha": item.get("sha"),
                        "size": item.get("size")
                    })
            return tf_files

    async def get_file_content(self, owner: str, repo: str, path: str) -> str:
        """Downloads raw file content for a given path."""
        url = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}"
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(url, headers=self.headers)
            if resp.status_code == 200:
                data = resp.json()
                import base64
                if data.get("encoding") == "base64" and data.get("content"):
                    return base64.b64decode(data["content"]).decode("utf-8", errors="replace")
                else:
                    download_url = data.get("download_url")
                    if download_url:
                        dl_resp = await client.get(download_url)
                        return dl_resp.text
            raise Exception(f"Could not read {path}: HTTP {resp.status_code}")
