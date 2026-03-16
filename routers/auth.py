from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from datetime import timedelta
import httpx
import os
import secrets

from database import get_db
import models
import schemas
from auth import (
    verify_password,
    get_password_hash,
    create_access_token,
    ACCESS_TOKEN_EXPIRE_MINUTES,
    get_current_user,
)

router = APIRouter()

UPWORK_CLIENT_ID = os.getenv("UPWORK_CLIENT_ID", "")
UPWORK_CLIENT_SECRET = os.getenv("UPWORK_CLIENT_SECRET", "")
UPWORK_REDIRECT_URI = os.getenv("UPWORK_REDIRECT_URI", "http://localhost:8000/api/auth/upwork/callback")
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:8000")


@router.post("/register", response_model=schemas.Token)
async def register(user_data: schemas.UserCreate, db: Session = Depends(get_db)):
    if db.query(models.User).filter(models.User.email == user_data.email).first():
        raise HTTPException(status_code=400, detail="Email already registered")
    if db.query(models.User).filter(models.User.username == user_data.username).first():
        raise HTTPException(status_code=400, detail="Username already taken")

    user = models.User(
        email=user_data.email,
        username=user_data.username,
        hashed_password=get_password_hash(user_data.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    token = create_access_token(
        data={"sub": str(user.id)},
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    )
    return {"access_token": token, "token_type": "bearer", "user": user}


@router.post("/login", response_model=schemas.Token)
async def login(user_data: schemas.UserLogin, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.email == user_data.email).first()
    if not user or not user.hashed_password or not verify_password(user_data.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    token = create_access_token(
        data={"sub": str(user.id)},
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    )
    return {"access_token": token, "token_type": "bearer", "user": user}


@router.get("/upwork/authorize")
async def upwork_authorize(current_user: models.User = Depends(get_current_user)):
    """Returns the Upwork OAuth2 authorization URL."""
    if not UPWORK_CLIENT_ID:
        raise HTTPException(status_code=500, detail="Upwork OAuth not configured. Set UPWORK_CLIENT_ID.")

    state = create_access_token(data={"sub": str(current_user.id)}, expires_delta=timedelta(minutes=10))
    auth_url = (
        f"https://www.upwork.com/ab/account-security/oauth2/authorize"
        f"?response_type=code"
        f"&client_id={UPWORK_CLIENT_ID}"
        f"&redirect_uri={UPWORK_REDIRECT_URI}"
        f"&state={state}"
    )
    return {"url": auth_url, "state": state}


@router.get("/upwork/callback")
async def upwork_callback(
    db: Session = Depends(get_db),
    code: str = None,
    state: str = None,
    error: str = None,
    error_description: str = None,
):
    if error:
        print(f"❌ Upwork OAuth error: {error} — {error_description}")
        return RedirectResponse(url=f"{FRONTEND_URL}/?error={error}&desc={error_description}")

    if not code:
        print("❌ No code received from Upwork")
        return RedirectResponse(url=f"{FRONTEND_URL}/?error=no_code_received")

    existing_user = None
    if state:
        try:
            from jose import jwt as jose_jwt
            from auth import SECRET_KEY, ALGORITHM
            payload = jose_jwt.decode(state, SECRET_KEY, algorithms=[ALGORITHM])
            user_id = payload.get("sub")
            if user_id:
                existing_user = db.query(models.User).filter(models.User.id == int(user_id)).first()
        except Exception as e:
            print("⚠️ Could not decode state JWT:", e)

    import base64
    credentials = base64.b64encode(
        f"{UPWORK_CLIENT_ID}:{UPWORK_CLIENT_SECRET}".encode()
    ).decode()

    async with httpx.AsyncClient() as client:
        token_response = await client.post(
            "https://www.upwork.com/api/v3/oauth2/token",
            headers={
                "Authorization": f"Basic {credentials}",
                "Content-Type": "application/x-www-form-urlencoded",
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "application/json",
                "Accept-Language": "en-US,en;q=0.9",
            },
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": UPWORK_REDIRECT_URI,
            },
            follow_redirects=True,
        )

    if token_response.status_code != 200:
        print("❌ Upwork token error:", token_response.status_code, token_response.text)
        return RedirectResponse(url=f"{FRONTEND_URL}/?error=upwork_token_failed&desc={token_response.text}")

    token_data    = token_response.json()
    access_token  = token_data.get("access_token")
    refresh_token = token_data.get("refresh_token")
    print("✅ Upwork token received:", access_token[:20] if access_token else "None")

    token_hash = str(abs(hash(access_token)))[:16]
    upwork_id  = f"upwork_{token_hash}"

    if existing_user:
        existing_user.upwork_access_token  = access_token
        existing_user.upwork_refresh_token = refresh_token
        existing_user.upwork_user_id       = upwork_id
        db.commit()
        db.refresh(existing_user)
        user = existing_user
    else:
        user = db.query(models.User).filter(models.User.upwork_user_id == upwork_id).first()
        if user:
            user.upwork_access_token  = access_token
            user.upwork_refresh_token = refresh_token
            user.upwork_user_id       = upwork_id
        else:
            email         = f"{upwork_id}@upwork.local"
            username      = upwork_id
            base_username = username
            counter       = 1
            while db.query(models.User).filter(models.User.username == username).first():
                username = f"{base_username}_{counter}"
                counter += 1
            user = models.User(
                email=email,
                username=username,
                upwork_user_id=upwork_id,
                upwork_access_token=access_token,
                upwork_refresh_token=refresh_token,
            )
            db.add(user)
        db.commit()
        db.refresh(user)

    jwt_token = create_access_token(
        data={"sub": str(user.id)},
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    )
    return RedirectResponse(url=f"{FRONTEND_URL}/?token={jwt_token}&source=upwork")


@router.get("/me", response_model=schemas.UserResponse)
async def get_me(current_user: models.User = Depends(get_current_user)):
    return current_user

@router.get("/admin", response_model=schemas.AdminResponse)
async def get_me(current_user: models.User = Depends(get_current_user)):
    return current_user

