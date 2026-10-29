from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from wishlist.app import USERNAME_MAX_CHARS, Settings, create_app
from wishlist.auth import InvalidCredentialError

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


def fake_verify(credential: str) -> str:
    """Treat 'token-<sub>' as a valid credential for account <sub>."""
    if not credential.startswith("token-"):
        raise InvalidCredentialError(credential)
    return credential.removeprefix("token-")


GROUPED_CONFIG = """
[want]
min = 1
max = 3
[[items]]
id = "loose"
label = "Loose"
[[groups]]
id = "games"
label = { en = "Board games", uk = "Настільні ігри" }
folded = true
[[groups.items]]
id = "wingspan"
label = "Wingspan"
"""


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    config = tmp_path / "config.toml"
    config.write_text(CONFIG)
    settings = Settings(
        config_path=config,
        db_path=tmp_path / "data" / "db.sqlite",
        google_client_id="test-client",
        secret_key="test-secret",
        secure_cookies=False,
    )
    with TestClient(create_app(settings, fake_verify)) as test_client:
        yield test_client


@pytest.fixture
def other_client(client: TestClient) -> TestClient:
    """A second browser against the same app, with its own cookies."""
    return TestClient(client.app)


def all_items(client: TestClient) -> list[dict]:
    groups = client.get("/api/wishlist").json()["groups"]
    return [item for group in groups for item in group["items"]]


def givers(client: TestClient, item_id: str) -> list[str]:
    item = next(item for item in all_items(client) if item["id"] == item_id)
    return [giver["username"] for giver in item["givers"]]


def sign_in(client: TestClient, sub: str, username: str | None = None) -> None:
    assert client.post("/api/session/google", json={"credential": f"token-{sub}"}).is_success
    if username is not None:
        response = client.put("/api/session/username", json={"username": username})
        assert response.is_success


def test_wishlist_reflects_config(client: TestClient) -> None:
    body = client.get("/api/wishlist").json()

    assert body["title"] == "Test list"
    assert body["want"] == {"min": 1, "max": 5}
    assert [(i["id"], i["want"]) for i in all_items(client)] == [("pen", 4), ("socks", 1)]


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


@pytest.mark.parametrize("username", [None, "", "   ", "x" * (USERNAME_MAX_CHARS + 1)])
def test_bad_username_is_rejected(client: TestClient, username: str) -> None:
    response = client.post("/api/items/pen/pledges", json={"username": username})

    assert response.status_code == 422
    assert givers(client, "pen") == []


def test_unknown_item_is_404(client: TestClient) -> None:
    response = client.post("/api/items/nope/pledges", json={"username": "Anna"})

    assert response.status_code == 404


def test_config_edit_is_picked_up_without_restart(client: TestClient, tmp_path: Path) -> None:
    config = tmp_path / "config.toml"
    config.write_text(CONFIG.replace('label = "Pen"', 'label = "Fountain pen"'))

    labels = [i["label"] for i in all_items(client)]

    assert labels[0] == "Fountain pen"


def test_frontend_is_served(client: TestClient) -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert "app.js" in response.text


def test_reserved_name_is_marked_protected(client: TestClient, other_client: TestClient) -> None:
    other_client.post("/api/items/pen/pledges", json={"username": "Bob"})
    sign_in(client, "anna-sub", "Anna")
    client.post("/api/items/pen/pledges", json={})

    item = all_items(client)[0]

    assert item["givers"] == [
        {"username": "Bob", "protected": False},
        {"username": "Anna", "protected": True},
    ]


@pytest.mark.parametrize("method", ["POST", "DELETE"])
def test_anonymous_cannot_use_reserved_name_in_any_case(
    client: TestClient, other_client: TestClient, method: str
) -> None:
    sign_in(client, "anna-sub", "Anna")
    client.post("/api/items/pen/pledges", json={})

    response = other_client.request(method, "/api/items/pen/pledges", json={"username": "aNNA"})

    assert response.status_code == 403
    assert givers(client, "pen") == ["Anna"]


def test_signed_in_pledge_ignores_body_username(client: TestClient) -> None:
    sign_in(client, "anna-sub", "Anna")

    client.post("/api/items/pen/pledges", json={"username": "Mallory"})

    assert givers(client, "pen") == ["Anna"]


def test_signed_in_without_name_cannot_pledge(client: TestClient) -> None:
    sign_in(client, "anna-sub")

    response = client.post("/api/items/pen/pledges", json={})

    assert response.status_code == 409


