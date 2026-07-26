SECRET_KEY_VALUE=$(python3 -c "import secrets; print(secrets.token_hex(32))")

cat > /etc/systemd/system/earlywarning.service <<EOF
[Unit]
Description=Early Warning Platform API + Dashboard
After=network.target

[Service]
User=root
WorkingDirectory=/opt/early-warning-platform/backend
Environment=SECRET_KEY=$SECRET_KEY_VALUE
ExecStart=/opt/early-warning-platform/backend/venv/bin/python -m uvicorn main:app --host 0.0.0.0 --port 80
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