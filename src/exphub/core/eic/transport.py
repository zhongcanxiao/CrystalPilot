"""Non-authenticated HTTP transport for the vendored EIC client.

``EICClientComm`` was extracted verbatim from ``eic_client.py`` (based on the
ONCat client by Peter Parker, modified for EIC by Ray Gregory). Behavior is
pinned by ``tests/test_eic_client_characterization.py``.
"""

from typing import Any, Optional

import oauthlib
import requests

from .errors import BadRequestError, EICClientError, NotFoundError, UnauthorizedError


class EICClientComm(object):
    """Class for EIC Client communication without OAuth authentication."""

    def __init__(self, eic_base_url: str, timeout: Optional[int] = None, verify: bool = True) -> None:
        self._eic_base_url = eic_base_url
        self._timeout = timeout
        self._verify = verify

    def get(self, url: str, **kwargs: Any) -> Any:
        return self._call_method("get", url, None, **kwargs)

    def put(self, url: str, data: Any, **kwargs: Any) -> Any:
        result = self._call_method("put", url, data, **kwargs)

        # Not all resources will return a confirmation representation.
        return result if result != "" else None

    def post(self, url: str, data: Any, **kwargs: Any) -> Any:
        return self._call_method("post", url, data, **kwargs)

    def delete(self, url: str, **kwargs: Any) -> Any:
        self._call_method("delete", url, None, **kwargs)

    def _call_method(self, method: str, url: str, data: Any, **kwargs: Any) -> Any:
        # noinspection PyUnresolvedReferences
        url = requests.utils.quote(url)
        url_sep = "/" if not url.startswith("/") else ""
        full_url = self.eic_base_url() + url_sep + url

        # print(f"\n\nIn EICClientComm._call_method(). full_url: {full_url}\n\n")

        def send_request() -> Any:
            response = getattr(requests, method)(
                full_url, params=kwargs, json=data, timeout=self._timeout, verify=self._verify
            )
            try:
                response.raise_for_status()
            except requests.exceptions.HTTPError as send_error:
                if send_error.response.status_code == 400:
                    raise BadRequestError("Bad request", original_error=send_error) from send_error
                if send_error.response.status_code == 401:
                    raise UnauthorizedError(
                        f'Not authorized to access "{full_url}"', original_error=send_error
                    ) from send_error
                if send_error.response.status_code == 404:
                    raise NotFoundError(
                        f'Could not find resource at "{full_url}"', original_error=send_error
                    ) from send_error
                raise EICClientError(f'Error: "{send_error}"', original_error=send_error) from send_error

            return response

        # noinspection PyUnresolvedReferences
        try:
            return send_request()
        except oauthlib.oauth2.rfc6749.errors.InvalidGrantError as error:
            raise EICClientError('Error: "%s"' % str(error), original_error=error) from error

    def eic_base_url(self) -> str:
        return self._eic_base_url
