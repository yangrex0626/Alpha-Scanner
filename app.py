"""Flask web dashboard for the Altcoin Alpha Scanner / 潛力幣種篩選器.

Run:  python app.py    then open http://127.0.0.1:5000

Results are cached for CACHE_TTL seconds so refreshing the page doesn't hammer
the APIs.  Hit "重新掃描" or /api/scan?refresh=1 to force a rescan.
"""
from __future__ import annotations

import threading
import time

from flask import Flask, jsonify, render_template, request

from screener import engine

app = Flask(__name__)

CACHE_TTL = 180  # seconds
_cache = {"data": None, "ts": 0}
_lock = threading.Lock()


def get_data(top_n=None, enrich=True, refresh=False):
    with _lock:
        fresh = _cache["data"] and (time.time() - _cache["ts"] < CACHE_TTL)
        if fresh and not refresh:
            return _cache["data"]
        data = engine.run(top_n=top_n, enrich=enrich)
        _cache["data"] = data
        _cache["ts"] = time.time()
        return data


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/scan")
def scan():
    top_n = request.args.get("top", type=int)
    enrich = request.args.get("enrich", "1") != "0"
    refresh = request.args.get("refresh") == "1"
    data = get_data(top_n=top_n, enrich=enrich, refresh=refresh)
    data = dict(data)
    data["cached_age"] = int(time.time() - _cache["ts"])
    return jsonify(data)


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
