"""
AI Analysis Engine for AWS Glue & Python Compatibility
Validates worker type, Glue version, Python version, cross-checks
all additional python library dependencies against PyPI and AWS specs,
computes Inefficiency Percentage, and recommends optimal Glue/Python versions.
Supports xAI Grok analysis integration.
"""
import httpx
from typing import Dict, Any, List, Optional
from packaging import version
from packaging.specifiers import SpecifierSet

try:
    from backend.glue_specs import GLUE_SPECS, KNOWN_PACKAGES_METADATA
    from backend.groq_service import GroqAnalysisService
except ImportError:
    from glue_specs import GLUE_SPECS, KNOWN_PACKAGES_METADATA
    from groq_service import GroqAnalysisService


class GlueAIAnalyzer:
    """Intelligent analyzer for Glue worker types, python compatibility, inefficiencies and recommendations."""

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
    async def analyze_job(
        cls,
        job: Dict[str, Any],
        grok_api_key: Optional[str] = None,
        use_grok: bool = False
    ) -> Dict[str, Any]:
        glue_ver = str(job.get("glue_version", "4.0")).strip()
        worker_type = str(job.get("worker_type", "G.1X")).strip().upper()

        # 1. Resolve Glue & Python Version based on worker type & glue version
        spec = GLUE_SPECS.get(glue_ver, GLUE_SPECS.get("4.0"))
        default_python = spec.get("default_python", "3.10")

        # Actual runtime python version determined:
        runtime_python = default_python
        declared_python = job.get("declared_python_version")
        if declared_python:
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
                lib_notes.append(
                    f"AWS Glue {glue_ver} already bundles '{pkg_name}=={builtin_ver}'. "
                    f"Overriding via --additional-python-modules can cause classpath or native ABI conflicts."
                )
                lib_status = "warning"

            # Check 2: Python Version Compatibility with Package via PyPI
            requires_python = pypi_data.get("requires_python")
            if requires_python:
                try:
                    spec_set = SpecifierSet(requires_python)
                    if not spec_set.contains(runtime_python):
                        lib_status = "fail"
                        overall_compatible = False
                        msg = (
                            f"Package '{pkg_name}' requires Python {requires_python}, which is "
                            f"INCOMPATIBLE with Glue {glue_ver}'s runtime Python {runtime_python}."
                        )
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
                        msg = f"'{pkg_name}' requires minimum Python {min_py}, but Glue {glue_ver} runs Python {runtime_python}."
                        lib_notes.append(msg)
                        if msg not in critical_issues:
                            critical_issues.append(msg)
                    if max_py and curr_v > version.parse(max_py):
                        lib_status = "fail"
                        overall_compatible = False
                        msg = f"'{pkg_name}' has maximum supported Python {max_py}, but Glue {glue_ver} runs {runtime_python}."
                        lib_notes.append(msg)
                        if msg not in critical_issues:
                            critical_issues.append(msg)
                except Exception:
                    pass

                if known_meta.get("c_extension"):
                    lib_notes.append("Contains native C/C++ compiled binaries. Wheels must match Amazon Linux OS architecture.")

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

        # 4. Calculate Inefficiency Score & Recommendation
        scoring = cls.calculate_inefficiency_score(
            glue_ver=glue_ver,
            worker_type=worker_type,
            worker_status=worker_status,
            critical_issues=critical_issues,
            worker_warnings=worker_warnings,
            lib_checks=lib_checks
        )

        recommended_version = cls.determine_recommended_glue_version(
            current_glue=glue_ver,
            lib_checks=lib_checks,
            critical_issues=critical_issues
        )

        # Generate AI Executive Summary
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
            lib_checks=lib_checks,
            scoring=scoring,
            recommendation=recommended_version
        )

        result = {
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
            "inefficiency_score": scoring["inefficiency_score"],
            "health_score": scoring["health_score"],
            "inefficiency_breakdown": scoring["breakdown"],
            "recommended_version": recommended_version,
            "ai_executive_summary": ai_summary,
            "grok_analysis": None
        }

        # 5. Optional Groq AI Analysis
        if use_grok or grok_api_key or os.getenv("GROQ_API_KEY"):
            groq_key = grok_api_key or os.getenv("GROQ_API_KEY")
            groq_metrics = {
                "inefficiency_score": scoring["inefficiency_score"],
                "health_score": scoring["health_score"],
                "critical_issues": critical_issues,
                "worker_warnings": worker_warnings,
                "recommended_glue_version": recommended_version["glue_version"],
                "recommended_python_version": recommended_version["python_version"]
            }
            groq_result = await GroqAnalysisService.analyze_with_groq(
                job_details=job,
                rule_based_metrics=groq_metrics,
                api_key=groq_key
            )
            result["grok_analysis"] = groq_result
            result["groq_analysis"] = groq_result

        return result

    @classmethod
    def calculate_inefficiency_score(
        cls,
        glue_ver: str,
        worker_type: str,
        worker_status: str,
        critical_issues: List[str],
        worker_warnings: List[str],
        lib_checks: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Calculates how much percentage the configuration is inefficient.
        Score ranges from 0% (Fully Optimal) to 100% (Critical Inefficiency / Breaking Failures).
        """
        inefficiency = 0
        breakdown = []

        # 1. Critical library version / runtime incompatibilities (up to 45%)
        failed_libs = [l for l in lib_checks if l.get("status") == "fail"]
        if failed_libs:
            penalty = min(len(failed_libs) * 25, 45)
            inefficiency += penalty
            breakdown.append(f"+{penalty}%: {len(failed_libs)} incompatible library package(s) detected for runtime Python.")

        # 2. Outdated / Deprecated Glue Version penalty (up to 25%)
        if glue_ver in ["1.0", "2.0"]:
            inefficiency += 25
            breakdown.append("+25%: Deprecated AWS Glue 1.0/2.0 runtime (End-of-Support / Python 3.6/3.7).")
        elif glue_ver == "3.0":
            inefficiency += 20
            breakdown.append("+20%: Legacy AWS Glue 3.0 (Python 3.7 runtime lacks modern wheels).")
        elif glue_ver == "4.0":
            inefficiency += 5
            breakdown.append("+5%: Glue 4.0 is stable, but Glue 5.0 offers faster Spark 3.5.2 & Python 3.11 optimizations.")

        # 3. Deprecated or Non-optimal Worker Type (up to 20%)
        if worker_status == "deprecated" or worker_type == "Standard":
            inefficiency += 20
            breakdown.append("+20%: Deprecated 'Standard' worker type causes slow executor allocation and poor cost efficiency.")
        elif worker_status == "warning":
            inefficiency += 10
            breakdown.append("+10%: Unrecognized worker type may trigger runtime fallback.")

        # 4. Heavy libraries on lightweight workers or bundle conflicts (up to 10%)
        warning_libs = [l for l in lib_checks if l.get("status") == "warning"]
        if warning_libs or worker_warnings:
            penalty = min(len(warning_libs) * 5 + len(worker_warnings) * 5, 10)
            inefficiency += penalty
            breakdown.append(f"+{penalty}%: Bundle collisions or memory pressure advisories.")

        inefficiency = min(max(inefficiency, 0), 100)
        health = 100 - inefficiency

        return {
            "inefficiency_score": inefficiency,
            "health_score": health,
            "breakdown": breakdown
        }

    @classmethod
    def determine_recommended_glue_version(
        cls,
        current_glue: str,
        lib_checks: List[Dict[str, Any]],
        critical_issues: List[str]
    ) -> Dict[str, Any]:
        """
        Recommends the most compatible AWS Glue & Python version based on
        current libraries, modern Spark features, and worker performance.
        """
        # Default modern target: Glue 5.0 with Python 3.11
        recommended_glue = "5.0"
        recommended_python = "3.11"
        spark_version = "Spark 3.5.2"
        worker_rec = "G.1X"
        rationale = []

        # Check if any required package does NOT support Python 3.11
        requires_older = False
        for lib in lib_checks:
            pkg = lib.get("package")
            meta = KNOWN_PACKAGES_METADATA.get(pkg, {})
            max_py = meta.get("max_py")
            if max_py and version.parse(max_py) < version.parse("3.11"):
                requires_older = True
                rationale.append(f"Package '{pkg}' max supported Python is {max_py}; caps version below Python 3.11.")

        if requires_older:
            recommended_glue = "4.0"
            recommended_python = "3.10"
            spark_version = "Spark 3.3.0"
            rationale.append("AWS Glue 4.0 (Python 3.10) is the optimal compatible target.")
        else:
            rationale.append("AWS Glue 5.0 (Python 3.11 / Spark 3.5.2) offers modern PyPI wheels, dynamic worker allocation, and 2-3x faster parquet reads.")

        if current_glue in ["1.0", "2.0", "3.0"]:
            rationale.append(f"Migrating from Glue {current_glue} will resolve End-of-Life Python 3.7 runtime constraints and allow modern packaging.")

        return {
            "glue_version": recommended_glue,
            "python_version": recommended_python,
            "spark_version": spark_version,
            "worker_type": worker_rec,
            "rationale": rationale,
            "upgrade_benefit": "35-50% faster ETL execution and full compatibility with modern Python wheels."
        }

    @staticmethod
    def _generate_ai_summary(
        job_name,
        glue_ver,
        worker_type,
        runtime_python,
        verdict,
        critical_issues,
        worker_warnings,
        lib_checks,
        scoring,
        recommendation
    ) -> str:
        points = [
            f"**Glue Job**: `{job_name}` configured with **AWS Glue {glue_ver}** and **{worker_type}** worker type.",
            f"**Runtime Python**: `{runtime_python}` | **Inefficiency Rating**: **{scoring['inefficiency_score']}% Inefficient** (Health: {scoring['health_score']}%)",
            f"**Status Verdict**: **{verdict}**",
            f"\n🎯 **Recommended Target**: **AWS Glue {recommendation['glue_version']} (Python {recommendation['python_version']})** with worker `{recommendation['worker_type']}`."
        ]

        if scoring["breakdown"]:
            points.append("\n**📉 Inefficiency Drivers:**")
            for b in scoring["breakdown"]:
                points.append(f"- {b}")

        if critical_issues:
            points.append("\n**🚨 Critical Conflicts:**")
            for ci in critical_issues:
                points.append(f"- {ci}")

        if worker_warnings:
            points.append("\n**⚠️ Worker / Infrastructure Advisories:**")
            for ww in worker_warnings:
                points.append(f"- {ww}")

        if recommendation["rationale"]:
            points.append("\n**💡 Recommendation Rationale:**")
            for r in recommendation["rationale"]:
                points.append(f"- {r}")

        return "\n".join(points)
