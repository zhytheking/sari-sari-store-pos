import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, Optional


class ApiError(Exception):
    
    def __init__(self, message: str, status: int = 0,
                 payload: Optional[dict] = None):
        super().__init__(message)
        self.message = message
        self.status = status
        self.payload = payload or {}


class Api:
    

    @classmethod
    def _call(
        cls,
        method: str,
        base_url: str,
        path: str,
        token: Optional[str] = None,
        timeout: int = 20,
        params: Optional[Dict[str, Any]] = None,
        json_body: Optional[Dict[str, Any]] = None,
        data: Optional[bytes] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:

        # Build URL
        url = f"{base_url.rstrip('/')}{path}"
        if params:
            query = urllib.parse.urlencode(params)
            url = f"{url}?{query}" if '?' not in url else f"{url}&{query}"

        # Build headers
        hdrs: Dict[str, str] = {
            'Accept': 'application/json',
            'User-Agent': 'SariSariPOS-GUI/1.0',
        }
        if token:
            hdrs['Authorization'] = f'Bearer {token}'
        if headers:
            hdrs.update(headers)

        # Build body
        body_bytes: Optional[bytes] = None
        if json_body is not None:
            body_bytes = json.dumps(json_body).encode('utf-8')
            hdrs['Content-Type'] = 'application/json'
            hdrs['Content-Length'] = str(len(body_bytes))
        elif data is not None:
            body_bytes = data
            if 'Content-Type' not in hdrs:
                hdrs['Content-Type'] = 'application/octet-stream'
            hdrs['Content-Length'] = str(len(body_bytes))

        # Build request
        req = urllib.request.Request(
            url, data=body_bytes, headers=hdrs, method=method.upper())

        # Extract a short host for error messages.
        try:
            parsed = urllib.parse.urlparse(url)
            host_for_errors = f"{parsed.scheme}://{parsed.netloc}"
        except Exception:
            host_for_errors = base_url

        # Execute
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read()
                status = resp.status
        except urllib.error.HTTPError as e:
            # 4xx/5xx — server responded with error
            raw = e.read() or b''
            status = e.code
        except urllib.error.URLError as e:
            reason = getattr(e, 'reason', e)
            reason_str = str(reason)
            if 'timed out' in reason_str.lower():
                raise ApiError(
                    "Request timed out. Please try again.", status=0) from e
            if ('refused' in reason_str.lower()
                    or 'unreachable' in reason_str.lower()):
                raise ApiError(
                    f"Cannot reach the server.\n"
                    f"Make sure the backend is running at {host_for_errors}",
                    status=0) from e
            raise ApiError(f"Network error: {reason_str}", status=0) from e
        except TimeoutError as e:
            raise ApiError(
                "Request timed out. Please try again.", status=0) from e
        except OSError as e:
            raise ApiError(f"Network error: {e}", status=0) from e

        # Parse JSON
        data_parsed: Dict[str, Any] = {}
        if raw:
            try:
                data_parsed = json.loads(raw.decode('utf-8'))
            except (ValueError, UnicodeDecodeError):
                data_parsed = {}

        # Success?
        if 200 <= status < 300:
            return data_parsed

        # Error
        message = (
            data_parsed.get('message')
            or data_parsed.get('error')
            or f"HTTP {status}"
        )
        raise ApiError(message, status=status, payload=data_parsed)

    @classmethod
    def get(cls, base_url, path, token=None, timeout=20,
            params=None, **kw):
        return cls._call('GET', base_url, path,
                         token=token, timeout=timeout,
                         params=params, **kw)

    @classmethod
    def post(cls, base_url, path, token=None, timeout=20,
             json=None, data=None, **kw):
        return cls._call('POST', base_url, path,
                         token=token, timeout=timeout,
                         json_body=json, data=data, **kw)

    @classmethod
    def put(cls, base_url, path, token=None, timeout=20,
            json=None, data=None, **kw):
        return cls._call('PUT', base_url, path,
                         token=token, timeout=timeout,
                         json_body=json, data=data, **kw)

    @classmethod
    def delete(cls, base_url, path, token=None, timeout=20, **kw):
        return cls._call('DELETE', base_url, path,
                         token=token, timeout=timeout, **kw)

    @classmethod
    def close(cls):
         pass
