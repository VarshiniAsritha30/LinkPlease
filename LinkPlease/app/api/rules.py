"""API endpoints for managing DM rules."""

from typing import List
from fastapi import APIRouter, Depends, status, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.rule import RuleCreate, RuleResponse
from app.services.rule_service import create_rule, get_active_rules

router = APIRouter(tags=["Rules"])


@router.post("/rules", response_model=RuleResponse, status_code=status.HTTP_201_CREATED)
async def api_create_rule(
    rule_in: RuleCreate,
    db: AsyncSession = Depends(get_db)
):
    """Create a new DM automation rule."""
    try:
        rule = await create_rule(db, rule_in)
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(err)
        )
    return RuleResponse(
        rule_id=rule.id,
        keyword=rule.keyword,
        dm_message=rule.dm_message,
        active=rule.active,
        created_at=rule.created_at
    )



@router.get("/rules", response_model=List[RuleResponse])
async def api_list_rules(
    db: AsyncSession = Depends(get_db)
):
    """List all active DM automation rules."""
    rules = await get_active_rules(db)
    return [
        RuleResponse(
            rule_id=r.id,
            keyword=r.keyword,
            dm_message=r.dm_message,
            active=r.active,
            created_at=r.created_at
        )
        for r in rules
    ]
