"""
AWS Glue Version & Worker Type Compatibility Matrix
Derived from AWS Glue documentation and specifications.
"""

GLUE_SPECS = {
    "5.0": {
        "release": "AWS Glue 5.0",
        "default_python": "3.11",
        "supported_pythons": ["3.11"],
        "spark_version": "Spark 3.5.2",
        "worker_types": {
            "G.1X": {"vCPU": 4, "memory_gb": 16, "executor_memory_gb": 10, "recommended_for": "Memory-intensive / general"},
            "G.2X": {"vCPU": 8, "memory_gb": 32, "executor_memory_gb": 20, "recommended_for": "Large data transforms / complex ML"},
            "G.4X": {"vCPU": 16, "memory_gb": 64, "executor_memory_gb": 40, "recommended_for": "Extreme memory & CPU jobs"},
            "G.8X": {"vCPU": 32, "memory_gb": 128, "executor_memory_gb": 80, "recommended_for": "Ultra high memory/compute workloads"},
            "G.025X": {"vCPU": 0.25, "memory_gb": 1, "executor_memory_gb": 0.5, "recommended_for": "Low volume / streaming / micro-batches"},
            "Standard": {"status": "deprecated", "notice": "Standard worker type is deprecated in Glue 5.0. Use G.1X or G.2X."}
        },
        "preinstalled_libraries": {
            "pyspark": "3.5.2",
            "boto3": "1.34.131",
            "botocore": "1.34.131",
            "numpy": "1.26.4",
            "pandas": "2.2.2",
            "scipy": "1.13.1",
            "pyarrow": "15.0.2",
            "s3fs": "2024.6.1"
        }
    },
    "4.0": {
        "release": "AWS Glue 4.0",
        "default_python": "3.10",
        "supported_pythons": ["3.10"],
        "spark_version": "Spark 3.3.0",
        "worker_types": {
            "G.1X": {"vCPU": 4, "memory_gb": 16, "executor_memory_gb": 10, "recommended_for": "Standard scalable ETL"},
            "G.2X": {"vCPU": 8, "memory_gb": 32, "executor_memory_gb": 20, "recommended_for": "Heavy transformations"},
            "G.4X": {"vCPU": 16, "memory_gb": 64, "executor_memory_gb": 40, "recommended_for": "Large scale aggregations"},
            "G.8X": {"vCPU": 32, "memory_gb": 128, "executor_memory_gb": 80, "recommended_for": "Massive enterprise jobs"},
            "G.025X": {"vCPU": 0.25, "memory_gb": 1, "executor_memory_gb": 0.5, "recommended_for": "Streaming / low-volume"},
            "Standard": {"status": "deprecated", "notice": "Deprecated in Glue 4.0"}
        },
        "preinstalled_libraries": {
            "pyspark": "3.3.0",
            "boto3": "1.26.90",
            "botocore": "1.29.90",
            "numpy": "1.22.4",
            "pandas": "1.5.3",
            "scipy": "1.9.3",
            "pyarrow": "9.0.0",
            "scikit-learn": "1.2.1"
        }
    },
    "3.0": {
        "release": "AWS Glue 3.0",
        "default_python": "3.7",
        "supported_pythons": ["3.7"],
        "spark_version": "Spark 3.1.1",
        "worker_types": {
            "G.1X": {"vCPU": 4, "memory_gb": 16, "executor_memory_gb": 10, "recommended_for": "General ETL"},
            "G.2X": {"vCPU": 8, "memory_gb": 32, "executor_memory_gb": 20, "recommended_for": "Data intensive"},
            "Standard": {"vCPU": 2, "memory_gb": 8, "executor_memory_gb": 4, "recommended_for": "Legacy standard"}
        },
        "preinstalled_libraries": {
            "pyspark": "3.1.1",
            "boto3": "1.20.24",
            "botocore": "1.23.24",
            "numpy": "1.21.5",
            "pandas": "1.3.5",
            "scipy": "1.7.3"
        }
    },
    "2.0": {
        "release": "AWS Glue 2.0",
        "default_python": "3.7",
        "supported_pythons": ["3.7"],
        "spark_version": "Spark 2.4.3",
        "worker_types": {
            "G.1X": {"vCPU": 4, "memory_gb": 16, "executor_memory_gb": 10, "recommended_for": "General ETL"},
            "G.2X": {"vCPU": 8, "memory_gb": 32, "executor_memory_gb": 20, "recommended_for": "Data intensive"},
            "Standard": {"vCPU": 2, "memory_gb": 8, "executor_memory_gb": 4, "recommended_for": "Legacy standard"}
        },
        "preinstalled_libraries": {
            "pyspark": "2.4.3",
            "boto3": "1.14.48",
            "numpy": "1.16.5",
            "pandas": "0.24.2"
        }
    },
    "1.0": {
        "release": "AWS Glue 1.0 (Legacy)",
        "default_python": "3.6",
        "supported_pythons": ["3.6", "2.7"],
        "spark_version": "Spark 2.4.3",
        "worker_types": {
            "Standard": {"vCPU": 2, "memory_gb": 8, "executor_memory_gb": 4, "recommended_for": "Legacy"}
        },
        "preinstalled_libraries": {
            "pyspark": "2.4.3",
            "boto3": "1.9.203"
        }
    },
    "ray-2.4": {
        "release": "AWS Glue Ray (Python 3.9)",
        "default_python": "3.9",
        "supported_pythons": ["3.9"],
        "spark_version": "Ray 2.4",
        "worker_types": {
            "Z.2X": {"vCPU": 8, "memory_gb": 64, "recommended_for": "Glue Ray Workloads"}
        },
        "preinstalled_libraries": {
            "ray": "2.4.0",
            "pandas": "2.0.2",
            "numpy": "1.24.3",
            "pyarrow": "12.0.0"
        }
    }
}

