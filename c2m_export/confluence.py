import logging
import time
from typing import Dict, List, Optional

import requests

logger = logging.getLogger(__name__)


def _extract_next_start(data: Dict, current_start: int, current_count: int) -> Optional[int]:
    """レスポンスの _links.next から次ページの start オフセットを取得する.

    次ページが存在しない場合は None を返す。
    """
    if not isinstance(data, dict):
        return None
    links = data.get("_links")
    if not isinstance(links, dict):
        return None
    next_link = links.get("next")
    if not next_link or not isinstance(next_link, str):
        return None

    if "start=" in next_link:
        from urllib.parse import parse_qs, urlparse

        parsed = urlparse(next_link)
        qs = parse_qs(parsed.query)
        start_vals = qs.get("start", [])
        if start_vals and start_vals[0].isdigit():
            next_start = int(start_vals[0])
            if next_start != current_start:
                return next_start

    if current_count > 0:
        return current_start + current_count
    return None


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

        429・5xxエラーやネットワークエラーは指数バックオフで再試行し、401・403・404は即時失敗する。
        """
        url = f"{self.base_url}{path}"
        for i in range(retries):
            try:
                response = self.session.request(method, url, params=params, timeout=30)
                if response.status_code == 200:
                    return response.json()
                elif 500 <= response.status_code < 600 and i < retries - 1:
                    logger.warning(
                        f"サーバーエラー {response.status_code} が発生しました。再試行中 ({i + 1}/{retries})..."
                    )
                    time.sleep(backoff * (2**i))
                    continue
                else:
                    response.raise_for_status()
            except requests.exceptions.RequestException as error:
                if i == retries - 1 or (
                    isinstance(error, requests.exceptions.HTTPError)
                    and error.response is not None
                    and error.response.status_code in (401, 403, 404)
                ):
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
            results = data.get("results", []) if isinstance(data, dict) else []
            children.extend(results)

            next_start = _extract_next_start(data, start, len(results))
            if next_start is None:
                break
            start = next_start

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
            results = data.get("results", []) if isinstance(data, dict) else []
            attachments.extend(results)

            next_start = _extract_next_start(data, start, len(results))
            if next_start is None:
                break
            start = next_start

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
            results = data.get("results", []) if isinstance(data, dict) else []
            root_pages.extend(results)

            next_start = _extract_next_start(data, start, len(results))
            if next_start is None:
                break
            start = next_start

        return root_pages

    # --- 全体把握フェーズ (A/C/D) API メソッド ---

    def list_spaces(
        self,
        type_: Optional[str] = None,
        status: Optional[str] = None,
        label: Optional[str] = None,
        content_label: Optional[str] = None,
        expand: Optional[str] = None,
        limit: int = 25,
    ) -> List[Dict]:
        """参照可能なSpace一覧を全件取得する (`GET /rest/api/space`)."""
        path = "/rest/api/space"
        spaces = []
        start = 0
        while True:
            params: Dict[str, object] = {"limit": limit, "start": start}
            if type_:
                params["type"] = type_
            if status:
                params["status"] = status
            if label:
                params["label"] = label
            if content_label:
                params["contentLabel"] = content_label
            if expand:
                params["expand"] = expand

            data = self._request("GET", path, params=params)
            results = data.get("results", []) if isinstance(data, dict) else []
            spaces.extend(results)

            next_start = _extract_next_start(data, start, len(results))
            if next_start is None:
                break
            start = next_start

        return spaces

    def get_space(self, space_key: str, expand: Optional[str] = None) -> Dict:
        """指定されたSpaceのメタデータを取得する (`GET /rest/api/space/{spaceKey}`)."""
        path = f"/rest/api/space/{space_key}"
        params = {}
        if expand:
            params["expand"] = expand
        return self._request("GET", path, params=params if params else None)

    def get_space_labels(self, space_key: str) -> Dict:
        """指定されたSpaceのラベル情報を取得する (`GET /rest/api/space/{spaceKey}/labels`)."""
        path = f"/rest/api/space/{space_key}/labels"
        return self._request("GET", path)

    def get_descendant_page_count(self, page_id: str) -> Dict:
        """指定されたページの子孫ページ総数を取得する (`GET /rest/api/content/{id}/descendant/page/count`)."""
        path = f"/rest/api/content/{page_id}/descendant/page/count"
        return self._request("GET", path)

    def scan_content(
        self,
        space_key: str,
        type_: str = "page",
        status: Optional[str] = None,
        expand: Optional[str] = None,
        cursor: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict]:
        """カーソルページングでSpace配下のコンテンツを全件列挙する (`GET /rest/api/content/scan`)."""
        path = "/rest/api/content/scan"
        items = []
        current_cursor = cursor
        while True:
            params: Dict[str, object] = {"spaceKey": space_key, "type": type_, "limit": limit}
            if status:
                params["status"] = status
            if expand:
                params["expand"] = expand
            if current_cursor:
                params["cursor"] = current_cursor

            data = self._request("GET", path, params=params)
            results = data.get("results", []) if isinstance(data, dict) else []
            items.extend(results)

            next_link = (
                data.get("_links", {}).get("next")
                if isinstance(data, dict) and isinstance(data.get("_links"), dict)
                else None
            )
            if not next_link:
                break

            if "cursor=" in next_link:
                from urllib.parse import parse_qs, urlparse

                parsed = urlparse(next_link)
                qs = parse_qs(parsed.query)
                cursor_vals = qs.get("cursor", [])
                if cursor_vals:
                    current_cursor = cursor_vals[0]
                else:
                    break
            else:
                break

        return items

    def get_descendants(
        self, page_id: str, type_: str = "page", expand: Optional[str] = None, limit: int = 25
    ) -> List[Dict]:
        """指定されたページの子孫コンテンツを型指定でフラット列挙する (`GET /rest/api/content/{id}/descendant/{type}`)."""
        path = f"/rest/api/content/{page_id}/descendant/{type_}"
        items = []
        start = 0
        while True:
            params: Dict[str, object] = {"limit": limit, "start": start}
            if expand:
                params["expand"] = expand
            data = self._request("GET", path, params=params)
            results = data.get("results", []) if isinstance(data, dict) else []
            items.extend(results)

            next_start = _extract_next_start(data, start, len(results))
            if next_start is None:
                break
            start = next_start

        return items

    def get_current_user(self, expand: Optional[str] = None) -> Dict:
        """実行ユーザー情報を取得する (`GET /rest/api/user/current`)."""
        path = "/rest/api/user/current"
        params = {}
        if expand:
            params["expand"] = expand
        return self._request("GET", path, params=params if params else None)

    def get_user_memberof(self, limit: int = 200) -> List[Dict]:
        """実行ユーザーの所属グループ一覧を取得する (`GET /rest/api/user/memberof`)."""
        path = "/rest/api/user/memberof"
        groups = []
        start = 0
        while True:
            params = {"limit": limit, "start": start}
            data = self._request("GET", path, params=params)
            results = data.get("results", []) if isinstance(data, dict) else []
            groups.extend(results)

            next_start = _extract_next_start(data, start, len(results))
            if next_start is None:
                break
            start = next_start

        return groups

    def get_access_mode(self) -> Dict:
        """インスタンスのアクセスモード情報を取得する (`GET /rest/api/accessmode`)."""
        path = "/rest/api/accessmode"
        return self._request("GET", path)

    def get_server_information(self) -> Dict:
        """Confluenceサーバー情報を取得する (`GET /rest/api/server-information`)."""
        path = "/rest/api/server-information"
        return self._request("GET", path)

    # --- 詳細調査フェーズ (B/C) API メソッド ---

    def get_content_history(self, page_id: str, expand: str = "lastUpdated,contributors") -> Dict:
        """指定されたページの更新履歴（作成者・最終更新者・貢献者）を取得する (`GET /rest/api/content/{id}/history`)."""
        path = f"/rest/api/content/{page_id}/history"
        params = {"expand": expand}
        return self._request("GET", path, params=params)

    def get_labels(self, page_id: str, prefix: Optional[str] = None, limit: int = 200) -> List[Dict]:
        """指定されたページのラベル一覧を取得する (`GET /rest/api/content/{id}/label`)."""
        path = f"/rest/api/content/{page_id}/label"
        labels = []
        start = 0
        while True:
            params: Dict[str, object] = {"limit": limit, "start": start}
            if prefix:
                params["prefix"] = prefix
            data = self._request("GET", path, params=params)
            results = data.get("results", []) if isinstance(data, dict) else []
            labels.extend(results)

            next_start = _extract_next_start(data, start, len(results))
            if next_start is None:
                break
            start = next_start

        return labels

    def search_cql(self, cql: str, expand: str = "history,space,version", limit: int = 50) -> List[Dict]:
        """CQL検索を実行し該当コンテンツ一覧を取得する (`GET /rest/api/content/search`)."""
        path = "/rest/api/content/search"
        items = []
        start = 0
        while True:
            params = {"cql": cql, "expand": expand, "limit": limit, "start": start}
            data = self._request("GET", path, params=params)
            results = data.get("results", []) if isinstance(data, dict) else []
            items.extend(results)

            next_start = _extract_next_start(data, start, len(results))
            if next_start is None:
                break
            start = next_start

        return items

    def get_comments(
        self,
        page_id: str,
        depth: str = "all",
        expand: str = "extensions.location,extensions.resolution",
        limit: int = 50,
    ) -> List[Dict]:
        """指定されたページのコメント一覧を取得する (`GET /rest/api/content/{id}/child/comment`)."""
        path = f"/rest/api/content/{page_id}/child/comment"
        comments = []
        start = 0
        while True:
            params = {"depth": depth, "expand": expand, "limit": limit, "start": start}
            data = self._request("GET", path, params=params)
            results = data.get("results", []) if isinstance(data, dict) else []
            comments.extend(results)

            next_start = _extract_next_start(data, start, len(results))
            if next_start is None:
                break
            start = next_start

        return comments

    def get_attachment_extracted_text(self, page_id: str, attachment_id: str, limit: Optional[int] = None) -> Dict:
        """指定された添付ファイルの抽出テキスト情報を取得する (`GET /rest/api/content/{id}/child/attachment/{attachmentId}/extractedtext`)."""
        path = f"/rest/api/content/{page_id}/child/attachment/{attachment_id}/extractedtext"
        params = {}
        if limit is not None:
            params["limit"] = limit
        return self._request("GET", path, params=params if params else None)

    def get_relevant_view_restrictions(self, page_id: str) -> Dict:
        """指定されたページの実効的な閲覧制限（継承含む）を取得する (`GET /rest/api/content/{id}/restriction/relevantViewRestrictions`)."""
        path = f"/rest/api/content/{page_id}/restriction/relevantViewRestrictions"
        return self._request("GET", path)

    def get_space_permissions(self, space_key: str) -> Dict:
        """指定されたSpaceの権限照会情報を取得する (`GET /rest/api/space/{spaceKey}/permissions`)."""
        path = f"/rest/api/space/{space_key}/permissions"
        return self._request("GET", path)

    def get_content_watchers(self, content_id: str) -> Dict:
        """指定されたコンテンツのウォッチャー情報を取得する (`GET /rest/api/content/{contentId}/watchers`)."""
        path = f"/rest/api/content/{content_id}/watchers"
        return self._request("GET", path)

    def get_space_watchers(self, space_key: str) -> Dict:
        """指定されたSpaceのウォッチャー情報を取得する (`GET /rest/api/space/{spaceKey}/watchers`)."""
        path = f"/rest/api/space/{space_key}/watchers"
        return self._request("GET", path)

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
                elif 500 <= response.status_code < 600 and i < retries - 1:
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
                if i == retries - 1 or (
                    isinstance(error, requests.exceptions.HTTPError)
                    and error.response is not None
                    and error.response.status_code in (401, 403, 404)
                ):
                    raise _safe_request_exception(error, "添付ファイルのダウンロードに失敗しました") from None
                logger.warning(f"添付ダウンロードリクエストが失敗しました。再試行中 ({i + 1}/{retries})...")
                time.sleep(backoff * (2**i))

        raise requests.exceptions.RequestException("添付ファイルのダウンロードに失敗しました")
