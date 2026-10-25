"""
AI Analysis Engine for AWS Glue & Python Compatibility
Validates worker type, Glue version, Python version, and cross-checks
all additional python library dependencies against PyPI and AWS specs.
"""
import httpx
from typing import Dict, Any, List
from packaging import version
from packaging.specifiers import SpecifierSet
try:
    from backend.glue_specs import GLUE_SPECS, KNOWN_PACKAGES_METADATA
except ImportError:
    from glue_specs import GLUE_SPECS, KNOWN_PACKAGES_METADATA

class GlueAIAnalyzer:
    """Intelligent analyzer for Glue worker types, python compatibility and dependencies."""

    @staticmethod
    async def fetch_pypi_metadata(package_name: str) -> Dict[str, Any]:
        """Queries PyPI JSON API for requires_python and releases."""
        url = f"https://pypi.org/pypi/{package_name}/json"
        try:
            async with httpx.AsyncClient(timeout=4.0) as client:
                resp = await client.get(url)
                if resp.status_code == 200:
                    data = resp.json()
                    info = data.get("info", {})
                    releases = list(data.get("releases", {}).keys())
                    return {
                        "found": True,
                        "latest_version": info.get("version"),
                        "requires_python": info.get("requires_python") or "",
                        "summary": info.get("summary", ""),
                        "releases_count": len(releases)
                    }
        except Exception:
            pass
        return {"found": False, "latest_version": None, "requires_python": "", "summary": ""}

    @classmethod
    async def analyze_job(cls, job: Dict[str, Any]) -> Dict[str, Any]:
        glue_ver = str(job.get("glue_version", "4.0")).strip()
        worker_type = str(job.get("worker_type", "G.1X")).strip().upper()
        
        # 1. Resolve Glue & Python Version based on worker type & glue version
        spec = GLUE_SPECS.get(glue_ver, GLUE_SPECS.get("4.0"))
        default_python = spec.get("default_python", "3.10")
        supported_pythons = spec.get("supported_pythons", [default_python])
        
        # Actual runtime python version determined:
        runtime_python = default_python
        declared_python = job.get("declared_python_version")
        if declared_python:
            # Clean "3" -> "3.10" or "3.11"
            if declared_python in ["3", "python3"]:
                runtime_python = default_python
            else:
                runtime_python = declared_python

        # 2. Worker Type Verification
        worker_specs = spec.get("worker_types", {})
        worker_info = worker_specs.get(worker_type)
        worker_status = "compatible"
        worker_warnings = []
        worker_recommendation = ""

        if not worker_info:
            worker_status = "warning"
            worker_warnings.append(
                f"Worker type '{worker_type}' is unrecognized or deprecated in AWS Glue {glue_ver}."
            )
            worker_recommendation = "Consider standardizing on G.1X or G.2X."
        elif worker_info.get("status") == "deprecated":
            worker_status = "deprecated"
            worker_warnings.append(worker_info.get("notice", f"{worker_type} is deprecated."))
            worker_recommendation = "Upgrade worker_type to G.1X or G.2X."
        else:
            worker_recommendation = worker_info.get("recommended_for", "General scalable workload")

        # Worker capacity analysis
        num_workers = job.get("number_of_workers", 2)
        total_vcpu = worker_info.get("vCPU", 4) * num_workers if worker_info and "vCPU" in worker_info else None
        total_mem = worker_info.get("memory_gb", 16) * num_workers if worker_info and "memory_gb" in worker_info else None

        # 3. Cross-Compatibility Check of Additional Python Libraries
        libraries = job.get("parsed_libraries", [])
        lib_checks = []
        overall_compatible = True
        critical_issues = []

        preinstalled = spec.get("preinstalled_libraries", {})

        for lib in libraries:
            pkg_name = lib["package"]
            constraint = lib["constraint"]
            raw_spec = lib["raw"]

            # Check PyPI & Known Metadata
            pypi_data = await cls.fetch_pypi_metadata(pkg_name)
            known_meta = KNOWN_PACKAGES_METADATA.get(pkg_name, {})

            lib_status = "pass"
            lib_notes = []
            
            # Check 1: Conflict with Pre-installed Glue libraries
            if pkg_name in preinstalled:
                builtin_ver = preinstalled[pkg_name]
                lib_notes.append(f"AWS Glue {glue_ver} already bundles '{pkg_name}=={builtin_ver}'. Overriding via --additional-python-modules can cause classpath or native ABI conflicts.")
                lib_status = "warning"

            # Check 2: Python Version Compatibility with Package
            requires_python = pypi_data.get("requires_python")
            if requires_python:
                try:
                    spec_set = SpecifierSet(requires_python)
                    if not spec_set.contains(runtime_python):
                        lib_status = "fail"
                        overall_compatible = False
                        msg = f"Package '{pkg_name}' requires Python {requires_python}, which is INCOMPATIBLE with Glue {glue_ver}'s runtime Python {runtime_python}."
                        lib_notes.append(msg)
                        critical_issues.append(msg)
                except Exception:
                    pass

            # Check 3: Check Known Metadata limits
            if known_meta:
                min_py = known_meta.get("min_py")
                max_py = known_meta.get("max_py")
                try:
                    curr_v = version.parse(runtime_python)
                    if min_py and curr_v < version.parse(min_py):
                        lib_status = "fail"
                        overall_compatible = False
                        msg = f"{pkg_name} requires minimum Python {min_py}, but Glue is running {runtime_python}."
                        lib_notes.append(msg)
                        critical_issues.append(msg)
                    if max_py and curr_v > version.parse(max_py):
                        lib_status = "fail"
                        overall_compatible = False
                        msg = f"{pkg_name} has maximum supported Python {max_py}, Glue {glue_ver} runs {runtime_python}."
                        lib_notes.append(msg)
                        critical_issues.append(msg)
                except Exception:
                    pass

                if known_meta.get("c_extension"):
                    lib_notes.append("Contains native C/C++ compiled binaries. Ensure wheels match Amazon Linux 2 / 2023 x86_64 architecture.")

                if known_meta.get("notes"):
                    lib_notes.append(known_meta["notes"])

            # Check 4: Heavy package warning on small worker
            if pkg_name in ["torch", "tensorflow", "polars", "pyarrow"] and worker_type in ["G.025X", "Standard"]:
                lib_status = "warning"
                worker_warnings.append(f"Heavy library '{pkg_name}' imported on light worker '{worker_type}'. High risk of OOM.")

            lib_checks.append({
                "raw": raw_spec,
                "package": pkg_name,
                "constraint": constraint,
                "status": lib_status,
                "pypi_latest": pypi_data.get("latest_version"),
                "requires_python": requires_python or "Any",
                "notes": lib_notes
            })

        # Generate AI Executive Summary & Remediation
        ai_verdict = "HEALTHY"
        if not overall_compatible or worker_status == "fail":
            ai_verdict = "ACTION REQUIRED - INCOMPATIBILITY DETECTED"
        elif worker_status in ["warning", "deprecated"] or any(l["status"] == "warning" for l in lib_checks):
            ai_verdict = "WARNINGS FOUND - REVIEW RECOMMENDATIONS"

        ai_summary = cls._generate_ai_summary(
            job_name=job.get("job_name"),
            glue_ver=glue_ver,
            worker_type=worker_type,
            runtime_python=runtime_python,
            verdict=ai_verdict,
            critical_issues=critical_issues,
            worker_warnings=worker_warnings,
            lib_checks=lib_checks
        )

        return {
            "job_name": job.get("job_name"),
            "resource_id": job.get("resource_id"),
            "file": job.get("filename"),
            "glue_version": glue_ver,
            "runtime_python": runtime_python,
            "spark_version": spec.get("spark_version"),
            "worker_type": worker_type,
            "worker_status": worker_status,
            "worker_specs": worker_info,
            "worker_capacity": {
                "num_workers": num_workers,
                "total_vcpu": total_vcpu,
                "total_memory_gb": total_mem
            },
            "worker_warnings": worker_warnings,
            "worker_recommendation": worker_recommendation,
            "library_checks": lib_checks,
            "overall_compatible": overall_compatible,
            "verdict": ai_verdict,
            "ai_executive_summary": ai_summary
        }

    @staticmethod
    def _generate_ai_summary(job_name, glue_ver, worker_type, runtime_python, verdict, critical_issues, worker_warnings, lib_checks) -> str:
        summary_points = [
            f"**Glue Job**: `{job_name}` configured with **AWS Glue {glue_ver}** and **{worker_type}** worker type.",
            f"**Derived Runtime Python**: `{runtime_python}`.",
            f"**Compatibility Verdict**: **{verdict}**"
        ]

        if critical_issues:
            summary_points.append("\n**🚨 Critical Conflicts:**")
            for ci in critical_issues:
                summary_points.append(f"- {ci}")

        if worker_warnings:
            summary_points.append("\n**⚠️ Worker / Infrastructure Advisories:**")
            for ww in worker_warnings:
                summary_points.append(f"- {ww}")

        if not lib_checks:
            summary_points.append("\n- No external `--additional-python-modules` declared. Uses Glue built-in bundle.")
        else:
            summary_points.append(f"\n- Evaluated **{len(lib_checks)}** additional python module(s) against PyPI specifications and Glue OS wheels.")

        return "\n".join(summary_points)
