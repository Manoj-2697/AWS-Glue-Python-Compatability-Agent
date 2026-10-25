"""
Parser for Terraform HCL code to extract AWS Glue resources and arguments.
Supports aws_glue_job, aws_glue_catalog_database, etc., focusing on glue jobs.
"""
import re
from typing import List, Dict, Any, Optional

class TerraformGlueParser:
    """Parses Terraform HCL content to discover aws_glue_job blocks and arguments."""

    @staticmethod
    def extract_glue_jobs(content: str, filename: str = "") -> List[Dict[str, Any]]:
        jobs = []
        # Pattern to find resource "aws_glue_job" "identifier" { ... }
        resource_pattern = re.compile(
            r'resource\s+"aws_glue_job"\s+"([^"]+)"\s*\{(.*?)\n\}',
            re.DOTALL
        )

        # For nested blocks we can match accurately using brace depth tracking
        for match in re.finditer(r'resource\s+"aws_glue_job"\s+"([^"]+)"\s*\{', content):
            resource_name = match.group(1)
            start_index = match.end() - 1  # at the opening brace
            
            # Find matching closing brace
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
                job_data = TerraformGlueParser._parse_job_block(resource_name, block_content, filename)
                jobs.append(job_data)

        return jobs

    @staticmethod
    def _parse_job_block(res_id: str, body: str, filename: str) -> Dict[str, Any]:
        # Extract job name
        name_match = re.search(r'name\s*=\s*["\']([^"\']+)["\']', body)
        job_name = name_match.group(1) if name_match else res_id

        # Extract glue_version
        glue_ver_match = re.search(r'glue_version\s*=\s*["\']([^"\']+)["\']', body)
        glue_version = glue_ver_match.group(1) if glue_ver_match else "4.0" # Default AWS fallback

        # Extract worker_type
        worker_match = re.search(r'worker_type\s*=\s*["\']([^"\']+)["\']', body)
        worker_type = worker_match.group(1) if worker_match else "G.1X"

        # Extract number_of_workers
        workers_count_match = re.search(r'number_of_workers\s*=\s*([0-9]+)', body)
        number_of_workers = int(workers_count_match.group(1)) if workers_count_match else 2

        # Extract python_version from command block if present
        command_match = re.search(r'command\s*\{([^}]+)\}', body, re.DOTALL)
        python_version = None
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
            # Find key = value pairs
            for line in args_block.splitlines():
                line = line.strip()
                if not line or line.startswith("#") or line.startswith("//"):
                    continue
                arg_kv = re.match(r'["\']?([^"\'\s=]+)["\']?\s*=\s*["\']?([^"\']+)["\']?', line)
                if arg_kv:
                    k, v = arg_kv.group(1), arg_kv.group(2)
                    default_args[k] = v.strip('"\'')

        # Extract extra python modules argument
        additional_py_modules = default_args.get("--additional-python-modules", "")
        extra_py_files = default_args.get("--extra-py-files", "")
        extra_jars = default_args.get("--extra-jars", "")

        # Parse module list
        parsed_libraries = []
        if additional_py_modules:
            # e.g., "polars==0.20.10,duckdb>=0.9.0,boto3,pandas==2.2.1"
            raw_modules = [m.strip() for m in additional_py_modules.split(",") if m.strip()]
            for rm in raw_modules:
                # Extract package name and version specifier
                spec_match = re.match(r'^([a-zA-Z0-9_\-\.]+)(.*)$', rm)
                if spec_match:
                    pkg_name = spec_match.group(1).lower()
                    pkg_constraint = spec_match.group(2).strip() or "latest"
                    parsed_libraries.append({
                        "raw": rm,
                        "package": pkg_name,
                        "constraint": pkg_constraint
                    })

        return {
            "resource_id": res_id,
            "job_name": job_name,
            "filename": filename,
            "glue_version": glue_version,
            "worker_type": worker_type,
            "number_of_workers": number_of_workers,
            "command_name": command_name,
            "declared_python_version": python_version,
            "script_location": script_location,
            "default_arguments": default_args,
            "additional_python_modules_raw": additional_py_modules,
            "parsed_libraries": parsed_libraries,
            "extra_py_files": extra_py_files,
            "extra_jars": extra_jars
        }
