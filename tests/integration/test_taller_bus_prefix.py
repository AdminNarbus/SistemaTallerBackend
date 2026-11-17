import pytest

from app.modules.buses.models.bus import Bus


@pytest.mark.parametrize("query,expected", [
    ("1", {"1", "10", "123"}),
    (" 12 ", {"123"}),
    ("abc", {"1", "10", "123", "21", "315"}),
    ("%", set()),
    ("_", set()),
])
async def test_taller_bus_search_matches_only_prefix(
    client, db_session, auth_headers_mecanico1, query, expected,
):
    db_session.add_all([
        Bus(n_bus=number, patente=f"ABC-{number}", is_active=True)
        for number in ("1", "10", "123", "21", "315")
    ])
    await db_session.commit()

    response = await client.get("/api/v1/taller/buses", headers=auth_headers_mecanico1, params={"q": query})

    assert response.status_code == 200, response.text
    assert {item["n_bus"] for item in response.json()} == expected
    assert response.headers["X-Total-Count"] == str(len(expected))
