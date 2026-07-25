#!/bin/bash
# DigitalOcean Droplet startup script (cloud-init "user data") for the
# Early Warning Platform. Paste this whole file into the "Enter your scripts
# or data" box during Droplet creation - it runs once, automatically, on
# first boot. See DEPLOY.md for the full walkthrough.
#
# It clones the repo, installs the backend's Python dependencies, and runs
# FastAPI (which also serves the dashboard's static files) as a systemd
# service on port 80, restarting automatically if it ever crashes.
set -e

# --- EDIT THIS: your GitHub repo URL (must be public - see DEPLOY.md) ---
REPO_URL="https://github.com/<you>/early-warning-platform.git"
# --------------------------------------------------------------------------

APP_DIR="/opt/early-warning-platform"

apt-get update -y
apt-get install -y python3-pip python3-venv git ufw

rm -rf "$APP_DIR"
git clone "$REPO_URL" "$APP_DIR"
cd "$APP_DIR/backend"

python3 -m venv venv
./venv/bin/pip install --upgrade pip
./venv/bin/pip install -r requirements.txt

# Random secret key each deploy - fine for a demo; set your own below if you
# need JWTs to survive a redeploy.
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

echo "Early Warning Platform deployed. Visit http://$(curl -s -4 ifconfig.me)/ once this finishes."
