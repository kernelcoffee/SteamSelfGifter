"""Integration tests against mocked external HTTP services.

Unlike tests/integration (which needs --run-integration and real
credentials), these run unconditionally, in CI included: the real client
code talks through httpx.MockTransport to canned SteamGifts/Steam
responses, exercising cookies, headers, form encoding, retries, and
parsing end to end without touching the network.
"""
