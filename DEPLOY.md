# Deploying to DigitalOcean

This project deploys as a **single process on a single port**: FastAPI (`backend/main.py`) now serves both the REST API and the dashboard's static files (it redirects `/` to `/dashboard.html` and mounts `frontend/` directly). One service, one port, nothing else to wire up.

What actually needs to reach the server is small — the whole `Prototype/` folder is ~11 MB. The raw 433 MB `studentVle.csv` and the rest of the original OULAD dataset are **not** needed at runtime (only `output/*.json`, already computed, are read by the API) and must never go into the git repo.

---

## Can you push from GitHub, or from VS Code directly?

Both, and they're really the same path: **VS Code's Source Control panel pushes to GitHub for you** — there's no separate "VS Code deploy" mechanism for a plain Droplet. The flow is:

1. Push `Prototype/` to a GitHub repo (from VS Code's Source Control panel, or the terminal commands below).
2. The Droplet pulls from that GitHub repo when it boots, via the script in Step 2.

A Droplet has no built-in git integration of its own (that's what DigitalOcean's *App Platform* product offers — auto-deploy on push — but you've already started creating a Droplet, which is cheaper and fine for this). So GitHub is the handoff point either way.

### Push from VS Code
1. Open the `Prototype/` folder in VS Code (`File → Open Folder…`).
2. Source Control panel (left sidebar) → **Initialize Repository**.
3. Stage all changes (`+`), write a commit message, **Commit**.
4. **Publish Branch** → sign in to GitHub if prompted → choose **public** (see note below) → this creates the GitHub repo and pushes in one step.

### Push from the terminal
```bash
cd Prototype
git init
git add .
git commit -m "Early warning platform prototype"
gh repo create early-warning-platform --public --source=. --push   # needs GitHub CLI (gh), or:
# git remote add origin https://github.com/<you>/early-warning-platform.git
# git push -u origin main
```

**Public vs. private:** the boot script below does a plain `git clone`, which only works unauthenticated against a **public** repo. That's fine here — there's no real student data or secret in this repo, only anonymised OULAD derivatives and a demo JWT secret you'll rotate anyway (Step 4). If you'd rather keep it private, use a [fine-grained GitHub deploy token](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens) in the clone URL instead — flag it and I'll adjust the script.

---

## Step 1: Create the Droplet

Continue the Droplet creation screen you already had open:
- **Image:** Ubuntu 24.04 (LTS) x64
- **Size:** Basic, Regular, $6/mo (1 vCPU / 1 GB) — plenty for this app
- **Authentication:** SSH key (recommended) or password
- Leave **Additional Options → Startup scripts** enabled — that's the box you paste Step 2 into.

## Step 2: Paste this into the startup-script box

Edit the `REPO_URL` line first (and nothing else needs to change), then paste the whole thing into "Enter your scripts or data":

```bash
#!/bin/bash
set -e

# --- EDIT THIS ---
REPO_URL="https://github.com/<you>/early-warning-platform.git"
# ------------------

APP_DIR="/opt/early-warning-platform"

apt-get update -y
apt-get install -y python3-pip python3-venv git ufw

rm -rf "$APP_DIR"
git clone "$REPO_URL" "$APP_DIR"
cd "$APP_DIR/backend"

python3 -m venv venv
./venv/bin/pip install --upgrade pip
./venv/bin/pip install -r requirements.txt

# Random secret key each deploy - fine for a demo; set your own via the
# environment if you need stable tokens across restarts.
SECRET_KEY_VALUE=$(python3 -c "import secrets; print(secrets.token_hex(32))")

cat > /etc/systemd/system/earlywarning.service <<EOF
[Unit]
Description=Early Warning Platform API + Dashboard
After=network.target

[Service]
User=root
WorkingDirectory=$APP_DIR/backend
Environment=SECRET_KEY=$SECRET_KEY_VALUE
ExecStart=$APP_DIR/backend/venv/bin/python -m uvicorn main:app --host 0.0.0.0 --port 80
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable earlywarning
systemctl start earlywarning

ufw allow 22/tcp
ufw allow 80/tcp
ufw --force enable
```

Click **Create Droplet**. Boot + provisioning takes about 1–2 minutes.

## Step 3: Open it

Visit `http://<your-droplet-ip>/` — that's the dashboard. `http://<your-droplet-ip>/docs` is the live Swagger API explorer.

If it's not up yet, SSH in and check the service:
```bash
ssh root@<your-droplet-ip>
systemctl status earlywarning
journalctl -u earlywarning -n 50 --no-pager
```

## Redeploying after you change code

```bash
ssh root@<your-droplet-ip>
cd /opt/early-warning-platform
git pull
cd backend && ./venv/bin/pip install -r requirements.txt   # only if requirements.txt changed
systemctl restart earlywarning
```

## Optional: a real domain + HTTPS

Point the domain's A record at the Droplet's IP, then install [Caddy](https://caddyserver.com/) as a reverse proxy in front of port 80 — it gets you free auto-renewing HTTPS with a two-line Caddyfile (`yourdomain.com { reverse_proxy localhost:8000 }`, after moving uvicorn to port 8000). Ask if you want this scripted too; it's a small addition once you have a domain to point.

## What this setup deliberately doesn't do

This is sized for a demo, not a production institutional deployment:
- Runs as `root` and binds port 80 directly — fine for one low-traffic droplet, not for anything handling real student data.
- No database — still reads the same JSON/CSV artefacts the local prototype uses (see `COMPLETION_PLAN.md` §3.3 for the PostgreSQL work still outstanding).
- No HTTPS out of the box (see above).
- `SECRET_KEY` is regenerated on every redeploy, which invalidates existing JWTs — fine here since there's no persistent login state, but set a fixed one via the systemd `Environment=` line if that ever matters.
