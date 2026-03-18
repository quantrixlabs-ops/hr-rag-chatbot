"""SSO / OIDC integration framework (Phase B1).

Provides the integration point for enterprise SSO. When configured,
the login flow becomes:

  1. Frontend redirects to /auth/sso/login
  2. Backend redirects to IdP (Okta, Azure AD, Google Workspace)
  3. IdP authenticates user and redirects back to /auth/sso/callback
  4. Backend exchanges code for tokens, creates/updates local user
  5. Backend issues JWT and redirects to frontend with token

Configuration (via .env):
    SSO_ENABLED=true
    SSO_PROVIDER=oidc          # oidc, saml
    SSO_CLIENT_ID=your-client-id
    SSO_CLIENT_SECRET=your-client-secret
    SSO_ISSUER_URL=https://your-tenant.okta.com
    SSO_REDIRECT_URI=http://localhost:8000/auth/sso/callback

Dependencies (install when enabling SSO):
    pip install authlib httpx
"""

from __future__ import annotations

import structlog

logger = structlog.get_logger()

# SSO is opt-in — only activates when SSO_ENABLED=true in config
_sso_client = None
_sso_enabled = False


def is_sso_enabled() -> bool:
    """Check if SSO is configured and enabled."""
    return _sso_enabled


def configure_sso(
    client_id: str,
    client_secret: str,
    issuer_url: str,
    redirect_uri: str,
) -> bool:
    """Initialize the OIDC client. Returns True if successful."""
    global _sso_client, _sso_enabled
    try:
        from authlib.integrations.starlette_client import OAuth
        oauth = OAuth()
        oauth.register(
            name="hr_sso",
            client_id=client_id,
            client_secret=client_secret,
            server_metadata_url=f"{issuer_url}/.well-known/openid-configuration",
            client_kwargs={"scope": "openid email profile"},
        )
        _sso_client = oauth
        _sso_enabled = True
        logger.info("sso_configured", issuer=issuer_url)
        return True
    except ImportError:
        logger.warning("sso_not_available", reason="authlib not installed")
        return False
    except Exception as e:
        logger.warning("sso_configuration_failed", error=str(e))
        return False


def get_sso_client():
    """Get the configured OAuth client."""
    return _sso_client


# ── SSO Route handlers (to be registered in auth_routes.py) ─────────────────
# These are template handlers that work with any OIDC provider.
#
# @router.get("/sso/login")
# async def sso_login(request: Request):
#     redirect_uri = request.url_for("sso_callback")
#     client = get_sso_client().hr_sso
#     return await client.authorize_redirect(request, redirect_uri)
#
# @router.get("/sso/callback")
# async def sso_callback(request: Request):
#     client = get_sso_client().hr_sso
#     token = await client.authorize_access_token(request)
#     userinfo = token.get("userinfo")
#     # Create or update local user from OIDC claims
#     # Issue local JWT
#     # Redirect to frontend with token
