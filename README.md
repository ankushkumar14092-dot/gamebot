<div align="center">

# 🎮 CAMBC Autonomous GameBot

### *Always-On, AI-Driven Autonomous Bot Evolution System for Cambridge Battlecode*

[![CI – Build, Test & Verify](https://github.com/ankushkumar14092-dot/gamebot/actions/workflows/ci.yml/badge.svg)](https://github.com/ankushkumar14092-dot/gamebot/actions/workflows/ci.yml)
[![Autonomous Improvement Loop](https://github.com/ankushkumar14092-dot/gamebot/actions/workflows/autonomous_improver.yml/badge.svg)](https://github.com/ankushkumar14092-dot/gamebot/actions/workflows/autonomous_improver.yml)
[![Python Version](https://img.shields.io/badge/python-3.13-blue.svg?logo=python&logoColor=white)](https://www.python.org/)
[![CAMBC Version](https://img.shields.io/badge/CAMBC%20SDK-v2.2.3-orange.svg)](https://battlecode.org/)
[![C++ Standard](https://img.shields.io/badge/C%2B%2B-20-00599C.svg?logo=c%2B%2B&logoColor=white)](https://isocpp.org/)
[![Docker Ready](https://img.shields.io/badge/Docker-Ready-2496ED.svg?logo=docker&logoColor=white)](./Dockerfile)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](./LICENSE)

<br/>

**A persistent cloud-native autonomous intelligence system that continuously analyzes match replays, diagnoses tactical failures, synthesizes algorithmic C++ patches via LLMs, runs regression suites and paired quantitative benchmarks, and safely promotes verified candidates.**

[Features](#-key-features) • [Architecture](#-architecture) • [Quick Start](#-quick-start) • [Cloud Deployment](#-cloud-deployment) • [CLI Tools](#-cli--tooling) • [Configuration](#-configuration) • [Contributing](#-contributing)

</div>

---

## 🌟 Overview

The **CAMBC GameBot Improvement Agent** transforms competitive bot programming into an automated, self-healing evolutionary loop. Running 24/7 on GitHub Cloud Infrastructure or dedicated Docker containers, the agent observes official platform matches, detects regressions, isolates candidate source branches, applies targeted patches using state-of-the-art LLMs (Gemini / Fireworks AI), and only promotes code that statistically out-performs the reigning incumbent bot.

```
+-----------------------------------------------------------------------------------------+
|                                    AUTONOMOUS PIPELINE                                  |
|                                                                                         |
|  [Match Replays] ➔ [Diagnostic Audit] ➔ [LLM Patching] ➔ [Isolated Git Branch]          |
|                                                                   │                     |
|  [Safe Release]   [Registry Record]   [Paired Benchmark]   [WASM Build & Tests]     |
+-----------------------------------------------------------------------------------------+
```

---

## ⚡ Key Features

| Feature | Description |
|---|---|
| 🤖 **Autonomous Evolution Loop** | Continuously runs scheduled improvement cycles every 3 hours in the cloud without requiring a running laptop. |
| 🛡️ **Zero-Pollution Git Isolation** | Candidates are developed and evaluated exclusively on dedicated, isolated Git worktrees/branches to protect incumbent code. |
| 🧠 **Multi-LLM Tactical Synthesis** | Evidence-backed patch generation using Google Gemini (`gemini-2.5-flash`) and Fireworks AI with bounded exponential backoff & rate-limit handling. |
| 📊 **Rigorous Quantitative Gate** | Statistical paired evaluation across symmetric map positions (sides A & B), measuring net gem delta, win rate, and zero-fault invariant. |
| 🔒 **Version Registry & State Ledger** | Cryptographic checksums and full audit trails recorded in [`best_version_registry.json`](./best_version_registry.json). |
| 🚨 **Fail-Safe Emergency Protocol** | Instant killswitch triggered by `EMERGENCY_STOP` sentinel files to halt execution gracefully in under 1 second. |
| 🐳 **Docker & Cloud Native** | Full multi-arch containerization with non-root UID/GID mapping, volume caching, and GitHub Actions CI/CD workflows. |

---

## 📐 Architecture

```mermaid
flowchart TD
    classDef platform fill:#1e293b,stroke:#38bdf8,stroke-width:2px,color:#f8fafc;
    classDef analysis fill:#1e1e38,stroke:#818cf8,stroke-width:2px,color:#f8fafc;
    classDef ai fill:#311042,stroke:#c084fc,stroke-width:2px,color:#f8fafc;
    classDef sandbox fill:#064e3b,stroke:#34d399,stroke-width:2px,color:#f8fafc;
    classDef gate fill:#78350f,stroke:#f59e0b,stroke-width:2px,color:#f8fafc;
    classDef registry fill:#14532d,stroke:#22c55e,stroke-width:2px,color:#f8fafc;
    classDef reject fill:#7f1d1d,stroke:#ef4444,stroke-width:2px,color:#f8fafc;

    subgraph Ingestion["📡 1. Ingestion & Telemetry"]
        CAMBC["Official CAMBC Competition Platform"]:::platform
        Replays["Replay Bundles (*.repl26a)<br/>& Statistics JSON"]:::platform
        CAMBC -->|Sync Matches| Replays
    end

    subgraph Diagnosis["🔍 2. Diagnostic & Loss Analysis"]
        Audit["Diagnostic Auditor<br/>(Death Tracker & Gem Drop Analysis)"]:::analysis
        Hypothesis{"Loss Pattern<br/>Identified?"}:::analysis
        Replays --> Audit
        Audit --> Hypothesis
    end

    subgraph Intelligence["🧠 3. Tactical LLM Synthesis"]
        LLM["Gemini 2.5 Flash / Fireworks AI<br/>(Bounded Backoff & Retry)"]:::ai
        Diff["Scoped Algorithmic Patch<br/>(bot.cpp / draft.cpp)"]:::ai
        Hypothesis -->|Yes| LLM
        LLM --> Diff
    end

    subgraph Sandbox["🌿 4. Isolated Candidate Sandbox"]
        Worktree["Isolated Git Candidate Branch<br/>(Incumbent Untouched)"]:::sandbox
        Build["WASM Compilation Engine<br/>(wasi-sdk + CMake + Ninja)"]:::sandbox
        PreFlight["Pre-Flight Unit Tests<br/>(Adapter, Reports, Security)"]:::sandbox
        
        Diff --> Worktree
        Worktree --> Build
        Build -->|Success| PreFlight
    end

    subgraph Gate["⚖️ 5. Paired Quantitative Benchmark"]
        Benchmark["Symmetric Mirror Matches<br/>(Sides A & B vs Opponent)"]:::gate
        Criteria{"Strict Gate Invariants<br/>1. Net Gem Delta > 0<br/>2. Wins >= Incumbent<br/>3. Bot Faults == 0"}:::gate
        
        PreFlight -->|Pass| Benchmark
        Benchmark --> Criteria
    end

    subgraph Outcome["🏆 6. Promotion & Ledger"]
        Registry[("best_version_registry.json<br/>(SHA-256 Checksum Ledger)")]:::registry
        GitCommit["Atomic Git Commit & Push<br/>to main branch"]:::registry
        CloudArtifacts["Upload Match Replays<br/>to GitHub Artifacts"]:::registry
        Rejected["Register Candidate as Rejected<br/>(State Saved in Ledger)"]:::reject
        
        Criteria -->|All Criteria Met| Registry
        Registry --> GitCommit
        Registry --> CloudArtifacts
        
        Build -->|Compile Error| Rejected
        PreFlight -->|Test Failure| Rejected
        Criteria -->|Regression Detected| Rejected
        Hypothesis -->|No Clear Hypothesis| Standby["Standby for Next Cycle"]:::analysis
    end
```

---

## 🚀 Quick Start

### 1. Prerequisites

- **Python 3.13+**
- **CAMBC SDK v2.2.3** (`pip install -r requirements.txt`)
- **Git**
- *Optional:* Docker & Docker Compose for containerized execution.

### 2. Local Setup

Clone the repository and install runtime dependencies:

```bash
# Clone repository
git clone https://github.com/ankushkumar14092-dot/gamebot.git
cd gamebot

# Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install --upgrade pip
pip install -r requirements.txt

# Copy environment template
cp .env.example .env
```

Edit `.env` to supply your API credentials:
```env
GEMINI_API_KEY=your_gemini_api_key_here
FIREWORKS_API_KEY=your_fireworks_api_key_here
CAMBC_TEAM_NAME=decrest
```

### 3. Verify the Environment

Run the pre-flight unit test suite to verify your setup:

```bash
python -m unittest tests/test_cambc_adapter.py \
                   tests/test_agent_reports.py \
                   tests/test_gemini_retry.py \
                   tests/test_improve_bot.py -v
```

---

## ☁️ Cloud Deployment

The repository includes a production-ready, persistent GitHub Actions workflow that executes autonomous improvement loops independently.

```mermaid
graph LR
    classDef cloud fill:#0f172a,stroke:#38bdf8,stroke-width:2px,color:#f8fafc;
    classDef runner fill:#1e1e38,stroke:#818cf8,stroke-width:2px,color:#f8fafc;
    classDef ai fill:#311042,stroke:#c084fc,stroke-width:2px,color:#f8fafc;
    classDef storage fill:#14532d,stroke:#22c55e,stroke-width:2px,color:#f8fafc;
    classDef external fill:#374151,stroke:#9ca3af,stroke-width:2px,color:#f8fafc;

    subgraph Cloud["☁️ GitHub Cloud Infrastructure"]
        Scheduler["⏰ Cloud Trigger<br/>(Cron 0 */3 * * * or Manual Dispatch)"]:::cloud
        Runner["🖥️ GitHub-Hosted Runner<br/>(Ubuntu 24.04 x86_64)"]:::runner
        ToolchainCache[("💾 Toolchain Cache<br/>(wasi-sdk, cmake, ninja, pip)")]:::storage
        ArtifactStorage[("📦 GitHub Artifacts<br/>(Replays & Evaluation Logs)")]:::storage
        GitRepo[("📂 Git Repository<br/>(ankushkumar14092-dot/gamebot)")]:::storage

        Scheduler -->|Trigger Job| Runner
        Runner <-->|Restore / Save Cache| ToolchainCache
        Runner -->|Push Validated Commits| GitRepo
        Runner -->|Upload Bundles| ArtifactStorage
    end

    subgraph ExternalServices["🌐 External Services & APIs"]
        Gemini["✨ Google Gemini API<br/>(gemini-2.5-flash)"]:::ai
        Fireworks["🎆 Fireworks AI API<br/>(LLaMA 3.3 70B)"]:::ai
        CAMBC["🎮 Cambridge Battlecode<br/>Platform & CLI"]:::external

        Runner <-->|Prompt & Diff Synthesis| Gemini
        Runner <-->|Alternative Reasoning| Fireworks
        Runner <-->|Sync Matches & Replays| CAMBC
    end
```

### 1. Automated Execution via GitHub Actions

The workflow runs on a persistent schedule (`cron: '0 */3 * * *'`) and can be triggered on-demand:

1. Navigate to **[Actions → Autonomous CAMBC Bot Improvement Loop](https://github.com/ankushkumar14092-dot/gamebot/actions/workflows/autonomous_improver.yml)**.
2. Click **Run workflow** ▾.
3. Select parameters:
   - `cycles`: Number of iterations (default: `1`)
   - `map`: Benchmark map (default: `maps/ambush.map26a`)
   - `allow_live_submission`: Toggle live platform upload (`true`/`false`)
4. Click the green **Run workflow** button.

### 2. Setting Up Repository Secrets

To enable cloud improvements with LLMs, configure these secrets in **Settings → Secrets and variables → Actions**:

| Secret Name | Required | Description |
|---|---|---|
| `GEMINI_API_KEY` | Recommended | Google Gemini API key for automated patch synthesis. |
| `FIREWORKS_API_KEY` | Optional | Fireworks AI key as alternative reasoning backend. |
| `CAMBC_TEAM_ID` | Optional | Team UUID on the official CAMBC platform. |

### 3. Containerized Daemon (Docker Compose)

For dedicated VM or home-server deployment:

```bash
# Build container image
docker compose build

# Authenticate CAMBC CLI (one-time interactive login)
docker compose run --rm match-agent cambc login

# Launch persistent background worker
docker compose up -d

# Follow live audit logs
docker compose logs -f match-agent
```

---

## 🛠️ CLI & Tooling

The [`tools/`](./tools/) directory provides modular CLI utilities for match inspection, bot evaluation, and code enhancement:

| Tool | Purpose | Usage Example |
|---|---|---|
| [`run_autonomous_agent.py`](./tools/run_autonomous_agent.py) | Master autonomous orchestrator | `python tools/run_autonomous_agent.py run --cycles 5` |
| [`review_match.py`](./tools/review_match.py) | Structured match & death analysis | `python tools/review_match.py stats.json --replay match.repl26a` |
| [`improve_bot.py`](./tools/improve_bot.py) | LLM patch creation & comparison | `python tools/improve_bot.py stats.json --gemini-fix --run` |
| [`sync_online_matches.py`](./tools/sync_online_matches.py) | Platform sync & auto-review | `python tools/sync_online_matches.py --max-experiments 1` |
| [`watch_online_matches.py`](./tools/watch_online_matches.py) | Daemon polling for new platform matches | `python tools/watch_online_matches.py` |
| [`analyze_online_losses.py`](./tools/analyze_online_losses.py) | Multi-match loss pattern auditor | `python tools/analyze_online_losses.py --limit 50` |

---

## 📂 Repository Structure

```text
gamebot/
├── .github/
│   ├── workflows/
│   │   ├── ci.yml                     # Fast CI unit tests, acceptance suite & Docker check
│   │   └── autonomous_improver.yml    # Always-on cloud improvement & benchmark loop
│   ├── ISSUE_TEMPLATE/                # GitHub issue templates
│   └── pull_request_template.md       # Standardized PR checklist
├── bots/
│   ├── submission-v6/                 # Current reigning incumbent bot (C++20)
│   │   ├── src/                       # bot.cpp, bot.h, draft.cpp, draft.h
│   │   └── CMakeLists.txt
│   └── baseline-cpp/                  # Reference opponent bot
├── maps/                              # Official competition map files (.map26a)
├── matches/                           # Local match replay exports and logs (gitignored)
├── tools/                             # Autonomous orchestrator and agent scripts
├── tests/                             # Unit tests & acceptance verification suite
├── best_version_registry.json         # Audited ledger of evaluated candidate versions
├── compose.yaml                       # Docker Compose multi-service deployment
├── Dockerfile                         # Production-grade hardened container image
├── requirements.txt                   # Verified Python dependencies
├── cambc.toml                         # CAMBC SDK configuration file
├── DEPLOYMENT.md                      # Comprehensive cloud & VPS deployment guide
├── CONTRIBUTING.md                    # Contribution guidelines
├── SECURITY.md                        # Security policy & emergency procedures
└── LICENSE                            # MIT License
```

---

## 🛑 Emergency Stop Protocol

To immediately halt any running local agent, background worker, or cloud workflow without risk of corrupting state:

```bash
# Create emergency stop flag
touch EMERGENCY_STOP
```

```mermaid
sequenceDiagram
    autonumber
    actor Dev as 👤 Operator
    participant Agent as 🤖 Autonomous Loop
    participant Sentinel as 📄 EMERGENCY_STOP File
    participant Subprocess as ⚙️ Active Match / Compiler
    participant Git as 🌿 Git Candidate State

    Note over Agent: Continuous Phase Gate Check
    Agent->>Sentinel: Check file existence (matches/EMERGENCY_STOP)
    alt Sentinel Not Found (Normal Operation)
        Sentinel-->>Agent: Proceed
        Agent->>Subprocess: Execute benchmark or LLM candidate cycle
    else Sentinel Detected (Killswitch Engaged)
        Dev->>Sentinel: touch EMERGENCY_STOP
        Sentinel-->>Agent: Stop sentinel detected!
        Agent->>Subprocess: Send SIGTERM to running worker processes
        Agent->>Git: Clean uncommitted scratch worktrees safely
        Agent-->>Dev: Gracefully exit loop with Return Code 130
    end
```

To resume normal operations, simply remove the file:
```bash
rm EMERGENCY_STOP
```

---

## 🤝 Contributing

We welcome contributions, bug fixes, and tactical improvements! Please review our [**Contributing Guide**](./CONTRIBUTING.md) and [**Security Policy**](./SECURITY.md) before submitting pull requests.

1. Fork the Project
2. Create your Feature Branch (`git checkout -b feature/AmazingFeature`)
3. Ensure all tests pass (`python -m unittest tests/test_*.py`)
4. Commit your Changes (`git commit -m 'feat: Add AmazingFeature'`)
5. Push to the Branch (`git push origin feature/AmazingFeature`)
6. Open a Pull Request

---

## 📄 License

Distributed under the **MIT License**. See [`LICENSE`](./LICENSE) for full details.

<div align="center">
<sub>Crafted with precision for competitive autonomous bot battles.</sub>
</div>
