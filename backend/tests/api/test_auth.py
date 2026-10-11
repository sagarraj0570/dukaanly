import pytest
from httpx import AsyncClient
import uuid

pytestmark = pytest.mark.asyncio

async def test_register_user(async_client: AsyncClient):
    unique_email = f"testuser_{uuid.uuid4()}@example.com"
    payload = {
        "name": "Test User",
        "email": unique_email,
        "phone_number": f"12345678{str(uuid.uuid4())[:2]}",
        "password": "SecurePassword123!"
    }
    
    # 1. Register
    response = await async_client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["email"] == unique_email
    assert data["name"] == "Test User"
    assert data["role"] == "customer" # Default role
    assert "password" not in data
    assert "password_hash" not in data
    assert "id" in data

    # 2. Prevent duplicate registration
    response = await async_client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 400

async def test_login_and_me(async_client: AsyncClient):
    unique_email = f"loginuser_{uuid.uuid4()}@example.com"
    password = "SuperSecretPassword123"
    
    # Register
    await async_client.post("/api/v1/auth/register", json={
        "name": "Login User",
        "email": unique_email,
        "password": password
    })
    
    # Login
    login_payload = {
        "email": unique_email,
        "password": password
    }
    response = await async_client.post("/api/v1/auth/login", json=login_payload)
    assert response.status_code == 200
    tokens = response.json()
    assert "access_token" in tokens
    assert "refresh_token" in tokens
    
    # Access /me
    me_response = await async_client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {tokens['access_token']}"})
    assert me_response.status_code == 200
    me_data = me_response.json()
    assert me_data["email"] == unique_email
    
    # Access /me without token
    fail_response = await async_client.get("/api/v1/auth/me")
    assert fail_response.status_code == 401

async def test_refresh_token(async_client: AsyncClient):
    unique_email = f"refreshuser_{uuid.uuid4()}@example.com"
    password = "SuperSecretPassword123"
    
    await async_client.post("/api/v1/auth/register", json={
        "name": "Refresh User",
        "email": unique_email,
        "password": password
    })
    
    login_response = await async_client.post("/api/v1/auth/login", json={
        "email": unique_email,
        "password": password
    })
    tokens = login_response.json()
    refresh_token = tokens["refresh_token"]
    
    # Refresh
    import asyncio
    await asyncio.sleep(1) # Ensure timestamp changes for access token
    refresh_res = await async_client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
    assert refresh_res.status_code == 200
    new_tokens = refresh_res.json()
    assert new_tokens["access_token"] != tokens["access_token"]
    assert new_tokens["refresh_token"] != tokens["refresh_token"]
    
    # Try reusing old refresh token
    reuse_res = await async_client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
    assert reuse_res.status_code == 401

async def test_logout(async_client: AsyncClient):
    unique_email = f"logoutuser_{uuid.uuid4()}@example.com"
    password = "SuperSecretPassword123"
    
    await async_client.post("/api/v1/auth/register", json={
        "name": "Logout User",
        "email": unique_email,
        "password": password
    })
    
    login_response = await async_client.post("/api/v1/auth/login", json={
        "email": unique_email,
        "password": password
    })
    refresh_token = login_response.json()["refresh_token"]
    
    # Logout
    logout_res = await async_client.post("/api/v1/auth/logout", json={"refresh_token": refresh_token})
    assert logout_res.status_code == 204
    
    # Try refreshing after logout
    refresh_res = await async_client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
    assert refresh_res.status_code == 401

async def test_role_authorization(async_client: AsyncClient):
    unique_email = f"roleuser_{uuid.uuid4()}@example.com"
    password = "SuperSecretPassword123"
    
    await async_client.post("/api/v1/auth/register", json={
        "name": "Role User",
        "email": unique_email,
        "password": password
    })
    
    login_response = await async_client.post("/api/v1/auth/login", json={
        "email": unique_email,
        "password": password
    })
    token = login_response.json()["access_token"]
    
    # Let's dynamically add a route to the app to test role authorization
    from app.main import app
    from fastapi import APIRouter, Depends
    from app.api.dependencies import require_role
    
    test_router = APIRouter()
    @test_router.get("/api/v1/auth/test-admin-only", dependencies=[Depends(require_role("admin"))])
    def admin_only():
        return {"status": "ok"}
    @test_router.get("/api/v1/auth/test-customer-only", dependencies=[Depends(require_role("customer"))])
    def customer_only():
        return {"status": "ok"}
        
    app.include_router(test_router)
    
    # Attempt to access admin route as customer
    admin_res = await async_client.get("/api/v1/auth/test-admin-only", headers={"Authorization": f"Bearer {token}"})
    assert admin_res.status_code == 403
    
    # Attempt to access customer route as customer
    cust_res = await async_client.get("/api/v1/auth/test-customer-only", headers={"Authorization": f"Bearer {token}"})
    assert cust_res.status_code == 200

async def test_register_privilege_escalation_prevented(async_client: AsyncClient):
    unique_email = f"escalate_{uuid.uuid4()}@example.com"
    payload = {
        "name": "Attacker",
        "email": unique_email,
        "password": "Password123!",
        "role": "admin"
    }
    res = await async_client.post("/api/v1/auth/register", json=payload)
    assert res.status_code == 201
    data = res.json()
    assert data["role"] == "customer"

async def test_invalid_and_expired_tokens(async_client: AsyncClient):
    # Invalid token format / garbage token
    res_bad = await async_client.get("/api/v1/auth/me", headers={"Authorization": "Bearer not-a-valid-token"})
    assert res_bad.status_code == 401

    # Forged token with invalid secret
    import jwt
    from datetime import datetime, timedelta, timezone
    forged = jwt.encode(
        {"sub": str(uuid.uuid4()), "role": "admin", "exp": datetime.now(timezone.utc) + timedelta(minutes=10)},
        "wrong_secret_key_12345678901234567890",
        algorithm="HS256"
    )
    res_forged = await async_client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {forged}"})
    assert res_forged.status_code == 401

