import logging
import smtplib
import ssl
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from hashlib import sha256
from typing import Annotated
from uuid import uuid4

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerificationError
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response
from fastapi.concurrency import run_in_threadpool
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import database
from app.models import RefreshToken, User

router = APIRouter(prefix="/auth", tags=["Authentication"])
DB = Annotated[AsyncSession, Depends(database)]
bearer = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")
passwords = PasswordHasher()
COOKIE = "assistant_refresh"
logger = logging.getLogger(__name__)


def now():
    return datetime.now(timezone.utc)


def digest(value: str):
    return sha256(value.encode()).hexdigest()


def decode(value: str, kind: str):
    try:
        claims = jwt.decode(value, settings().jwt_secret_key, algorithms=["HS256"],
                            options={"require": ["sub", "typ", "exp", "jti"]})
        if claims["typ"] == kind:
            return claims
    except jwt.InvalidTokenError:
        pass
    raise HTTPException(401, "Invalid or expired credentials")


def issue(db: AsyncSession, response: Response, user_id: str):
    config = settings()
    refresh_exp = now() + timedelta(days=config.refresh_days)

    def encode(kind: str, expires: datetime):
        return jwt.encode({"sub": user_id, "typ": kind, "exp": expires,
                           "iat": now(), "jti": str(uuid4())}, config.jwt_secret_key, algorithm="HS256")

    refresh = encode("refresh", refresh_exp)
    db.add(RefreshToken(user_id=user_id, token_hash=digest(refresh), expires_at=refresh_exp))
    response.set_cookie(COOKIE, refresh, httponly=True, secure=config.secure_cookies,
                        samesite="strict", path="/api/v1/auth", max_age=config.refresh_days * 86400)
    response.headers["Cache-Control"] = "no-store"
    return {"access_token": encode("access", now() + timedelta(minutes=config.access_token_expire_minutes)),
            "token_type": "bearer"}


async def current_user(db: DB, value: Annotated[str, Depends(bearer)]):
    user = await db.get(User, decode(value, "access")["sub"])
    if not user:
        raise HTTPException(401, "Invalid credentials")
    return user


Actor = Annotated[User, Depends(current_user)]


async def rate(request: Request, key: str, limit: int):
    bucket = f"rate:{key}:{int(now().timestamp()) // 60}"
    async with request.app.state.redis.pipeline(transaction=True) as pipe:
        pipe.incr(bucket)
        pipe.expire(bucket, 60)
        count, _ = await pipe.execute()
    if count > limit:
        raise HTTPException(429, "Too many requests", headers={"Retry-After": "60"})


class Login(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class Registration(Login):
    full_name: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=12, max_length=128)


class Profile(BaseModel):
    full_name: str = Field(min_length=1, max_length=100)
    theme: str = Field(pattern="^(light|dark)$")
    model: str = Field(default="", max_length=150)


@router.post("/register", status_code=201)
async def register(data: Registration, request: Request, response: Response, db: DB):
    await rate(request, f"register:{request.client.host}", 5)
    if not data.full_name.strip():
        raise HTTPException(422, "Name is required")
    user = User(email=data.email.lower(), full_name=data.full_name.strip(),
                password_hash=await run_in_threadpool(passwords.hash, data.password))
    db.add(user)
    try:
        await db.flush()
        result = issue(db, response, user.id)
        await db.commit()
    except IntegrityError as exc:
        raise HTTPException(409, "Email already registered") from exc
    return result


@router.post("/login")
async def login(request: Request, response: Response, db: DB):
    await rate(request, f"login:{request.client.host}", 15)
    try:
        if request.headers.get("content-type", "").startswith("application/json"):
            raw = await request.json()
        else:
            form = await request.form()
            raw = {"email": form.get("username"), "password": form.get("password")}
        data = Login.model_validate(raw)
    except ValueError as exc:
        raise HTTPException(422, "Enter a valid email and password") from exc
    user = await db.scalar(select(User).where(User.email == data.email.lower()).with_for_update())
    try:
        if not user or not await run_in_threadpool(passwords.verify, user.password_hash, data.password):
            raise HTTPException(401, "Invalid credentials")
    except VerificationError as exc:
        raise HTTPException(401, "Invalid credentials") from exc
    result = issue(db, response, user.id)
    await db.commit()
    return result


