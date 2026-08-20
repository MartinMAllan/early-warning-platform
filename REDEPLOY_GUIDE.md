# Configuration drift & redeploy guide

Answers three questions: what's drifted from `startup-script.sh`'s original
design, how to compare local vs. the Droplet yourself, and how to get the
Droplet serving what's in this working tree now. Nothing here has been run
against the Droplet — you're already SSH'd into it; I only have the local
repo. Treat this as a checklist to run yourself.

---

## 1. What's actually drifted

There are two separate kinds of drift, and they compound.

### 1a. `startup-script.sh` lost its provisioning half

The file as first committed (`eea7d43`) did four things: install
Python/git/ufw, `git clone` the repo, create a venv and `pip install`, *then*
write the systemd unit and open the firewall. The version in the repo now
only does the last part:

```diff
- apt-get update -y
- apt-get install -y python3-pip python3-venv git ufw
- rm -rf "$APP_DIR"
- git clone "$REPO_URL" "$APP_DIR"
- cd "$APP_DIR/backend"
- python3 -m venv venv
- ./venv/bin/pip install --upgrade pip
- ./venv/bin/pip install -r requirements.txt
-
  SECRET_KEY_VALUE=$(python3 -c "import secrets; print(secrets.token_hex(32))")
  cat > /etc/systemd/system/earlywarning.service <<EOF
  ...
```

Practical effect: **if you paste today's `startup-script.sh` into a brand
new Droplet's startup-script box, it will fail** — the systemd unit points
at `/opt/early-warning-platform/backend/venv/bin/python`, but nothing in the
current script creates that directory, clones the repo, or builds the venv
anymore. It only works as a "reapply the systemd service" script on a box
that's already been provisioned by hand — which is presumably how the
current Droplet got set up (the provisioning steps were run once,
interactively, and never made it back into the committed file).

`DEPLOY.md` Step 2 still describes the *original* four-part script, so the
doc and the file it points to are now out of sync too.

**Fix, if you want fresh-Droplet provisioning to work again:** restore the
`apt-get`/`git clone`/venv block above `SECRET_KEY_VALUE=...` in
`startup-script.sh`. Not required for redeploying to the *existing* Droplet
(section 3 below) — only matters the next time you spin up a new one.

### 1b. The Droplet is running code that was never committed

`backend/main.py` has only ever been touched in one commit
(`2294d0a`, the initial commit) — it has **never been modified since**, and
none of this session's changes to it have been committed. Compare what's
deployed (what you pasted) to the working tree:

| | Deployed (Droplet) | Local working tree now |
|---|---|---|
| Role values | `"administrator"`, `"advisor"`, `"module_leader"` | `"admin"`, `"advisor"`, `"module_leader"` |
| Student routes | `GET /students`, `GET /students/{id}/risk` | `GET /api/students`, `GET /api/students/{id}` |
| Cohort route | `GET /cohort/overview` | `GET /api/cohort` |
| Interventions | `POST /interventions`, `GET /interventions/{id}` | `POST /api/interventions`, `GET /api/interventions/{id}` |
| `StudentRisk` fields | 6 fields (id, module, presentation, score, band, top_factors) | + gender, region, education, age_band, prior attempts, credits, submission rate, mean score, active days, early clicks, final_result (redacted for advisor) |
| `InterventionCreate` field | `id_student` | `student_id` |
| DB schema | none | `backend/database.py` + `backend/models.py` (SQLAlchemy, untracked) |
| Load test | none | `backend/locustfile.py` (untracked) |
| Frontend auth | none (static demo data only) | real login against `/auth/token`, live-fetched student data, role-gated API Explorer |

So the live site at `http://137.184.145.221/` is still serving the
**original, day-one API contract** — none of this session's work (or, going
by the single-commit history of `main.py`, any backend work since project
start) has reached it. `git status` locally confirms this is all
uncommitted:

```
 M backend/main.py            M frontend/dashboard.html
?? backend/database.py        M frontend/dashboard_data.json
?? backend/models.py          M frontend/template.html
?? backend/locustfile.py       ?? tests/
```

---

## 2. How to compare, yourself

Run the left column on the Droplet, the right column locally, and diff.

