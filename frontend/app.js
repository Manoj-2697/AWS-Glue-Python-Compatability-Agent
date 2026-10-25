// State Management
let currentAuth = null;
let repositories = [];
let selectedRepo = null;
let lastAnalysisReport = null;
let glueSpecsData = null;

const API_BASE = window.location.origin;

// Tab Switching
function switchTab(tabId) {
  document.getElementById('tabGithub').classList.add('hidden');
  document.getElementById('tabDirect').classList.add('hidden');
  document.getElementById('tabMatrix').classList.add('hidden');

  document.getElementById('tabGithubBtn').classList.remove('active');
  document.getElementById('tabDirectBtn').classList.remove('active');
  document.getElementById('tabMatrixBtn').classList.remove('active');

  if (tabId === 'github') {
    document.getElementById('tabGithub').classList.remove('hidden');
    document.getElementById('tabGithubBtn').classList.add('active');
  } else if (tabId === 'direct') {
    document.getElementById('tabDirect').classList.remove('hidden');
    document.getElementById('tabDirectBtn').classList.add('active');
  } else if (tabId === 'matrix') {
    document.getElementById('tabMatrix').classList.remove('hidden');
    document.getElementById('tabMatrixBtn').classList.add('active');
    loadMatrixData();
  }
}

// GitHub Authentication
async function handleGitHubAuth() {
  const token = document.getElementById('ghToken').value.trim();
  if (!token) {
    alert('Please enter a GitHub Personal Access Token or click Quick Demo Mode.');
    return;
  }

  const spinner = document.getElementById('connectSpinner');
  const btn = document.getElementById('connectGhBtn');
  spinner.classList.remove('hidden');
  btn.disabled = true;

  try {
    const res = await fetch(`${API_BASE}/api/github/authenticate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ token })
    });

    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || 'Authentication failed');
    }

    const data = await res.json();
    currentAuth = { token, ...data };
    updateUserUI(data.user);
    await loadRepositories(token, data.demo_mode);
  } catch (err) {
    alert('GitHub Auth Error: ' + err.message);
  } finally {
    spinner.classList.add('hidden');
    btn.disabled = false;
  }
}

function useDemoAccount() {
  document.getElementById('ghToken').value = 'demo-token';
  handleGitHubAuth();
}

function updateUserUI(user) {
  const badge = document.getElementById('userBadge');
  const avatar = document.getElementById('userAvatar');
  const name = document.getElementById('userName');

  avatar.src = user.avatar_url || 'https://avatars.githubusercontent.com/u/583231?v=4';
  name.textContent = user.name || user.login;
  badge.classList.remove('hidden');

  document.getElementById('logoutBtn').onclick = () => {
    currentAuth = null;
    selectedRepo = null;
    badge.classList.add('hidden');
    document.getElementById('repoSection').style.display = 'none';
    document.getElementById('reportSection').style.display = 'none';
    document.getElementById('ghToken').value = '';
  };
}

// Load Repositories
async function loadRepositories(token, isDemo = false) {
  const repoSection = document.getElementById('repoSection');
  repoSection.style.display = 'flex';

  try {
    const res = await fetch(`${API_BASE}/api/github/repositories?token=${encodeURIComponent(token)}&demo=${isDemo}`);
    const data = await res.json();
    repositories = data.repositories || [];
    renderRepositories(repositories);
  } catch (err) {
    alert('Failed to load repositories: ' + err.message);
  }
}

function refreshRepositories() {
  if (currentAuth) {
    loadRepositories(currentAuth.token, currentAuth.demo_mode);
  }
}

let selectedRepos = new Map(); // Store selected repos by id: id -> repo

function renderRepositories(repos) {
  const grid = document.getElementById('repoList');
  grid.innerHTML = '';

  if (repos.length === 0) {
    grid.innerHTML = '<div style="color: var(--text-muted); padding: 1rem;">No repositories found.</div>';
    return;
  }

  repos.forEach(repo => {
    const isSelected = selectedRepos.has(repo.id);
    const card = document.createElement('div');
    card.className = `repo-card ${isSelected ? 'selected' : ''}`;
    card.id = `repo-card-${repo.id}`;
    card.onclick = () => toggleSelectRepository(repo, card);

    card.innerHTML = `
      <div>
        <div class="repo-card-top">
          <div class="repo-title">
            <input type="checkbox" id="chk-${repo.id}" ${isSelected ? 'checked' : ''} style="margin-right: 8px; transform: scale(1.2); cursor: pointer;" onclick="event.stopPropagation(); toggleSelectRepository(repo, card);">
            <span>📁</span> ${escapeHtml(repo.name)}
          </div>
          <span class="repo-badge">${repo.private ? '🔒 Private' : '🌐 Public'}</span>
        </div>
        <p class="repo-desc">${escapeHtml(repo.description || 'No description provided.')}</p>
      </div>
      <div class="repo-meta">
        <span>Branch: <strong>${repo.default_branch}</strong></span>
        <span>${repo.language || 'HCL/Terraform'}</span>
        <span>Updated: ${new Date(repo.updated_at).toLocaleDateString()}</span>
      </div>
    `;

    grid.appendChild(card);
  });
  updateAnalysisButtonState();
}

function toggleSelectRepository(repo, cardElement) {
  if (selectedRepos.has(repo.id)) {
    selectedRepos.delete(repo.id);
    if (cardElement) cardElement.classList.remove('selected');
    const chk = document.getElementById(`chk-${repo.id}`);
    if (chk) chk.checked = false;
  } else {
    selectedRepos.set(repo.id, repo);
    if (cardElement) cardElement.classList.add('selected');
    const chk = document.getElementById(`chk-${repo.id}`);
    if (chk) chk.checked = true;
  }
  updateAnalysisButtonState();
}

function updateAnalysisButtonState() {
  const btn = document.getElementById('runRepoAnalysisBtn');
  const count = selectedRepos.size;
  if (count === 0) {
    btn.disabled = true;
    btn.querySelector('span:last-child').textContent = '⚡ Run AI Compatibility Analysis';
  } else if (count === 1) {
    btn.disabled = false;
    btn.querySelector('span:last-child').textContent = `⚡ Run AI Analysis (1 Repository)`;
  } else {
    btn.disabled = false;
    btn.querySelector('span:last-child').textContent = `⚡ Run AI Analysis (${count} Repositories)`;
  }
}

// Execute Multi-Repo Analysis
async function executeRepoAnalysis() {
  if (selectedRepos.size === 0) return;

  const spinner = document.getElementById('analysisSpinner');
  const btn = document.getElementById('runRepoAnalysisBtn');
  spinner.classList.remove('hidden');
  btn.disabled = true;

  try {
    const reposList = Array.from(selectedRepos.values());
    const combinedReport = {
      repository: reposList.map(r => r.name).join(', '),
      scanned_tf_files_count: 0,
      scanned_files: [],
      glue_jobs_count: 0,
      summary: {
        total_jobs: 0,
        healthy: 0,
        warnings: 0,
        action_required: 0,
        average_inefficiency_score: 0
      },
      jobs_analysis: []
    };

    let totalInefficiencySum = 0;

    for (const repo of reposList) {
      const res = await fetch(`${API_BASE}/api/analyze/repository`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          owner: repo.owner,
          repo: repo.name,
          default_branch: repo.default_branch,
          token: currentAuth ? currentAuth.token : '',
          is_demo: currentAuth ? currentAuth.demo_mode : false,
          use_grok: true
        })
      });

      if (!res.ok) {
        let errMsg = 'HTTP ' + res.status;
        try {
          const err = await res.json();
          errMsg = err.detail || errMsg;
        } catch (_) {
          errMsg = await res.text();
        }
        console.warn(`Analysis failed for ${repo.name}:`, errMsg);
        alert(`Analysis failed for ${repo.name}: ` + errMsg);
        continue;
      }

      const report = await res.json();
      combinedReport.scanned_tf_files_count += (report.scanned_tf_files_count || 0);
      combinedReport.glue_jobs_count += (report.glue_jobs_count || 0);
      if (report.scanned_files) {
        combinedReport.scanned_files.push(...report.scanned_files);
      }
      if (report.jobs_analysis) {
        combinedReport.jobs_analysis.push(...report.jobs_analysis);
      }
      if (report.summary) {
        combinedReport.summary.healthy += (report.summary.healthy || 0);
        combinedReport.summary.warnings += (report.summary.warnings || 0);
        combinedReport.summary.action_required += (report.summary.action_required || 0);
        totalInefficiencySum += (report.summary.average_inefficiency_score * (report.glue_jobs_count || 1));
      }
    }

    combinedReport.summary.total_jobs = combinedReport.glue_jobs_count;
    combinedReport.summary.average_inefficiency_score = combinedReport.glue_jobs_count > 0 
      ? Math.round(totalInefficiencySum / combinedReport.glue_jobs_count) 
      : 0;

    lastAnalysisReport = combinedReport;
    renderAnalysisReport(combinedReport);
  } catch (err) {
    alert('Analysis Error: ' + err.message);
  } finally {
    spinner.classList.add('hidden');
    btn.disabled = false;
  }
}

// Render Analysis Report
function renderAnalysisReport(report) {
  const reportSec = document.getElementById('reportSection');
  reportSec.style.display = 'flex';
  reportSec.scrollIntoView({ behavior: 'smooth' });

  document.getElementById('repoNameBadge').textContent = report.repository;
  document.getElementById('reportSubheader').textContent = 
    `Scanned ${report.scanned_tf_files_count} Terraform file(s) across repository. Found ${report.glue_jobs_count} AWS Glue Job resource(s).`;

  const summary = report.summary || {
    total_jobs: report.glue_jobs_count,
    healthy: 0,
    warnings: 0,
    action_required: 0
  };

  document.getElementById('statTotalJobs').textContent = summary.total_jobs;
  document.getElementById('statHealthy').textContent = summary.healthy;
  document.getElementById('statWarnings').textContent = summary.warnings;
  document.getElementById('statActionReq').textContent = summary.action_required;

  const container = document.getElementById('jobsListContainer');
  container.innerHTML = '';

  if (!report.jobs_analysis || report.jobs_analysis.length === 0) {
    container.innerHTML = `
      <div style="background: rgba(0,0,0,0.3); border-radius: var(--radius-md); padding: 2rem; text-align: center; color: var(--text-muted);">
        No AWS Glue Job resources detected in this repository.
      </div>
    `;
    return;
  }

  report.jobs_analysis.forEach(job => {
    container.appendChild(createJobCard(job));
  });
}

function createJobCard(job) {
  const card = document.createElement('div');
  
  let statusClass = 'status-healthy';
  let badgeClass = 'pass';
  let badgeText = 'Fully Compatible';

  if (job.verdict.includes('ACTION REQUIRED') || !job.overall_compatible) {
    statusClass = 'status-critical';
    badgeClass = 'fail';
    badgeText = 'Compatibility Action Required';
  } else if (job.verdict.includes('WARNINGS') || job.worker_status !== 'compatible') {
    statusClass = 'status-warning';
    badgeClass = 'warning';
    badgeText = 'Review Advisories';
  }

  card.className = `job-card ${statusClass}`;

  const workerInfo = job.worker_specs || {};
  const vcpuText = workerInfo.vCPU ? `${workerInfo.vCPU} vCPU` : 'N/A';
  const memText = workerInfo.memory_gb ? `${workerInfo.memory_gb} GB RAM` : 'N/A';

  // Build libraries table rows
  let libRows = '';
  if (job.library_checks && job.library_checks.length > 0) {
    libRows = job.library_checks.map(lib => {
      let lBadge = '<span class="badge-tag pass">Compatible</span>';
      if (lib.status === 'fail') lBadge = '<span class="badge-tag fail">Incompatible</span>';
      if (lib.status === 'warning') lBadge = '<span class="badge-tag warning">Advisory</span>';

      const notesHtml = lib.notes && lib.notes.length > 0
        ? lib.notes.map(n => `<div style="margin-top: 4px; font-size: 0.8rem; color: ${lib.status === 'fail' ? '#f87171' : '#fbbf24'};">• ${escapeHtml(n)}</div>`).join('')
        : '<span style="color: var(--text-dim);">No conflicts detected</span>';

      return `
        <tr>
          <td><span class="code-badge">${escapeHtml(lib.raw)}</span></td>
          <td><strong style="color: #cbd5e1;">${escapeHtml(lib.package)}</strong></td>
          <td><span class="code-badge" style="color: #94a3b8;">${escapeHtml(lib.requires_python || 'Any')}</span></td>
          <td>${lib.pypi_latest ? '<span style="color: #38bdf8;">' + lib.pypi_latest + '</span>' : 'N/A'}</td>
          <td>${lBadge}</td>
          <td>${notesHtml}</td>
        </tr>
      `;
    }).join('');
  } else {
    libRows = `<tr><td colspan="6" style="text-align: center; color: var(--text-muted); padding: 1.5rem;">No additional python modules specified in default_arguments. Uses standard Glue runtime libraries.</td></tr>`;
  }

  card.innerHTML = `
    <div class="job-header">
      <div>
        <div class="job-title">
          <span>⚙️</span> ${escapeHtml(job.job_name)}
          <span style="font-size: 0.8rem; font-weight: normal; color: var(--text-dim); font-family: var(--font-mono);">(${escapeHtml(job.file || 'Terraform Module')})</span>
        </div>
      </div>
      <span class="badge-tag ${badgeClass}" style="font-size: 0.85rem; padding: 6px 14px;">${badgeText}</span>
    </div>

    <!-- Job Specifications Pills -->
    <div class="job-specs-pills">
      <div class="pill">Glue Version: <strong>AWS Glue ${escapeHtml(job.glue_version)}</strong></div>
      <div class="pill">Worker Type: <strong>${escapeHtml(job.worker_type)}</strong> (${vcpuText}, ${memText})</div>
      <div class="pill">Cluster Scale: <strong>${job.worker_capacity?.num_workers || 2} Workers</strong> (${job.worker_capacity?.total_vcpu || 'N/A'} vCPUs, ${job.worker_capacity?.total_memory_gb || 'N/A'} GB Memory)</div>
      <div class="pill">Runtime Python: <strong style="color: #38bdf8;">Python ${escapeHtml(job.runtime_python)}</strong></div>
      <div class="pill">Engine: <strong>${escapeHtml(job.spark_version || 'PySpark')}</strong></div>
    </div>

    <!-- AI Insights Box -->
    <div class="ai-insights">
      <h4><span>🤖</span> AI Compatibility Analysis &amp; Guidance</h4>
      <div class="ai-insights-content">${escapeHtml(job.ai_executive_summary)}</div>
    </div>

    <!-- Additional Python Libraries Table -->
    <div>
      <div style="font-size: 0.9rem; font-weight: 600; margin-bottom: 8px; color: #cbd5e1; display: flex; justify-content: space-between;">
        <span>Additional Python Libraries Cross-Check (--additional-python-modules)</span>
        <span style="font-size: 0.8rem; color: var(--text-dim);">${job.library_checks?.length || 0} module(s) analyzed</span>
      </div>
      <div class="lib-table-container">
        <table class="lib-table">
          <thead>
            <tr>
              <th>Module Argument</th>
              <th>Package Name</th>
              <th>Required Python</th>
              <th>PyPI Latest</th>
              <th>Status</th>
              <th>Analysis &amp; Conflict Notes</th>
            </tr>
          </thead>
          <tbody>
            ${libRows}
          </tbody>
        </table>
      </div>
    </div>
  `;

  return card;
}

// Direct HCL Analysis
async function analyzeDirectHcl() {
  const content = document.getElementById('directHclEditor').value.trim();
  if (!content) {
    alert('Please enter or paste Terraform HCL content.');
    return;
  }

  const spinner = document.getElementById('directSpinner');
  const btn = document.getElementById('runDirectAnalysisBtn');
  spinner.classList.remove('hidden');
  btn.disabled = true;

  try {
    const res = await fetch(`${API_BASE}/api/analyze/direct-hcl`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ hcl_content: content, filename: 'playground.tf' })
    });

    if (!res.ok) throw new Error('Analysis failed');

    const data = await res.json();
    const container = document.getElementById('directResultsContainer');
    container.innerHTML = '';

    if (!data.jobs_analysis || data.jobs_analysis.length === 0) {
      container.innerHTML = '<div style="color: var(--text-muted); padding: 1rem;">No aws_glue_job resources found in pasted HCL.</div>';
      return;
    }

    data.jobs_analysis.forEach(job => {
      container.appendChild(createJobCard(job));
    });
  } catch (err) {
    alert('HCL Analysis Error: ' + err.message);
  } finally {
    spinner.classList.add('hidden');
    btn.disabled = false;
  }
}

// Sample HCL Templates
const SAMPLE_HCL = {
  glue4: `resource "aws_glue_job" "modern_pyspark_job" {
  name              = "customer-pipeline-glue4"
  glue_version      = "4.0"
  worker_type       = "G.1X"
  number_of_workers = 10

  command {
    name            = "glueetl"
    script_location = "s3://my-bucket/script.py"
    python_version  = "3"
  }

  default_arguments = {
    "--additional-python-modules" = "polars>=0.20.0,duckdb>=0.9.2,pyarrow,s3fs"
    "--job-language"              = "python"
  }
}`,
  glue3_conflict: `resource "aws_glue_job" "legacy_glue3_job" {
  name              = "legacy-warehouse-glue3"
  glue_version      = "3.0"
  worker_type       = "Standard"
  number_of_workers = 4

  command {
    name            = "glueetl"
    script_location = "s3://my-bucket/legacy.py"
    python_version  = "3"
  }

  default_arguments = {
    # Incompatible with Glue 3.0's Python 3.7 runtime!
    "--additional-python-modules" = "pandas==2.2.2,scikit-learn>=1.4.0,polars"
  }
}`,
  glue5: `resource "aws_glue_job" "glue5_ultra_job" {
  name              = "high-throughput-ml-glue5"
  glue_version      = "5.0"
  worker_type       = "G.2X"
  number_of_workers = 16

  command {
    name            = "glueetl"
    script_location = "s3://my-bucket/ml_etl.py"
    python_version  = "3"
  }

  default_arguments = {
    "--additional-python-modules" = "fastparquet>=2024.2.0,pydantic>=2.5.0,s3fs"
  }
}`
};

function loadSampleHcl(type) {
  document.getElementById('directHclEditor').value = SAMPLE_HCL[type] || SAMPLE_HCL['glue4'];
}

// Load Matrix
async function loadMatrixData() {
  const container = document.getElementById('matrixTableContainer');
  if (glueSpecsData) return;

  container.innerHTML = '<div style="padding: 1rem; color: var(--text-muted);">Loading official specifications...</div>';
  try {
    const res = await fetch(`${API_BASE}/api/specs`);
    const specs = await res.json();
    glueSpecsData = specs;

    let rows = '';
    for (const [vKey, vVal] of Object.entries(specs)) {
      const workers = Object.keys(vVal.worker_types).join(', ');
      const preinstalled = Object.entries(vVal.preinstalled_libraries || {})
        .map(([k, v]) => `${k}==${v}`)
        .join(', ');

      rows += `
        <tr>
          <td><strong style="color: #60a5fa;">AWS Glue ${escapeHtml(vKey)}</strong></td>
          <td><span class="code-badge" style="color: #34d399;">Python ${escapeHtml(vVal.default_python)}</span></td>
          <td>${escapeHtml(vVal.spark_version || 'PySpark')}</td>
          <td><span style="font-size: 0.8rem; color: #cbd5e1;">${escapeHtml(workers)}</span></td>
          <td><span style="font-size: 0.775rem; color: var(--text-muted); font-family: var(--font-mono);">${escapeHtml(preinstalled)}</span></td>
        </tr>
      `;
    }

    container.innerHTML = `
      <table class="lib-table">
        <thead>
          <tr>
            <th>Glue Version</th>
            <th>Runtime Python</th>
            <th>Engine / Spark</th>
            <th>Available Worker Types</th>
            <th>Key Pre-installed Bundles</th>
          </tr>
        </thead>
        <tbody>
          ${rows}
        </tbody>
      </table>
    `;
  } catch (err) {
    container.innerHTML = '<div style="color: #f87171; padding: 1rem;">Failed to load specs: ' + err.message + '</div>';
  }
}

// Utility: Export JSON
function exportReportJson() {
  if (!lastAnalysisReport) {
    alert('No report available to export.');
    return;
  }
  const blob = new Blob([JSON.stringify(lastAnalysisReport, null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `glue_compatibility_report_${new Date().toISOString().slice(0, 10)}.json`;
  a.click();
}

function printReport() {
  window.print();
}

function escapeHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

// Initialise default editor content
window.addEventListener('DOMContentLoaded', () => {
  loadSampleHcl('glue4');
});
