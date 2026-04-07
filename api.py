from flask import Flask, request, jsonify
import json
import os

app = Flask(__name__)

# ── Storage: flat JSON file (Railway has an ephemeral filesystem, so we
#    use a path that survives redeploys by mounting a Railway Volume,
#    or swap DATA_FILE for a real DB later). ──────────────────────────────
DATA_FILE  = os.environ.get("DATA_FILE", "/data/links.json")
API_SECRET = os.environ.get("API_SECRET", "changeme")   # set this in Railway vars

def _load() -> dict:
    try:
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"discord_links": {}, "hwids": {}}

def _save(data: dict) -> None:
    os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
    with open(DATA_FILE, "w") as f:
        json.dump(data, f)

def _auth(req) -> bool:
    return req.headers.get("X-API-Secret") == API_SECRET

# ── Routes ────────────────────────────────────────────────────────────────

@app.route("/check/<hwid>", methods=["GET"])
def check_hwid(hwid: str):
    """
    Called by the C++ client every 30 s.
    Returns {"linked": true/false}  – no auth required (public, read-only).
    hwid is the raw 12-char code (no dashes).
    """
    hwid = hwid.upper().strip()
    data = _load()
    linked = hwid in data.get("hwids", {})
    return jsonify({"linked": linked})

@app.route("/link", methods=["POST"])
def link_device():
    """
    Called by the Discord bot to link a discord_id → hwid.
    Body: {"discord_id": "...", "hwid": "..."}
    Returns: {"ok": true} or {"error": "..."}
    """
    if not _auth(request):
        return jsonify({"error": "unauthorized"}), 401

    body       = request.get_json(force=True)
    discord_id = str(body.get("discord_id", "")).strip()
    hwid       = str(body.get("hwid", "")).upper().strip()

    if not discord_id or len(hwid) != 12:
        return jsonify({"error": "bad_request"}), 400

    data = _load()

    # Already linked to a different HWID?
    if discord_id in data["discord_links"]:
        return jsonify({"error": "already_linked",
                        "hwid": data["discord_links"][discord_id]}), 409

    # HWID claimed by someone else?
    if hwid in data["hwids"] and data["hwids"][hwid] != discord_id:
        return jsonify({"error": "hwid_taken"}), 409

    data["discord_links"][discord_id] = hwid
    data["hwids"][hwid]               = discord_id
    _save(data)
    return jsonify({"ok": True})

@app.route("/change", methods=["POST"])
def change_device():
    """
    Called by the Discord bot to change a discord_id's HWID.
    Body: {"discord_id": "...", "new_hwid": "..."}
    """
    if not _auth(request):
        return jsonify({"error": "unauthorized"}), 401

    body       = request.get_json(force=True)
    discord_id = str(body.get("discord_id", "")).strip()
    new_hwid   = str(body.get("new_hwid",   "")).upper().strip()

    if not discord_id or len(new_hwid) != 12:
        return jsonify({"error": "bad_request"}), 400

    data = _load()

    # New HWID taken by someone else?
    if new_hwid in data["hwids"] and data["hwids"][new_hwid] != discord_id:
        return jsonify({"error": "hwid_taken"}), 409

    # Remove old reverse entry
    old_hwid = data["discord_links"].get(discord_id)
    if old_hwid and old_hwid in data["hwids"]:
        del data["hwids"][old_hwid]

    data["discord_links"][discord_id] = new_hwid
    data["hwids"][new_hwid]           = discord_id
    _save(data)
    return jsonify({"ok": True, "old_hwid": old_hwid or ""})

@app.route("/unlink", methods=["POST"])
def unlink_device():
    """
    Called by the Discord bot (admin command) to force-unlink a user.
    Body: {"discord_id": "..."}
    """
    if not _auth(request):
        return jsonify({"error": "unauthorized"}), 401

    body       = request.get_json(force=True)
    discord_id = str(body.get("discord_id", "")).strip()

    data    = _load()
    old_hwid = data["discord_links"].pop(discord_id, None)
    if old_hwid:
        data["hwids"].pop(old_hwid, None)
        _save(data)
        return jsonify({"ok": True, "removed_hwid": old_hwid})
    return jsonify({"ok": False, "error": "not_found"}), 404

@app.route("/status/<discord_id>", methods=["GET"])
def status(discord_id: str):
    """Check what HWID a discord_id is linked to. Auth required."""
    if not _auth(request):
        return jsonify({"error": "unauthorized"}), 401
    data = _load()
    hwid = data["discord_links"].get(discord_id)
    if hwid:
        return jsonify({"linked": True, "hwid": hwid})
    return jsonify({"linked": False})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
