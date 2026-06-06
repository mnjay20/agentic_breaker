from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from auragrid.config import settings

security = HTTPBearer()

def verify_agent_token(credentials: HTTPAuthorizationCredentials = Depends(security)) -> str:
    """Verifies that the incoming Bearer token matches the configured agent_token."""
    if credentials.credentials != settings.agent_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing secure agent token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return credentials.credentials
