import logging
import time
from typing import Dict, List, Optional

import requests

logger = logging.getLogger(__name__)


def _safe_request_exception(
    error: requests.exceptions.RequestException, message: str
) -> requests.exceptions.RequestException:
    """URLや応答本文を引き継がず、例外分類に必要なステータスだけを保持する."""
    response = None
    if error.response is not None:
        response = requests.Response()
        response.status_code = error.response.status_code
        message += f" (HTTP {response.status_code})"
    if isinstance(error, requests.exceptions.HTTPError):
        return requests.exceptions.HTTPError(message, response=response)
    return requests.exceptions.RequestException(message, response=response)


class ConfluenceClient:
    """Confluence Data Center REST APIとの通信を担当するクライアントクラス.

    Bearer認証、Proxy経由の接続、および一時的なエラーに対するリトライロジックを実装。
    """

    def __init__(self, base_url: str, token: str, proxy: Optional[str] = None):
        self.base_url = base_url
        self.headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
        self.proxies = None
        if proxy:
            self.proxies = {"http": proxy, "https": proxy}
        self.session = requests.Session()
        self.session.headers.update(self.headers)
        if self.proxies:
            self.session.proxies.update(self.proxies)

    def _request(
        self, method: str, path: str, params: Optional[Dict] = None, retries: int = 3, backoff: float = 2.0
    ) -> Dict:
        """共通のリクエスト処理.

        5xxエラーやネットワークエラーに対して指数バックオフを伴うリトライを行う。
        """
        url = f"{self.base_url}{path}"
        for i in range(retries):
            try:
                response = self.session.request(method, url, params=params, timeout=30)
                if response.status_code == 200:
                    return response.json()
                elif 500 <= response.status_code < 600:
                    logger.warning(
                        f"サーバーエラー {response.status_code} が発生しました。再試行中 ({i + 1}/{retries})..."
                    )
                    time.sleep(backoff * (2**i))
                    continue
                else:
                    response.raise_for_status()
            except requests.exceptions.RequestException as error:
                if i == retries - 1:
                    raise _safe_request_exception(error, "Confluence API リクエストに失敗しました") from None
                logger.warning(f"リクエストが失敗しました。再試行中 ({i + 1}/{retries})...")
                time.sleep(backoff * (2**i))

        raise Exception("Confluence API リクエストに失敗しました")

    def get_page(self, page_id: str, expand: str = "body.storage,space") -> Dict:
        """指定されたページIDの情報を取得する.

        既定値 expand="body.storage,space" により既存呼び出しの後方互換性を保持する。
        """
        path = f"/rest/api/content/{page_id}"
        params = {"expand": expand}
        return self._request("GET", path, params=params)

    def get_child_pages(self, page_id: str, limit: int = 25) -> List[Dict]:
        """指定されたページの子ページ一覧を取得する.

        大規模なツリーに対応するため、内部でページング処理を完結させて全件を返す。
        """
        path = f"/rest/api/content/{page_id}/child/page"
        children = []
        start = 0
        while True:
            params = {"limit": limit, "start": start}
            data = self._request("GET", path, params=params)
            results = data.get("results", [])
            children.extend(results)

            # 結果がlimit未満であれば全件取得完了と判断
            if len(results) < limit:
                break
            start += len(results)

        return children

    def get_attachments(self, page_id: str, limit: int = 50) -> List[Dict]:
        """指定されたページの添付ファイル一覧を取得する.

        `expand=extensions,version` を付与し、内部でページング処理を行って全件取得する。
        """
        path = f"/rest/api/content/{page_id}/child/attachment"
        attachments = []
        start = 0
        while True:
            params = {"limit": limit, "start": start, "expand": "extensions,version"}
            data = self._request("GET", path, params=params)
            results = data.get("results", [])
            attachments.extend(results)

            if len(results) < limit:
                break
            start += len(results)

        return attachments

    def get_restrictions(self, page_id: str) -> Dict:
        """指定されたページのコンテンツ制限（byOperation）情報を取得する."""
        path = f"/rest/api/content/{page_id}/restriction/byOperation"
        return self._request("GET", path)

    def get_space_root_pages(self, space_key: str, limit: int = 25) -> List[Dict]:
        """指定されたSpaceのトップレベル（ルート）ページ一覧を取得する.

        `/rest/api/space/{space_key}/content/page?depth=root` をページングで全件取得する。
        """
        path = f"/rest/api/space/{space_key}/content/page"
        root_pages = []
        start = 0
        while True:
            params = {"depth": "root", "limit": limit, "start": start}
            data = self._request("GET", path, params=params)
            results = data.get("results", [])
            root_pages.extend(results)

            if len(results) < limit:
                break
            start += len(results)

        return root_pages

    def download_attachment(
        self,
        download_path: str,
        dest_file: str,
        max_bytes: Optional[int] = None,
        retries: int = 3,
        backoff: float = 2.0,
    ) -> int:
        """添付バイナリをストリーミングダウンロードして保存する.

        Args:
            download_path: `_links.download` 等のダウンロード用パス (コンテキスト相対または絶対URL)
            dest_file: 保存先ローカルファイルパス
            max_bytes: 単一ファイルの許容最大バイト数 (到達時に即時停止して削除・例外発生)
            retries: リトライ回数
            backoff: 指数バックオフの係数

        Returns:
            保存されたファイルのバイト数

        Raises:
            ValueError: `max_bytes` を超えた場合
            requests.exceptions.RequestException: ダウンロード失敗時
        """
        import os

        if download_path.startswith("http://") or download_path.startswith("https://"):
            url = download_path
        else:
            url = f"{self.base_url}{download_path}"

        for i in range(retries):
            try:
                response = self.session.get(url, stream=True, timeout=60)
                if response.status_code == 200:
                    written_bytes = 0
                    os.makedirs(os.path.dirname(os.path.abspath(dest_file)), exist_ok=True)
                    try:
                        with open(dest_file, "wb") as f:
                            for chunk in response.iter_content(chunk_size=8192):
                                if chunk:
                                    written_bytes += len(chunk)
                                    if max_bytes is not None and written_bytes > max_bytes:
                                        f.close()
                                        if os.path.exists(dest_file):
                                            os.remove(dest_file)
                                        raise ValueError(
                                            f"単一ファイルサイズ上限 ({max_bytes} バイト) を超過したためダウンロードを中断しました"
                                        )
                                    f.write(chunk)
                        return written_bytes
                    except Exception:
                        if os.path.exists(dest_file):
                            os.remove(dest_file)
                        raise
                elif 500 <= response.status_code < 600:
                    logger.warning(
                        f"サーバーエラー {response.status_code} が発生しました。再試行中 ({i + 1}/{retries})..."
                    )
                    time.sleep(backoff * (2**i))
                    continue
                else:
                    response.raise_for_status()
            except ValueError:
                raise
            except requests.exceptions.RequestException as error:
                if i == retries - 1:
                    raise _safe_request_exception(error, "添付ファイルのダウンロードに失敗しました") from None
                logger.warning(f"添付ダウンロードリクエストが失敗しました。再試行中 ({i + 1}/{retries})...")
                time.sleep(backoff * (2**i))

        raise requests.exceptions.RequestException("添付ファイルのダウンロードに失敗しました")
