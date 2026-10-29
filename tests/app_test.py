from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from wishlist.app import USERNAME_MAX_CHARS, create_app

CONFIG = """
title = "Test list"
[want]
min = 1
max = 5
[[items]]
id = "pen"
label = "Pen"
want = 4
[[items]]
id = "socks"
label = "Socks"
"""


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    config = tmp_path / "config.toml"
    config.write_text(CONFIG)
    with TestClient(create_app(config, tmp_path / "data" / "db.sqlite")) as test_client:
        yield test_client


def givers(client: TestClient, item_id: str) -> list[str]:
    items = client.get("/api/wishlist").json()["items"]
    return next(item["givers"] for item in items if item["id"] == item_id)


def test_wishlist_reflects_config(client: TestClient) -> None:
    body = client.get("/api/wishlist").json()

    assert body["title"] == "Test list"
    assert body["want"] == {"min": 1, "max": 5}
    assert [(i["id"], i["want"]) for i in body["items"]] == [("pen", 4), ("socks", 1)]


def test_many_people_can_pledge_one_item_once_each(client: TestClient) -> None:
    for name in ["Anna", "Bob", "Anna"]:
        assert client.post("/api/items/pen/pledges", json={"username": name}).status_code == 204

    assert givers(client, "pen") == ["Anna", "Bob"]
    assert givers(client, "socks") == []


def test_withdraw_removes_only_that_username(client: TestClient) -> None:
    client.post("/api/items/pen/pledges", json={"username": "Anna"})
    client.post("/api/items/pen/pledges", json={"username": "Bob"})

    response = client.request("DELETE", "/api/items/pen/pledges", json={"username": "Anna"})

    assert response.status_code == 204
    assert givers(client, "pen") == ["Bob"]


def test_username_whitespace_is_collapsed(client: TestClient) -> None:
    client.post("/api/items/pen/pledges", json={"username": "  Aunt   May "})

    assert givers(client, "pen") == ["Aunt May"]


@pytest.mark.parametrize("username", ["", "   ", "x" * (USERNAME_MAX_CHARS + 1)])
def test_bad_username_is_rejected(client: TestClient, username: str) -> None:
    response = client.post("/api/items/pen/pledges", json={"username": username})

    assert response.status_code == 422


def test_unknown_item_is_404(client: TestClient) -> None:
    response = client.post("/api/items/nope/pledges", json={"username": "Anna"})

    assert response.status_code == 404


def test_config_edit_is_picked_up_without_restart(client: TestClient, tmp_path: Path) -> None:
    config = tmp_path / "config.toml"
    config.write_text(CONFIG.replace('label = "Pen"', 'label = "Fountain pen"'))

    labels = [i["label"] for i in client.get("/api/wishlist").json()["items"]]

    assert labels[0] == "Fountain pen"


def test_frontend_is_served(client: TestClient) -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert "app.js" in response.text
