"""
Demo/Mock GitHub Data and Samples to allow instant exploration
even before or without a personal GitHub token.
"""

SAMPLE_GLUE_TERRAFORM = """# Production AWS Glue Data Processing Pipeline
# Environment: AWS Production Infrastructure

terraform {
  required_version = ">= 1.5.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

# 1. High-throughput PySpark ETL Job with Modern Python Libraries
resource "aws_glue_job" "customer_analytics_etl" {
  name              = "prod-customer-analytics-etl"
  role_arn          = "arn:aws:iam::123456789012:role/AWSGlueServiceRole-Analytics"
  glue_version      = "4.0"
  worker_type       = "G.2X"
  number_of_workers = 10
  timeout           = 120

  command {
    name            = "glueetl"
    script_location = "s3://company-glue-scripts-prod/customer_analytics.py"
    python_version  = "3"
  }

  default_arguments = {
    "--job-language"                     = "python"
    "--job-bookmark-option"              = "job-bookmark-enable"
    "--enable-metrics"                   = "true"
    "--enable-continuous-cloudwatch-log" = "true"
    "--TempDir"                          = "s3://company-glue-temp-prod/temp/"
    "--additional-python-modules"        = "polars==0.20.15,duckdb>=0.10.0,pyarrow==14.0.2,boto3"
    "--extra-py-files"                   = "s3://company-glue-scripts-prod/utils.zip"
  }
}

# 2. Legacy Migration Job using Glue 3.0 with Version-locked Libraries
resource "aws_glue_job" "legacy_event_transformer" {
  name              = "legacy-event-transformer-v3"
  role_arn          = "arn:aws:iam::123456789012:role/AWSGlueServiceRole-Legacy"
  glue_version      = "3.0"
  worker_type       = "Standard"
  number_of_workers = 4

  command {
    name            = "glueetl"
    script_location = "s3://legacy-glue-scripts/transformer.py"
    python_version  = "3"
  }

  default_arguments = {
    "--job-language"              = "python"
    "--additional-python-modules" = "pandas==2.2.2,scikit-learn>=1.4.0,polars"
  }
}

# 3. Next-Gen Glue 5.0 Fast Streaming Aggregator
resource "aws_glue_job" "realtime_clickstream_processor" {
  name              = "realtime-clickstream-processor"
  role_arn          = "arn:aws:iam::123456789012:role/AWSGlueServiceRole-Realtime"
  glue_version      = "5.0"
  worker_type       = "G.1X"
  number_of_workers = 6

  command {
    name            = "glueetl"
    script_location = "s3://company-glue-scripts-prod/clickstream.py"
    python_version  = "3"
  }

  default_arguments = {
    "--job-language"              = "python"
    "--additional-python-modules" = "fastparquet>=2024.2.0,pydantic>=2.5.0,s3fs"
  }
}
"""

SAMPLE_REPOSITORIES = [
    {
        "id": 101,
        "name": "data-platform-terraform-infrastructure",
        "full_name": "enterprise-data/data-platform-terraform-infrastructure",
        "owner": "enterprise-data",
        "private": True,
        "description": "Production Terraform modules for AWS Glue ETL, Lakehouse, and Athena resources",
        "default_branch": "main",
        "updated_at": "2026-10-24T18:40:00Z",
        "language": "HCL",
        "sample_files": {
            "terraform/modules/glue_jobs/main.tf": SAMPLE_GLUE_TERRAFORM,
            "terraform/modules/glue_jobs/variables.tf": "# Variable definitions",
            "terraform/environments/prod/glue.tf": SAMPLE_GLUE_TERRAFORM
        }
    },
    {
        "id": 102,
        "name": "aws-lakehouse-analytics",
        "full_name": "enterprise-data/aws-lakehouse-analytics",
        "owner": "enterprise-data",
        "private": False,
        "description": "Lakehouse data ingestion pipelines, Spark jobs, and AWS Glue crawlers",
        "default_branch": "main",
        "updated_at": "2026-10-22T11:15:00Z",
        "language": "HCL",
        "sample_files": {
            "infra/glue_etl_jobs.tf": SAMPLE_GLUE_TERRAFORM
        }
    },
    {
        "id": 103,
        "name": "fintech-risk-pipeline-glue",
        "full_name": "fintech-org/fintech-risk-pipeline-glue",
        "owner": "fintech-org",
        "private": True,
        "description": "Risk calculation Glue pipelines with heavy numeric and ML dependencies",
        "default_branch": "main",
        "updated_at": "2026-10-20T09:20:00Z",
        "language": "HCL",
        "sample_files": {
            "glue_jobs.tf": SAMPLE_GLUE_TERRAFORM
        }
    }
]
