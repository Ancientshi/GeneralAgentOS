import time

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from general_agent_os.profile import ProfileError, load_profile
from general_agent_os.runtime import create_app


@pytest.fixture
def jwt_keys(tmp_path):
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_file = tmp_path / "control-plane-public.pem"
    public_file.write_bytes(
        private.public_key().public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
        )
    )
    return private, public_file


def test_control_plane_jwt_authentication_scopes_and_chat(
    profile_factory, model_server, jwt_keys, monkeypatch
):
    private, public_file = jwt_keys
    url, requests = model_server
    path = profile_factory(
        os={
            "host": "0.0.0.0",
            "authorization": True,
            "jwt_verification_key_file": public_file.name,
            "cors_origins": ["https://os.agno.com"],
        },
        agents={"assistant": {"base_url": url}},
    )
    # A legacy deployment key must neither intercept JWTs nor bypass JWT authentication.
    monkeypatch.setenv("GAOS_API_KEY", "old-deployment-key")
    monkeypatch.setenv("OS_SECURITY_KEY", "old-deployment-key")
    now = int(time.time())
    claims = {"sub": "control-plane-user", "iat": now, "exp": now + 300, "scopes": ["agent_os:admin"]}
    token = jwt.encode(claims, private, algorithm="RS256")
    wrong_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    rejected = [
        "old-deployment-key",
        jwt.encode(claims, wrong_key, algorithm="RS256"),
        jwt.encode({**claims, "exp": now - 300}, private, algorithm="RS256"),
        jwt.encode(claims, "a-different-hmac-signing-key-with-32-characters", algorithm="HS256"),
    ]
    with TestClient(create_app(load_profile([path]))) as client:
        assert client.get("/health").status_code == 200
        assert client.get("/info").json()["auth_mode"] == "jwt"
        assert client.get("/agents").status_code == 401
        for invalid in rejected:
            assert client.get("/agents", headers={"Authorization": f"Bearer {invalid}"}).status_code == 401
        no_scopes = jwt.encode({**claims, "scopes": []}, private, algorithm="RS256")
        assert client.post(
            "/agents/assistant/runs",
            data={"message": "Hello", "stream": "false"},
            headers={"Authorization": f"Bearer {no_scopes}"},
        ).status_code == 403
        assert not requests
        auth = {"Authorization": f"Bearer {token}", "Origin": "https://os.agno.com"}
        agents = client.get("/agents", headers=auth)
        assert agents.status_code == 200
        assert agents.json()[0]["id"] == "assistant"
        assert agents.headers["access-control-allow-origin"] == "https://os.agno.com"
        response = client.post(
            "/agents/assistant/runs",
            headers=auth,
            data={"message": "Hello", "stream": "false", "session_id": "jwt-test-session"},
        )
        assert response.status_code == 200, response.text
        assert response.json()["content"] == "Profile works."
        assert len(requests) == 1


@pytest.mark.parametrize(
    "settings,match",
    [
        ({"authorization": "true"}, "must be a boolean"),
        ({"jwt_verification_key_file": "key.pem"}, "requires os.authorization"),
        ({"authorization": True, "jwt_verification_key_file": ""}, "non-empty path"),
        ({"authorization": True}, "requires.*verification"),
        ({"authorization": True, "jwt_verification_key_file": "missing.pem"}, "Cannot read"),
    ],
)
def test_jwt_configuration_fails_closed(profile_factory, settings, match):
    with pytest.raises(ProfileError, match=match):
        create_app(load_profile([profile_factory(os=settings)]))


def test_jwt_empty_key_file_fails_closed(profile_factory, tmp_path):
    (tmp_path / "empty.pem").write_text("\n")
    with pytest.raises(ProfileError, match="is empty"):
        create_app(
            load_profile(
                [profile_factory(os={"authorization": True, "jwt_verification_key_file": "empty.pem"})]
            )
        )
