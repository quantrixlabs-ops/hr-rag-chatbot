"""FAQ management API routes — admin CRUD for curated Q&A pairs."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from backend.app.core.security import get_current_user, require_role
from backend.app.models.chat_models import User
from backend.app.services.faq_service import FAQService

router = APIRouter(prefix="/faq", tags=["FAQ"])
_svc = FAQService()


class FAQCreate(BaseModel):
    question: str
    answer: str
    keywords: str = ""
    category: str = "general"


class FAQUpdate(BaseModel):
    question: Optional[str] = None
    answer: Optional[str] = None
    keywords: Optional[str] = None
    category: Optional[str] = None
    is_active: Optional[bool] = None


@router.get("")
async def list_faqs(user: User = Depends(get_current_user)):
    require_role(user, "hr_team")
    return {"faqs": _svc.list_faqs()}


@router.post("")
async def create_faq(body: FAQCreate, user: User = Depends(get_current_user)):
    require_role(user, "hr_admin")
    faq_id = _svc.create_faq(
        question=body.question,
        answer=body.answer,
        keywords=body.keywords,
        category=body.category,
        created_by=user.user_id,
    )
    return {"faq_id": faq_id, "status": "created"}


@router.put("/{faq_id}")
async def update_faq(faq_id: str, body: FAQUpdate, user: User = Depends(get_current_user)):
    require_role(user, "hr_admin")
    fields = {k: v for k, v in body.dict().items() if v is not None}
    if not _svc.update_faq(faq_id, **fields):
        raise HTTPException(404, "FAQ not found")
    return {"status": "updated"}


@router.delete("/{faq_id}")
async def delete_faq(faq_id: str, user: User = Depends(get_current_user)):
    require_role(user, "hr_admin")
    if not _svc.delete_faq(faq_id):
        raise HTTPException(404, "FAQ not found")
    return {"status": "deleted"}
