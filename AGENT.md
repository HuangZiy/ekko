# AGENT.md

## Build & Run

```bash
# Backend
pip install -r requirements.txt
python main.py

# Frontend
cd web && npm install && npm run build
```

## Commit Message Convention

This project follows [Conventional Commits](https://www.conventionalcommits.org/).

### Format

```
<type>(<scope>): <subject>

<body>
```

### Types

- `feat` — new feature
- `fix` — bug fix
- `chore` — maintenance (deps, config, tooling)
- `ci` — CI/CD changes
- `docs` — documentation only

### Rules

1. The commit message MUST describe the actual diff content, not copy a previous message
2. Unrelated changes MUST NOT be mixed into the same commit
3. Reference the issue ID in scope or footer (e.g. `feat(EKO-10):` or `Refs: EKO-10`)
4. Use imperative mood in the subject line ("add", not "added")

### Lessons Learned

- EKO-11: A commit (`32ecca9`) had its message copied from a prior code-splitting commit, but the actual diff was config parameter bumps and package-lock cleanup. Fixed via `git rebase -i` reword.