| Check | On the Droplet (SSH'd in) | Locally |
|---|---|---|
| Which commit is deployed | `cd /opt/early-warning-platform && git log -1 --oneline` | `git log -1 --oneline` |
| Uncommitted local changes | — | `git status` / `git diff` |
| Backend contract | `cat backend/main.py` (or `curl localhost/docs`, `curl localhost/openapi.json \| python3 -m json.tool`) | `cat backend/main.py` |
| Installed packages vs. lockfile | `backend/venv/bin/pip freeze` vs. `cat backend/requirements.txt` | `pip freeze` vs. `cat backend/requirements.txt` |
| What's actually running | `systemctl cat earlywarning` (shows the live unit file, including `ExecStart` and `SECRET_KEY`) | `cat startup-script.sh` (shows what the unit *should* be, minus the provisioning half per §1a) |
| Service health | `systemctl status earlywarning`; `journalctl -u earlywarning -n 50 --no-pager` | `curl http://127.0.0.1:8000/health` against your own local run |
| Live vs. local API behaviour | `curl http://137.184.145.221/health`, `curl -X POST 'http://137.184.145.221/auth/token?username=x&role=administrator'` | same against `http://127.0.0.1:8000` — note the role value differs today, see §1b |

Fastest single check: `git log -1 --oneline` in both places. If they match,
the code is in sync; if not, the SHAs tell you exactly how far apart they
are. Right now they won't match anything meaningful because the interesting
changes were never committed at all — `git status` locally is the real
source of truth until that changes.

---

## 3. Commit locally, then redeploy

### Step 0 — decide what should and shouldn't go into a public repo

`origin` is `https://github.com/MartinMAllan/early-warning-platform.git`,
and per `DEPLOY.md` it **must stay public** for the Droplet's unauthenticated
`git clone` to keep working. Before staging everything, look at:

- **`tests/Usability Evaluation Questionnaire – Early Warning Platform (Responses).xlsx`** —
  real respondents' role descriptions and free-text comments. No names in
  the columns, but it's still real participant data going into a public
  repo. Decide if that's fine as-is, or if it should be trimmed/anonymised
  further, or kept out of git and deployed separately (e.g. `scp`'d directly
  to the Droplet instead of committed).
- **`.claude/`** — Claude Code's local tool config, not part of the app.
  Probably belongs in `.gitignore`, not in the commit.
- **`~$DEPLOY.md`** — a stray Word lock file that leaked into a previous
  commit; already shows as deleted (`D`) in `git status`, so committing now
  removes it. Good to include.
- Large already-tracked binaries (`output/attrition_risk_model.joblib` ~4.2 MB,
  `output/processed_student_data.csv` ~6.1 MB) aren't read by `backend/main.py`
  at runtime at all (it only reads `output/*.json`) — pre-existing bloat, not
  new, not blocking, just worth knowing.

### Step 1 — review and stage

```bash
git status
git diff                       # skim the real code changes
git add backend/ frontend/ data_engineering/ modelling/ output/ \
        tests/ COMPLETION_PLAN.md DATA_LINEAGE.md
git add -u '~$DEPLOY.md'       # stages the deletion
# leave .claude/ out, or add it to .gitignore first:
echo ".claude/" >> .gitignore
git add .gitignore
```

### Step 2 — commit and push

```bash
git commit -m "Real JWT auth end-to-end, server-sourced student data, SQLAlchemy schema, usability study"
git push origin main
```

### Step 3 — pull and restart on the Droplet

```bash
ssh root@137.184.145.221
cd /opt/early-warning-platform
git pull
cd backend && ./venv/bin/pip install -r requirements.txt   # no-op today, requirements.txt is unchanged — safe to run anyway
systemctl restart earlywarning
systemctl status earlywarning        # confirm it's active (running)
```

Nothing here changes `SECRET_KEY` — it's fixed in the systemd unit's
`Environment=` line from whenever the service was first provisioned, and a
`restart` doesn't touch it. Existing JWTs (if any were issued) stay valid
across this redeploy.

### Step 4 — verify

```bash
curl http://137.184.145.221/health
curl -s http://137.184.145.221/openapi.json | python3 -m json.tool | grep '"/api'
```

The second command should now list `/api/students`, `/api/cohort`, etc. —
if it still shows the old `/students`, `/cohort/overview` paths, the pull or
restart didn't take; re-check `git log -1` and `systemctl status` on the
Droplet. Then open `http://137.184.145.221/dashboard.html` in a browser and
confirm sign-in works and the sidebar dots match what you see locally.

---

## Note on the breaking API change

Because the deployed contract is jumping straight from the original
`/students` + `"administrator"` shape to `/api/students` + `"admin"` in one
push (nothing incremental was ever deployed in between), anything that was
built against the *old* live API — a bookmark, a saved Postman request, a
separate client — breaks at that point. Given `COMPLETION_PLAN.md` records
that no real external consumer exists yet beyond this dashboard, that's
almost certainly fine, but worth being aware of before pushing.