def test_second_account_cannot_reserve_taken_name(
    client: TestClient, other_client: TestClient
) -> None:
    sign_in(client, "anna-sub", "Anna")
    sign_in(other_client, "eve-sub")

    response = other_client.put("/api/session/username", json={"username": "anna"})

    assert response.status_code == 409


def test_rename_moves_pledges(client: TestClient) -> None:
    sign_in(client, "anna-sub", "Anna")
    client.post("/api/items/pen/pledges", json={})

    sign_in(client, "anna-sub", "Anna K")

    assert givers(client, "pen") == ["Anna K"]
    assert client.get("/api/usernames/Anna").json() == {"reserved": False}


def test_session_survives_and_sign_out_ends_it(client: TestClient) -> None:
    sign_in(client, "anna-sub", "Anna")
    assert client.get("/api/session").json()["username"] == "Anna"

    client.delete("/api/session")

    assert client.get("/api/session").json() == {
        "google_client_id": "test-client",
        "signed_in": False,
        "username": None,
    }


def test_invalid_google_credential_is_401(client: TestClient) -> None:
    response = client.post("/api/session/google", json={"credential": "forged"})

    assert response.status_code == 401
    assert client.get("/api/session").json()["signed_in"] is False


def test_google_disabled_without_client_id(tmp_path: Path) -> None:
    config = tmp_path / "config.toml"
    config.write_text(CONFIG)
    settings = Settings(config_path=config, db_path=tmp_path / "db.sqlite")
    with TestClient(create_app(settings)) as client:
        assert client.get("/api/session").json()["google_client_id"] is None
        response = client.post("/api/session/google", json={"credential": "token-x"})

    assert response.status_code == 404


@pytest.mark.parametrize("anonymous_name", ["Anna", "aNNA"])
def test_cannot_reserve_name_someone_pledged_under(
    client: TestClient, other_client: TestClient, anonymous_name: str
) -> None:
    other_client.post("/api/items/pen/pledges", json={"username": anonymous_name})
    sign_in(client, "anna-sub")

    response = client.put("/api/session/username", json={"username": "Anna"})

    assert response.status_code == 409
    assert client.get("/api/session").json()["username"] is None
    assert givers(client, "pen") == [anonymous_name]
    assert other_client.get("/api/usernames/Anna").json() == {"reserved": False}


def test_cannot_rename_onto_name_someone_pledged_under(
    client: TestClient, other_client: TestClient
) -> None:
    other_client.post("/api/items/socks/pledges", json={"username": "Bob"})
    sign_in(client, "anna-sub", "Anna")
    client.post("/api/items/pen/pledges", json={})

    response = client.put("/api/session/username", json={"username": "Bob"})

    assert response.status_code == 409
    assert givers(client, "pen") == ["Anna"]
    assert givers(client, "socks") == ["Bob"]


def test_cyrillic_names_compare_case_insensitively(
    client: TestClient, other_client: TestClient
) -> None:
    other_client.post("/api/items/pen/pledges", json={"username": "аня"})
    sign_in(client, "anya-sub")

    response = client.put("/api/session/username", json={"username": "Аня"})

    assert response.status_code == 409


def test_account_can_recase_its_own_pledged_name(client: TestClient) -> None:
    sign_in(client, "anna-sub", "Anna")
    client.post("/api/items/pen/pledges", json={})

    sign_in(client, "anna-sub", "ANNA")

    assert givers(client, "pen") == ["ANNA"]


def test_groups_come_after_ungrouped_items_and_accept_pledges(tmp_path: Path) -> None:
    config = tmp_path / "config.toml"
    config.write_text(GROUPED_CONFIG)
    settings = Settings(config_path=config, db_path=tmp_path / "db.sqlite")
    with TestClient(create_app(settings)) as grouped:
        grouped.post("/api/items/wingspan/pledges", json={"username": "Anna"})
        groups = grouped.get("/api/wishlist").json()["groups"]

    assert [(g["id"], g["label"], g["folded"]) for g in groups] == [
        (None, None, False),
        ("games", {"en": "Board games", "uk": "Настільні ігри"}, True),
    ]
    assert [i["id"] for i in groups[0]["items"]] == ["loose"]
    assert groups[1]["items"][0]["givers"] == [{"username": "Anna", "protected": False}]
