"""Autenticación JWT y hashing de contraseñas."""
import datetime as dt
import os
from functools import wraps

import jwt
from flask import g, jsonify, request
from werkzeug.security import check_password_hash, generate_password_hash

from logger import log_unauthorized_access

SECRET_KEY = os.environ.get("JWT_SECRET_KEY", "qa-reports-app-dev-secret-key-change-in-production")
ALGORITHM = "HS256"
TOKEN_TTL_MINUTES = int(os.environ.get("JWT_TTL_MINUTES", "60"))

# Usuarios de prueba. Las contraseñas solo se almacenan como hash (PBKDF2/scrypt de Werkzeug).
USERS = {
    "admin@test.com": {
        "name": "Admin QA",
        "role": "Lead QA",
        "password_hash": generate_password_hash("SecurePassword123"),
    },
}


def authenticate(email: str, password: str):
    """Valida credenciales. Devuelve los datos públicos del usuario o ``None``."""
    user = USERS.get((email or "").strip().lower())
    if user is None or not check_password_hash(user["password_hash"], password or ""):
        return None
    return {"name": user["name"], "role": user["role"]}


def create_token(email: str, user: dict) -> str:
    now = dt.datetime.now(dt.timezone.utc)
    payload = {
        "sub": email.strip().lower(),
        "name": user["name"],
        "role": user["role"],
        "iat": now,
        "exp": now + dt.timedelta(minutes=TOKEN_TTL_MINUTES),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> dict:
    """Decodifica y valida firma/expiración. Lanza ``jwt.InvalidTokenError`` si no es válido."""
    return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM], options={"require": ["sub", "exp"]})


def token_required(view):
    """Decorador que exige la cabecera ``Authorization: Bearer <token>``."""

    @wraps(view)
    def wrapper(*args, **kwargs):
        header = request.headers.get("Authorization", "")
        scheme, _, token = header.partition(" ")
        if scheme.lower() != "bearer" or not token.strip():
            log_unauthorized_access(request.path, request.remote_addr, "token ausente")
            return jsonify({"error": "Token de autenticación requerido"}), 401
        try:
            g.current_user = decode_token(token.strip())
        except jwt.ExpiredSignatureError:
            log_unauthorized_access(request.path, request.remote_addr, "token expirado")
            return jsonify({"error": "El token ha expirado"}), 401
        except jwt.InvalidTokenError:
            log_unauthorized_access(request.path, request.remote_addr, "token inválido")
            return jsonify({"error": "Token inválido"}), 401
        return view(*args, **kwargs)

    return wrapper
