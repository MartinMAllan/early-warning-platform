"""Assembles dashboard.html by injecting the real computed JSON bundle into
the HTML/CSS/JS template below. Run after etl.py and train_models.py.
"""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA = json.loads((HERE / "dashboard_data.json").read_text())

TEMPLATE = Path(HERE / "template.html").read_text()
html = TEMPLATE.replace("__DASHBOARD_DATA__", json.dumps(DATA))
(HERE / "dashboard.html").write_text(html, encoding="utf-8")
print("Wrote", HERE / "dashboard.html", "-", len(html), "bytes")