KNOWN_PACKAGES_METADATA = {
    "polars": {"min_py": "3.8", "max_py": "3.13", "c_extension": True, "notes": "Requires GLIBC >= 2.17; wheels available for x86_64."},
    "duckdb": {"min_py": "3.8", "max_py": "3.13", "c_extension": True, "notes": "Native binary library; ensure wheel matches Amazon Linux."},
    "pandas": {"min_py": "3.8", "max_py": "3.13", "c_extension": True, "notes": "Pre-installed in Glue; version pinning can cause conflicts."},
    "numpy": {"min_py": "3.8", "max_py": "3.13", "c_extension": True, "notes": "NumPy 2.x broke ABI compatibility with older pandas & scipy."},
    "scipy": {"min_py": "3.9", "max_py": "3.13", "c_extension": True, "notes": "Requires Fortran/BLAS runtimes."},
    "pyarrow": {"min_py": "3.8", "max_py": "3.13", "c_extension": True, "notes": "Heavy binary dependency; version mismatch with PySpark can fail ORC/Parquet."},
    "boto3": {"min_py": "3.7", "max_py": "3.13", "c_extension": False, "notes": "Pure Python, but bundled with Glue runtime."},
    "scikit-learn": {"min_py": "3.9", "max_py": "3.13", "c_extension": True, "notes": "Requires numpy & scipy compatibility."},
    "torch": {"min_py": "3.8", "max_py": "3.12", "c_extension": True, "notes": "Size exceeds typical Glue bundle limit (>800MB); recommend s3 dist."},
    "tensorflow": {"min_py": "3.9", "max_py": "3.12", "c_extension": True, "notes": "Requires G.2X+ worker due to high memory footprint during import."},
    "fastparquet": {"min_py": "3.8", "max_py": "3.12", "c_extension": True, "notes": "LLVM/numba compilation needed unless binary wheel provided."},
    "delta-spark": {"min_py": "3.8", "max_py": "3.11", "c_extension": False, "notes": "Strict Spark version dependency. Glue 4.0 (Spark 3.3) needs delta-spark 2.2.0."},
    "great-expectations": {"min_py": "3.8", "max_py": "3.11", "c_extension": False, "notes": "Heavy dependency tree; can cause pip resolution timeouts in Glue."},
    "awswrangler": {"min_py": "3.8", "max_py": "3.11", "c_extension": False, "notes": "AWS SDK for pandas. Often provided via AWS Glue pre-installed connector."}
}
