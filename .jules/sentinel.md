## 2026/10/29 - Prevent Bearer Token Leakage and SSRF in Attachment Downloads

**Vulnerability:** In `ConfluenceClient.download_attachment`, passing an absolute URL targeting an external host or untrusted IP (e.g. `https://attacker.com` or `http://169.254.169.254`) caused `requests.Session` to send the HTTP request with the `Authorization: Bearer <token>` header intact, leaking API tokens to external hosts and allowing SSRF.

**Learning:** When API responses include URL links (like `_links.download`), directly fetching those URLs using an authenticated HTTP session without verifying that the target host matches the configured API `base_url` exposes credentials to third parties.

**Prevention:** Always validate target URL hosts using `urllib.parse.urlparse` before executing authenticated requests against endpoints specified in dynamic API metadata.
