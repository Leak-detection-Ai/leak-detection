from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import current_user
from app.db.session import get_db
from app.models.models import User
from app.schemas.schemas import UserOut
from app.services.audit import audit


router = APIRouter(
    prefix="/profile",
    tags=["profile"],
)


class ProfileUpdate(BaseModel):
    email: EmailStr


@router.get(
    "",
    response_model=UserOut,
)
def get_profile(
    user: User = Depends(current_user),
):
    return user


@router.patch(
    "",
    response_model=UserOut,
)
def update_profile(
    data: ProfileUpdate,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    new_email = str(
        data.email
    ).lower().strip()

    # No change.
    if new_email == user.email:
        return user

    existing = (
        db.query(User)
        .filter(
            User.email == new_email,
            User.id != user.id,
        )
        .first()
    )

    if existing:
        raise HTTPException(
            status_code=409,
            detail="Email address is already registered",
        )

    old_email = user.email

    user.email = new_email

    audit(
        db,
        user.id,
        "PROFILE_UPDATED",
        "user",
        user.id,
        metadata={
            "old_email": old_email,
            "new_email": new_email,
        },
    )

    try:
        db.commit()
        db.refresh(user)

    except IntegrityError:
        db.rollback()

        raise HTTPException(
            status_code=409,
            detail="Email address is already registered",
        )

    return user