import pytest

from app.core.security import verify_password


@pytest.mark.asyncio
async def test_register_four_digit_password(client):
    response = await client.post(
        "/api/v1/auth/register", json={"username": "pinuser", "password": "1234"}
    )
    assert response.status_code == 201
    login = await client.post(
        "/api/v1/auth/login", json={"username": "pinuser", "password": "1234"}
    )
    assert login.status_code == 200


@pytest.mark.asyncio
async def test_update_credentials(client, auth_headers_supervisor, seed_test_data):
    user = seed_test_data["conductor"]
    endpoint = f"/api/v1/auth/usuarios/{user.id}"
    response = await client.patch(
        endpoint, headers=auth_headers_supervisor,
        json={"username": "  nuevo_username  ", "password": "4321"},
    )
    assert response.status_code == 200
    assert response.json()["username"] == "nuevo_username"
    assert "password" not in response.json()
    assert "password_hash" not in response.json()
    assert user.password_hash != "4321"
    assert verify_password("4321", user.password_hash)
    login = await client.post(
        "/api/v1/auth/login", json={"username": "nuevo_username", "password": "4321"}
    )
    assert login.status_code == 200
    old_password = await client.post(
        "/api/v1/auth/login",
        json={"username": "nuevo_username", "password": "password123"},
    )
    assert old_password.status_code == 401
    profile = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {login.json()['access_token']}"},
    )
    assert profile.json()["username"] == "nuevo_username"


@pytest.mark.asyncio
async def test_credentials_validation_and_permissions(
    client, auth_headers_supervisor, auth_headers_conductor, seed_test_data,
):
    user = seed_test_data["conductor"]
    endpoint = f"/api/v1/auth/usuarios/{user.id}"
    original_hash = user.password_hash
    for payload in ({"password": "123"}, {"password": "    "}, {"username": "  "}):
        response = await client.patch(endpoint, headers=auth_headers_supervisor, json=payload)
        assert response.status_code == 422
    duplicate = await client.patch(
        endpoint, headers=auth_headers_supervisor,
        json={"username": seed_test_data["supervisor"].username.upper(), "password": "4321"},
    )
    assert duplicate.status_code == 409
    assert user.password_hash == original_hash
    for headers, status in (({}, 401), (auth_headers_conductor, 403)):
        response = await client.patch(endpoint, headers=headers, json={"password": "4321"})
        assert response.status_code == status
    unchanged = await client.patch(
        endpoint, headers=auth_headers_supervisor, json={"password": None, "username": None}
    )
    assert unchanged.status_code == 200
    assert user.password_hash == original_hash
    renamed = await client.patch(
        endpoint, headers=auth_headers_supervisor, json={"username": "solo_username"}
    )
    assert renamed.status_code == 200
    assert user.password_hash == original_hash
    password_only = await client.patch(
        endpoint, headers=auth_headers_supervisor, json={"password": "9876"}
    )
    assert password_only.status_code == 200
    assert password_only.json()["username"] == "solo_username"
    assert verify_password("9876", user.password_hash)
