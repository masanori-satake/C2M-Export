import requests
import time
import logging
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)

class ConfluenceClient:
    def __init__(self, base_url: str, token: str, proxy: Optional[str] = None):
        self.base_url = base_url
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json"
        }
        self.proxies = None
        if proxy:
            self.proxies = {
                "http": proxy,
                "https": proxy
            }
        self.session = requests.Session()
        self.session.headers.update(self.headers)
        if self.proxies:
            self.session.proxies.update(self.proxies)

    def _request(self, method: str, path: str, params: Optional[Dict] = None, retries: int = 3, backoff: float = 2.0) -> Dict:
        url = f"{self.base_url}{path}"
        for i in range(retries):
            try:
                response = self.session.request(method, url, params=params, timeout=30)
                if response.status_code == 200:
                    return response.json()
                elif 500 <= response.status_code < 600:
                    logger.warning(f"Server error {response.status_code} for {url}. Retrying ({i+1}/{retries})...")
                    time.sleep(backoff * (2 ** i))
                    continue
                else:
                    response.raise_for_status()
            except requests.exceptions.RequestException as e:
                if i == retries - 1:
                    raise
                logger.warning(f"Request failed: {e}. Retrying ({i+1}/{retries})...")
                time.sleep(backoff * (2 ** i))

        raise Exception(f"Failed to fetch {url} after {retries} retries")

    def get_page(self, page_id: str) -> Dict:
        """
        GET /rest/api/content/{id}?expand=body.storage,space
        """
        path = f"/rest/api/content/{page_id}"
        params = {"expand": "body.storage,space"}
        return self._request("GET", path, params=params)

    def get_child_pages(self, page_id: str, limit: int = 25) -> List[Dict]:
        """
        GET /rest/api/content/{id}/child/page?limit=N&start=S
        """
        path = f"/rest/api/content/{page_id}/child/page"
        children = []
        start = 0
        while True:
            params = {"limit": limit, "start": start}
            data = self._request("GET", path, params=params)
            results = data.get("results", [])
            children.extend(results)

            if len(results) < limit:
                break
            start += len(results)

        return children
