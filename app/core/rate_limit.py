from slowapi import Limiter

from app.core.client_ip import client_ip

# Keyed by the caller's address, which behind a trusted proxy is the real
# client rather than the proxy (app/core/client_ip.py).
limiter = Limiter(key_func=client_ip, default_limits=["60/minute"])
