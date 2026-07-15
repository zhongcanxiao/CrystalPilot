"""OAuth (client-credentials) HTTP transport for the vendored EIC client.

``EICClientAuthComm`` was extracted verbatim from ``eic_client.py`` (based on
the ONCat client by Peter Parker, modified for EIC by Ray Gregory). Behavior
is pinned by ``tests/test_eic_client_auth_characterization.py``.
"""

import os
import sys
import warnings
from typing import Any, Optional

import oauthlib
import requests
import requests_oauthlib
from urllib3.exceptions import InsecureRequestWarning

from .constants import use_https_in_production
from .errors import (
    BadRequestError,
    EICClientError,
    InvalidClientCredentialsError,
    NotFoundError,
    UnauthorizedError,
)


class EICClientAuthComm(object):
    """Class for EIC client communications with authentication."""

    def __init__(
        self,
        eic_base_url: str,
        ping_fed_url: str,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        token_getter: Any = None,
        token_setter: Any = None,
        api_token: Optional[str] = None,
        scopes: Optional[Any] = None,
        verify: bool = True,
        timeout: Optional[int] = None,
    ) -> None:
        self._token_getter = token_getter
        self._token_setter = token_setter

        self._api_token = api_token
        self._client_id = client_id
        self._client_secret = client_secret
        self._eic_base_url = eic_base_url
        self._ping_fed_url = ping_fed_url
        self._scopes = scopes
        self._verify = verify
        self._timeout = timeout

        self._token = None
        self._oauth_client = None

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
        # print(f'\n\nIn EICClientComm._call_method().\n'
        #       f'self.eic_base_url() = {self.eic_base_url()} url = {url} full_url = {full_url}\n\n')
        # print(f"\n\nIn EICClientAuthComm._call_method(). eic_base_url: {self.eic_base_url()} full_url: {full_url}\n\n")#noqa

        def send_request() -> Any:
            if use_https_in_production and self._client_id:
                do_verify = self.should_verify()
                client = self.oauth_client()
                response = getattr(client, method)(
                    full_url,
                    params=kwargs,
                    json=data,
                    verify=do_verify,
                    # verify=False,
                    timeout=self._timeout,
                )
            else:
                response = getattr(requests, method)(
                    full_url,
                    params=kwargs,
                    json=data,
                    # verify=do_verify,
                    verify=False,
                    headers={"Authorization": f"Bearer {self._api_token}"} if self._api_token else None,
                    timeout=self._timeout,
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
        except oauthlib.oauth2.TokenExpiredError:
            self.login()
            return send_request()

    def oauth_client(self) -> requests_oauthlib.OAuth2Session:
        if not self._oauth_client:
            self.login()

        return self._oauth_client

    def get_token(self) -> Any:
        if self._token_getter is not None:
            return self._token_getter()

        return self._token

    def set_token(self, token: Any) -> None:
        if self._token_setter is not None:
            self._token_setter(token)
        else:
            self._token = token

    def should_verify(self) -> bool:
        if self._verify:
            do_verify = (
                "localhost" not in self.eic_base_url()
                and "load-balancer" not in self.eic_base_url()
                and "proxy" not in self.eic_base_url()
            )

            # print(f'\n\nIn EICClient.should_verify(). do_verify = {do_verify}\n\n')
            if not do_verify:
                # Ignore invalid certs and lack of SSL for OAuth if
                # deploying locally.
                # noinspection PyUnresolvedReferences
                requests.packages.urllib3.disable_warnings(InsecureRequestWarning)
                os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"

        else:
            do_verify = False

        return do_verify

    def eic_base_url(self) -> str:
        return self._eic_base_url

    def ping_fed_url(self) -> str:
        return self._ping_fed_url

    def login(self) -> None:
        self._login_client_credentials()

    def _retrieve_client_credentials_token(self) -> Any:
        grant_type = "client_credentials"

        response = requests.post(
            self.ping_fed_url(),
            data={
                "grant_type": grant_type,
                "client_id": self._client_id,
                "client_secret": self._client_secret,
                "scope": self._scopes,
            },
        )
        response.raise_for_status()

        return response.json()

    def _login_client_credentials(self) -> None:
        # print('\n\nIn _login_client_credentials(). Checkpoint 1\n\n')
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", category=DeprecationWarning)
            # noinspection PyUnresolvedReferences
            self._oauth_client = requests_oauthlib.OAuth2Session(
                client=oauthlib.oauth2.BackendApplicationClient(
                    client_id=self._client_id,
                    client_secret=self._client_secret,
                    scope=self._scopes,
                ),
                scope=self._scopes,
            )
        # print('\n\nIn _login_client_credentials(). Checkpoint 2\n\n')
        # noinspection PyUnresolvedReferences
        try:
            assert self._oauth_client is not None
            token = self._oauth_client.fetch_token(
                self.ping_fed_url(),
                auth=False,
                client_id=self._client_id,
                client_secret=self._client_secret,
                include_client_id=True,
                verify=self.should_verify(),
                scope=self._scopes,
                timeout=self._timeout,
            )
            # print('\n\nIn _login_client_credentials(). Checkpoint 3\n\n')
        except (AssertionError, oauthlib.oauth2.rfc6749.errors.InvalidClientError) as error:
            e = sys.exc_info()
            error_message = f"ERROR in _login_client_credentials(): {e}"
            print(f"\n\n{error_message}\n\n")
            raise InvalidClientCredentialsError(
                "You seem to have provided some invalid client credentials.  Are you sure they are correct?",
                original_error=error,
            ) from error

        self.set_token(token)
