import pytest
from app.services.rule_service import matches_keyword


@pytest.mark.asyncio
async def test_create_rule(client):
    response = await client.post("/rules", json={
        "keyword": "PRICE",
        "dm_message": "Here is our price list: $10"
    })
    assert response.status_code == 201
    data = response.json()
    assert data["keyword"] == "PRICE"
    assert data["dm_message"] == "Here is our price list: $10"
    assert "rule_id" in data


def test_keyword_matching_cases():
    keyword = "PRICE"

    # Exact matches
    assert matches_keyword("PRICE", keyword) is True
    assert matches_keyword("price", keyword) is True

    # Matching anywhere in text
    assert matches_keyword("price please", keyword) is True
    assert matches_keyword("Can I get the PRICE?", keyword) is True
    assert matches_keyword("what is the price?", keyword) is True
    assert matches_keyword("PRICE🙏", keyword) is True

    # Nonmatching comments
    assert matches_keyword("pricing", keyword) is False
    assert matches_keyword("overpriced", keyword) is False
    assert matches_keyword("hello world", keyword) is False
