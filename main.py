import threading
import os

def run_api():
    from api import app
    port = int(os.environ.get("PORT", 8080))
    # Use threaded=True so Flask handles concurrent requests
    app.run(host="0.0.0.0", port=port, threaded=True)

# API in background thread
api_thread = threading.Thread(target=run_api, daemon=True)
api_thread.start()

# Bot on main thread
from bot import start
start()
