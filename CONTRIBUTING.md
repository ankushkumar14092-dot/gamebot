# Contributing to CAMBC GameBot

Thank you for your interest in improving the CAMBC GameBot Autonomous Intelligence system! We welcome contributions ranging from bot tactical improvements to cloud workflow optimizations.

---

## 🛠️ Development Setup

1. **Fork and Clone:**
   ```bash
   git clone https://github.com/ankushkumar14092-dot/gamebot.git
   cd gamebot
   ```

2. **Set up Python Virtual Environment:**
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install --upgrade pip
   pip install -r requirements.txt
   ```

3. **Verify Environment with Unit Tests:**
   ```bash
   python -m unittest tests/test_cambc_adapter.py \
                      tests/test_agent_reports.py \
                      tests/test_gemini_retry.py \
                      tests/test_improve_bot.py -v
   ```

---

## 🌿 Branching & Workflow Guidelines

- **Protected Main:** The `main` branch is protected and always reflects verified, passing code.
- **Feature Branches:** Use descriptive branch names:
  - `feature/<description>` for new capabilities
  - `fix/<description>` for bug fixes
  - `bot/<strategy-name>` for bot algorithmic candidate experiments
  - `docs/<description>` for documentation improvements

---

## 🧪 Testing Requirements

Before opening a pull request, verify that:
1. All unit tests pass:
   ```bash
   python -m unittest tests/test_*.py -v
   ```
2. Any bot C++ modifications compile cleanly via the CAMBC CLI:
   ```bash
   cambc build bots/submission-v6 --release
   ```
3. No secrets or API keys are committed in code, configs, or test fixtures.

---

## 📝 Commit Conventions

We follow the [Conventional Commits](https://www.conventionalcommits.org/) specification:

- `feat:` A new feature or capability
- `fix:` A bug fix or CI repair
- `docs:` Documentation changes
- `refactor:` Code refactoring without behavior changes
- `test:` Adding or improving test cases
- `chore:` Routine maintenance or dependency updates

**Example:**
```bash
git commit -m "feat(agent): add adaptive gem threshold based on opponent distance"
```

---

## 📬 Submitting a Pull Request

1. Push your branch to GitHub.
2. Open a Pull Request targeting the `main` branch.
3. Fill out the [Pull Request Template](.github/pull_request_template.md).
4. Verify that all GitHub Actions CI checks turn green.
