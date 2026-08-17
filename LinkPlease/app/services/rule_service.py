"""Rule management and keyword matching service."""

import re
import logging
from typing import List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.rule import Rule
from app.schemas.rule import RuleCreate

logger = logging.getLogger(__name__)


async def get_rule_by_keyword(db: AsyncSession, keyword: str) -> Optional[Rule]:
    """Retrieve an active rule by keyword (case-insensitive)."""
    stmt = select(Rule).where(
        Rule.active == True,
        Rule.keyword.ilike(keyword.strip())
    )
    result = await db.execute(stmt)
    return result.scalars().first()


async def create_rule(db: AsyncSession, rule_in: RuleCreate) -> Rule:
    """Create a new DM automation rule. Prevents duplicate active keywords."""
    keyword_normalized = rule_in.keyword.strip()
    existing_rule = await get_rule_by_keyword(db, keyword_normalized)
    if existing_rule:
        raise ValueError(f"Rule with keyword '{keyword_normalized}' already exists.")

    rule = Rule(
        keyword=keyword_normalized,
        dm_message=rule_in.dm_message.strip(),
        active=True
    )
    db.add(rule)
    await db.commit()
    await db.refresh(rule)
    logger.info(f"Rule created: id={rule.id}, keyword='{rule.keyword}'")
    return rule


async def clean_duplicate_rules(db: AsyncSession) -> int:
    """
    Find active rules with duplicate keywords (case-insensitive)
    and deactivate all but the oldest rule for each keyword.
    Returns the count of deactivated rules.
    """
    stmt = select(Rule).where(Rule.active == True).order_by(Rule.created_at.asc())
    result = await db.execute(stmt)
    all_active_rules = result.scalars().all()

    seen_keywords = set()
    deactivated_count = 0

    for rule in all_active_rules:
        normalized_keyword = rule.keyword.strip().lower()
        if normalized_keyword in seen_keywords:
            rule.active = False
            deactivated_count += 1
            logger.info(f"Deactivated duplicate rule: id={rule.id}, keyword='{rule.keyword}'")
        else:
            seen_keywords.add(normalized_keyword)

    if deactivated_count > 0:
        await db.commit()
        logger.info(f"Cleaned up duplicate rules. Deactivated {deactivated_count} rules.")

    return deactivated_count



async def get_active_rules(db: AsyncSession) -> List[Rule]:
    """Retrieve all active rules."""
    result = await db.execute(select(Rule).where(Rule.active == True))
    return list(result.scalars().all())


def matches_keyword(text: str, keyword: str) -> bool:
    """
    Case-insensitive word boundary match anywhere in comment text.
    Example: keyword 'PRICE' matches 'PRICE please' but NOT 'pricing'.
    """
    if not text or not keyword:
        return False
    pattern = r'\b' + re.escape(keyword) + r'\b'
    return bool(re.search(pattern, text, flags=re.IGNORECASE))


async def find_matching_rules(db: AsyncSession, text: str) -> List[Rule]:
    """Find all active rules matching the comment text."""
    rules = await get_active_rules(db)
    matching = [rule for rule in rules if matches_keyword(text, rule.keyword)]
    return matching