@router.post("/refresh")
async def refresh(request: Request, response: Response, db: DB):
    await rate(request, f"refresh:{request.client.host}", 60)
    value = request.cookies.get(COOKIE, "")
    claims = decode(value, "refresh")
    await db.scalar(select(User.id).where(User.id == claims["sub"]).with_for_update())
    owner = await db.scalar(update(RefreshToken).where(
        RefreshToken.token_hash == digest(value), RefreshToken.user_id == claims["sub"],
        RefreshToken.revoked_at.is_(None), RefreshToken.expires_at > now(),
    ).values(revoked_at=now()).returning(RefreshToken.user_id))
    if not owner:
        raise HTTPException(401, "Session expired")
    result = issue(db, response, owner)
    await db.commit()
    return result


@router.post("/logout", status_code=204)
async def logout(request: Request, response: Response, db: DB):
    value = request.cookies.get(COOKIE)
    if value:
        await db.execute(update(RefreshToken).where(
            RefreshToken.token_hash == digest(value), RefreshToken.revoked_at.is_(None),
        ).values(revoked_at=now()))
        await db.commit()
    response.delete_cookie(COOKIE, path="/api/v1/auth")


@router.get("/me")
async def me(user: Actor):
    return {"id": user.id, "email": user.email, "full_name": user.full_name,
            "role": user.role, "preferences": user.preferences}


@router.patch("/me")
async def profile(data: Profile, db: DB, user: Actor):
    if not data.full_name.strip():
        raise HTTPException(422, "Name is required")
    if data.model and data.model not in settings().groq_models.split(","):
        raise HTTPException(422, "Unknown model")
    user.full_name = data.full_name.strip()
    user.preferences = {"theme": data.theme, "model": data.model}
    await db.commit()
    return await me(user)


class ResetRequest(BaseModel):
    email: EmailStr


class ResetConfirm(BaseModel):
    token: str = Field(max_length=2048)
    password: str = Field(min_length=12, max_length=128)


def send_reset(recipient: str, value: str):
    config = settings()
    message = EmailMessage()
    message["Subject"] = "Reset your Agentic AI password"
    message["From"] = config.reset_sender
    message["To"] = recipient
    message.set_content(f"Reset your password within 30 minutes: "
                        f"{config.public_app_url.rstrip('/')}/reset#token={value}")
    try:
        with smtplib.SMTP(config.smtp_host, config.smtp_port, timeout=10) as client:
            client.starttls(context=ssl.create_default_context())
            if config.smtp_user:
                client.login(config.smtp_user, config.smtp_password)
            client.send_message(message)
    except (OSError, smtplib.SMTPException):
        logger.warning("Password reset delivery failed")


@router.post("/password-reset/request", status_code=202)
async def request_reset(data: ResetRequest, request: Request, db: DB, tasks: BackgroundTasks):
    await rate(request, f"reset:{request.client.host}", 5)
    config = settings()
    if not config.smtp_host or not config.reset_sender:
        raise HTTPException(503, "Password reset delivery is unavailable")
    user = await db.scalar(select(User).where(User.email == data.email.lower()))
    if user:
        expires = now() + timedelta(minutes=30)
        value = jwt.encode({"sub": user.id, "typ": "password_reset", "exp": expires, "jti": str(uuid4())},
                           config.jwt_secret_key, algorithm="HS256")
        db.add(RefreshToken(user_id=user.id, token_hash=digest(value), expires_at=expires))
        await db.commit()
        tasks.add_task(send_reset, user.email, value)
    return {"message": "If the account exists, a reset link will be sent."}


@router.post("/password-reset/confirm", status_code=204)
async def confirm_reset(data: ResetConfirm, request: Request, db: DB):
    await rate(request, f"reset-confirm:{request.client.host}", 10)
    claims = decode(data.token, "password_reset")
    user = await db.scalar(select(User).where(User.id == claims["sub"]).with_for_update())
    record = await db.scalar(select(RefreshToken).where(
        RefreshToken.token_hash == digest(data.token), RefreshToken.user_id == claims["sub"],
        RefreshToken.revoked_at.is_(None), RefreshToken.expires_at > now()))
    if not user or not record:
        raise HTTPException(401, "Invalid or expired reset link")
    user.password_hash = await run_in_threadpool(passwords.hash, data.password)
    await db.execute(update(RefreshToken).where(RefreshToken.user_id == user.id,
                     RefreshToken.revoked_at.is_(None)).values(revoked_at=now()))
    await db.commit()
