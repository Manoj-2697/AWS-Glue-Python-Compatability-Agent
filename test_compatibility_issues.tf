# AWS Glue Infrastructure with Known Python Compatibility Inefficiencies
# Environment: Migration Staging
# Description: This Terraform script contains intentional Glue & Python compatibility issues
# to demonstrate inefficiency scoring (0-100%) and optimal target version recommendations.

terraform {
  required_version = ">= 1.5.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

# -----------------------------------------------------------------------------
# ISSUE JOB 1: Legacy Glue 3.0 (Python 3.7) with Modern Incompatible Libraries
# Issues:
# - Glue 3.0 runs Python 3.7 (Deprecated / EOL)
# - Worker type "Standard" is deprecated
# - pandas==2.2.2 requires Python >= 3.9 (FAIL on 3.7)
# - scikit-learn>=1.4.0 requires Python >= 3.10 (FAIL on 3.7)
# - polars requires Python >= 3.8 and GLIBC >= 2.17 (FAIL on 3.7)
# Expected Inefficiency Score: ~85% (Critical Action Required)
# Recommended Target: AWS Glue 5.0 (Python 3.11) with G.1X or G.2X
# -----------------------------------------------------------------------------
resource "aws_glue_job" "legacy_telemetry_processor" {
  name              = "legacy-telemetry-processor-incompatible"
  role_arn          = "arn:aws:iam::123456789012:role/AWSGlueServiceRole-Telemetry"
  glue_version      = "3.0"
  worker_type       = "Standard"
  number_of_workers = 4
  timeout           = 60

  command {
    name            = "glueetl"
    script_location = "s3://company-glue-scripts/telemetry_etl.py"
    python_version  = "3"
  }

  default_arguments = {
    "--job-language"                     = "python"
    "--job-bookmark-option"              = "job-bookmark-enable"
    "--TempDir"                          = "s3://company-glue-temp/temp/"
    "--additional-python-modules"        = "pandas==2.2.2,scikit-learn>=1.4.0,polars==0.20.15"
    "--enable-continuous-cloudwatch-log" = "true"
  }
}

# -----------------------------------------------------------------------------
# ISSUE JOB 2: Glue 4.0 Heavy ML Libraries on Underpowered Micro Worker
# Issues:
# - Worker type G.025X only has 0.25 vCPU & 1GB RAM
# - torch (PyTorch) requires > 800MB and high memory for C++ bindings
# - PySpark collision with built-in version
# Expected Inefficiency Score: ~35-45% (Advisories / OOM Risks)
# Recommended Target: AWS Glue 5.0 with worker type G.2X or G.4X
# -----------------------------------------------------------------------------
resource "aws_glue_job" "micro_worker_heavy_ml" {
  name              = "micro-worker-heavy-ml-risk"
  role_arn          = "arn:aws:iam::123456789012:role/AWSGlueServiceRole-ML"
  glue_version      = "4.0"
  worker_type       = "G.025X"
  number_of_workers = 2
  timeout           = 30

  command {
    name            = "glueetl"
    script_location = "s3://company-glue-scripts/deep_learning_infer.py"
    python_version  = "3"
  }

  default_arguments = {
    "--job-language"              = "python"
    "--additional-python-modules" = "torch,tensorflow,pyarrow==9.0.0"
  }
}
