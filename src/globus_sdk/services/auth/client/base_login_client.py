from __future__ import annotations

import logging
import sys
import typing as t

from globus_sdk import _guards, exc, utils
from globus_sdk._types import UUIDLike
from globus_sdk.authorizers import GlobusAuthorizer, NullAuthorizer
from globus_sdk.response import GlobusHTTPResponse

from ..flow_managers import GlobusOAuthFlowManager
from ..response import OAuthTokenResponse
from .base import AuthBaseClient

if sys.version_info >= (3, 8):
    from typing import Literal
else:
    from typing_extensions import Literal

log = logging.getLogger(__name__)

RT = t.TypeVar("RT", bound=GlobusHTTPResponse)


class AuthLoginClient(AuthBaseClient):
    """
    This client class provides the common base for clients providing login
    functionality via
    `Globus Auth <https://docs.globus.org/api/auth/>`_

    :param client_id: The ID of the application provided by registration with
        Globus Auth.
    :type client_id: str or UUID

    All other initialization parameters are passed through to ``BaseClient``.

    .. automethodlist:: globus_sdk.AuthLoginClient
    """

    def __init__(
        self,
        client_id: UUIDLike | None = None,
        environment: str | None = None,
        base_url: str | None = None,
        authorizer: GlobusAuthorizer | None = None,
        app_name: str | None = None,
        transport_params: dict[str, t.Any] | None = None,
    ) -> None:
        super().__init__(
            environment=environment,
            base_url=base_url,
            authorizer=authorizer,
            app_name=app_name,
            transport_params=transport_params,
        )
        self.client_id: str | None = str(client_id) if client_id is not None else None
        # an AuthClient may contain a GlobusOAuth2FlowManager in order to
        # encapsulate the functionality of various different types of flow
        # managers
        self.current_oauth2_flow_manager: GlobusOAuthFlowManager | None = None

        log.info(
            "Finished initializing AuthLoginClient. "
            f"client_id='{client_id}', type(authorizer)={type(authorizer)}"
        )

    def oauth2_get_authorize_url(
        self,
        *,
        session_required_identities: UUIDLike | t.Iterable[UUIDLike] | None = None,
        session_required_single_domain: str | t.Iterable[str] | None = None,
        session_required_policies: UUIDLike | t.Iterable[UUIDLike] | None = None,
        prompt: Literal["login"] | None = None,
        query_params: dict[str, t.Any] | None = None,
    ) -> str:
        """
        Get the authorization URL to which users should be sent.
        This method may only be called after ``oauth2_start_flow``
        has been called on this ``AuthClient``.

        :param session_required_identities: A list of identities must be
            added to the session.
        :type session_required_identities: str or uuid or list of str or uuid, optional
        :param session_required_single_domain: A list of domain requirements
            which must be satisfied by identities added to the session.
        :type session_required_single_domain: str or list of str, optional
        :param session_required_policies: A list of IDs for policies which must
            be satisfied by the user.
        :type session_required_policies: str or uuid or list of str or uuid, optional
        :param prompt:
            Control whether a user is required to log in before the authorization step.

            If set to "login", the user must authenticate with an identity provider
            even if they are already logged in. Setting this parameter can help ensure
            that a user's session meets known or unknown session requirement policies
            and avoid additional login flows.
        :type prompt: ``"login"``, optional
        :param query_params: Additional query parameters to include in the
            authorize URL. Primarily for internal use
        :type query_params: dict, optional
        :rtype: ``string``
        """
        if not self.current_oauth2_flow_manager:
            log.error("OutOfOrderOperations(get_authorize_url before start_flow)")
            raise exc.GlobusSDKUsageError(
                "Cannot get authorize URL until starting an OAuth2 flow. "
                "Call the oauth2_start_flow() method on this "
                "AuthClient to resolve"
            )
        if query_params is None:
            query_params = {}
        if session_required_identities is not None:
            query_params["session_required_identities"] = utils.commajoin(
                session_required_identities
            )
        if session_required_single_domain is not None:
            query_params["session_required_single_domain"] = utils.commajoin(
                session_required_single_domain
            )
        if session_required_policies is not None:
            query_params["session_required_policies"] = utils.commajoin(
                session_required_policies
            )
        if prompt is not None:
            query_params["prompt"] = prompt
        auth_url = self.current_oauth2_flow_manager.get_authorize_url(
            query_params=query_params
        )
        log.info(f"Got authorization URL: {auth_url}")
        return auth_url

    def oauth2_exchange_code_for_tokens(self, auth_code: str) -> OAuthTokenResponse:
        """
        Exchange an authorization code for a token or tokens.

        :rtype: :class:`OAuthTokenResponse <.OAuthTokenResponse>`

        :param auth_code: An auth code typically obtained by sending the user to the
            authorize URL. The code is a very short-lived credential which this method
            is exchanging for tokens. Tokens are the credentials used to authenticate
            against Globus APIs.
        :type auth_code: str
        """
        log.info(
            "Final Step of 3-legged OAuth2 Flows: "
            "Exchanging authorization code for token(s)"
        )
        if not self.current_oauth2_flow_manager:
            log.error("OutOfOrderOperations(exchange_code before start_flow)")
            raise exc.GlobusSDKUsageError(
                "Cannot exchange auth code until starting an OAuth2 flow. "
                "Call the oauth2_start_flow() method on this "
                "AuthClient to resolve"
            )

        return self.current_oauth2_flow_manager.exchange_code_for_tokens(auth_code)

    def oauth2_refresh_token(
        self,
        refresh_token: str,
        *,
        body_params: dict[str, t.Any] | None = None,
    ) -> OAuthTokenResponse:
        r"""
        Exchange a refresh token for a
        :class:`OAuthTokenResponse <.OAuthTokenResponse>`, containing
        an access token.

        Does a token call of the form

        .. code-block:: none

            refresh_token=<refresh_token>
            grant_type=refresh_token

        plus any additional parameters you may specify.

        :param refresh_token: A Globus Refresh Token as a string
        :type refresh_token: str

        :param body_params: A dict of extra params to encode in the refresh call.
        :type body_params: dict, optional
        """
        log.info("Executing token refresh; typically requires client credentials")
        form_data = {"refresh_token": refresh_token, "grant_type": "refresh_token"}
        return self.oauth2_token(form_data, body_params=body_params)

    def oauth2_validate_token(
        self,
        token: str,
        *,
        body_params: dict[str, t.Any] | None = None,
    ) -> GlobusHTTPResponse:
        """
        Validate a token. It can be an Access Token or a Refresh token.

        This call can be used to check tokens issued to your client,
        confirming that they are or are not still valid. The resulting response
        has the form ``{"active": True}`` when the token is valid, and
        ``{"active": False}`` when it is not.

        It is not necessary to validate tokens immediately after receiving them
        from the service -- any tokens which you are issued will be valid at
        that time. This is more for the purpose of doing checks like

        - confirm that ``oauth2_revoke_token`` succeeded
        - at application boot, confirm no need to do fresh login

        :param token: The token which should be validated. Can be a refresh token or an
            access token
        :type token: str
        :param body_params: Additional parameters to include in the validation
            body. Primarily for internal use
        :type body_params: dict, optional

        **Examples**

        Revoke a token and confirm that it is no longer active:

        >>> from globus_sdk import ConfidentialAppAuthClient
        >>> ac = ConfidentialAppAuthClient(CLIENT_ID, CLIENT_SECRET)
        >>> ac.oauth2_revoke_token('<token_string>')
        >>> data = ac.oauth2_validate_token('<token_string>')
        >>> assert not data['active']

        During application boot, check if the user needs to do a login, even
        if a token is present:

        >>> from globus_sdk import ConfidentialAppAuthClient
        >>> ac = ConfidentialAppAuthClient(CLIENT_ID, CLIENT_SECRET)
        >>> # this is not an SDK function, but a hypothetical function which
        >>> # you use to load a token out of configuration data
        >>> tok = load_token_from_config(...)
        >>>
        >>> if not tok or not ac.oauth2_validate_token(tok)['active']:
        >>>     # do_new_login() is another hypothetical helper
        >>>     tok = do_new_login()
        >>> # at this point, tok is expected to be a valid token
        """
        log.info("Validating token")
        body = {"token": token}

        # if this client has no way of authenticating itself but
        # it does have a client_id, we'll send that in the request
        no_authentication = _guards.is_optional(self.authorizer, NullAuthorizer)
        if no_authentication and self.client_id:
            log.debug("Validating token with unauthenticated client")
            body.update({"client_id": self.client_id})

        if body_params:
            body.update(body_params)
        return self.post("/v2/oauth2/token/validate", data=body, encoding="form")

    def oauth2_revoke_token(
        self,
        token: str,
        *,
        body_params: dict[str, t.Any] | None = None,
    ) -> GlobusHTTPResponse:
        """
        Revoke a token. It can be an Access Token or a Refresh token.

        This call should be used to revoke tokens issued to your client,
        rendering them inert and not further usable. Typically, this is
        incorporated into "logout" functionality, but it should also be used if
        the client detects that its tokens are in an unsafe location (e.x.
        found in a world-readable logfile).

        You can check the "active" status of the token after revocation if you
        want to confirm that it was revoked.

        :param token: The token which should be revoked
        :type token: str
        :param body_params: Additional parameters to include in the revocation
            body, which can help speed the revocation process. Primarily for
            internal use
        :type body_params: dict, optional

        **Examples**

        >>> from globus_sdk import ConfidentialAppAuthClient
        >>> ac = ConfidentialAppAuthClient(CLIENT_ID, CLIENT_SECRET)
        >>> ac.oauth2_revoke_token('<token_string>')
        """
        log.info("Revoking token")
        body = {"token": token}

        # if this client has no way of authenticating itself but
        # it does have a client_id, we'll send that in the request
        no_authentication = self.authorizer is None or isinstance(
            self.authorizer, NullAuthorizer
        )
        if no_authentication and self.client_id:
            log.debug("Revoking token with unauthenticated client")
            body.update({"client_id": self.client_id})

        if body_params:
            body.update(body_params)
        return self.post("/v2/oauth2/token/revoke", data=body, encoding="form")

    @t.overload
    def oauth2_token(
        self,
        form_data: dict[str, t.Any] | utils.PayloadWrapper,
    ) -> OAuthTokenResponse:
        ...

    @t.overload
    def oauth2_token(
        self,
        form_data: dict[str, t.Any] | utils.PayloadWrapper,
        *,
        body_params: dict[str, t.Any] | None,
    ) -> OAuthTokenResponse:
        ...

    @t.overload
    def oauth2_token(
        self,
        form_data: dict[str, t.Any] | utils.PayloadWrapper,
        *,
        response_class: type[RT],
    ) -> RT:
        ...

    @t.overload
    def oauth2_token(
        self,
        form_data: dict[str, t.Any] | utils.PayloadWrapper,
        *,
        body_params: dict[str, t.Any] | None,
        response_class: type[RT],
    ) -> RT:
        ...

    def oauth2_token(
        self,
        form_data: dict[str, t.Any] | utils.PayloadWrapper,
        *,
        body_params: dict[str, t.Any] | None = None,
        response_class: (type[OAuthTokenResponse] | type[RT]) = OAuthTokenResponse,
    ) -> OAuthTokenResponse | RT:
        """
        This is the generic form of calling the OAuth2 Token endpoint.
        It takes ``form_data``, a dict which will be encoded in a form POST
        body on the request.

        Generally, users of the SDK should not call this method unless they are
        implementing OAuth2 flows.

        :param response_class: This is used by calls to the oauth2_token endpoint which
            need to specialize their responses. For example,
            :meth:`oauth2_get_dependent_tokens \
            <globus_sdk.ConfidentialAppAuthClient.oauth2_get_dependent_tokens>`
            requires a specialize response class to handle the dramatically different
            format of the Dependent Token Grant response
        :type response_class: class, optional
        :param form_data: The main body of the request
        :type form_data: dict or `utils.PayloadWrapper`
        :param body_params: Any additional parameters to be passed through
            as body parameters.
        :type body_params: dict, optional
        :rtype: ``response_class``
        """
        log.info("Fetching new token from Globus Auth")
        # use the fact that requests implicitly encodes the `data` parameter as
        # a form POST
        data = dict(form_data)
        if body_params:
            data.update(body_params)
        return response_class(
            self.post(
                "/v2/oauth2/token",
                data=data,
                encoding="form",
            )
        )

    def oauth2_userinfo(self) -> GlobusHTTPResponse:
        """
        Call the Userinfo endpoint of Globus Auth.
        Userinfo is specified as part of the OpenID Connect (OIDC) standard,
        and Globus Auth's Userinfo is OIDC-compliant.

        The exact data returned will depend upon the set of OIDC-related scopes
        which were used to acquire the token being used for this call. For
        details, see the **API Info** below.

        .. tab-set::

            .. tab-item:: Example Usage

                .. code-block:: python

                    ac = AuthClient(...)
                    info = ac.oauth2_userinfo()
                    print(
                        'Effective Identity "{info["sub"]}" has '
                        f'Full Name "{info["name"]}" and '
                        f'Email "{info["email"]}"'
                    )

            .. tab-item:: API Info

                ``GET /v2/oauth2/userinfo``

                .. extdoclink:: Get Userinfo
                    :ref: auth/reference/#get_or_post_v2_oauth2_userinfo_resource
        """
        log.info("Looking up OIDC-style Userinfo from Globus Auth")
        return self.get("/v2/oauth2/userinfo")
