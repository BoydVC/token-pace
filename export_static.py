#!/usr/bin/env python3
"""Write dist/token-pace-snapshot.html: one offline file with pace JSON inlined (file:// safe)."""
import os

HERE = os.path.dirname(os.path.abspath(__file__))
html = open(os.path.join(HERE, "web", "index.html"), encoding="utf-8").read()
data = open(os.path.join(HERE, "data", "pace.json"), encoding="utf-8").read().replace("</", "<\\/")
html = html.replace("<script>", f"<script>window.__DATA__={data};</script>\n<script>", 1)
os.makedirs(os.path.join(HERE, "dist"), exist_ok=True)
out = os.path.join(HERE, "dist", "token-pace-snapshot.html")
open(out, "w", encoding="utf-8").write(html)
print("wrote", out, os.path.getsize(out), "bytes")
