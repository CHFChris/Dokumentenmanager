from fastapi import APIRouter, Depends
from app.api.deps import get_current_user, CurrentUser
from app.schemas.user import UserOut

router = APIRouter(prefix="/users", tags=["users"])

@router.get("/me", response_model=UserOut)
def me(user: CurrentUser = Depends(get_current_user)):
    return {"id": user.id, "email": user.email}
