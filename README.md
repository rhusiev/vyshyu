# wishlist

A small wishlist page. The items, their descriptions and how much each one is wanted come
from a config file. Visitors open an item and mark it as something they are going to gift.
There are no accounts. The first time someone marks an item they type a name, and a cookie
keeps it on that device. Several devices can use the same name, and several people can mark
the same item. Every name gets an identicon generated from a hash of it

## Config

Copy `config.example.toml` to `config.toml`. The comments in the example describe every
field. The app re-reads the file on the next request after it changes, so edits need no
restart. An invalid file makes the API return 500 until it is fixed

Pledges are stored by item `id`, so rewording a label keeps them. Removing an item from the
config hides its pledges. Adding it back with the same `id` brings them back

## Run locally

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
cp config.example.toml config.toml
.venv/bin/uvicorn wishlist.app:app_from_env --factory --reload
.venv/bin/python -m pytest tests
```

`WISHLIST_CONFIG` (default `config.toml`) and `WISHLIST_DB` (default `data/wishlist.db`)
point the app at its files

## API

- `GET /api/wishlist` returns the config plus `givers` for each item, oldest pledge first
- `POST /api/items/{id}/pledges` with `{"username": "..."}` adds a pledge. Repeating it does nothing
- `DELETE /api/items/{id}/pledges` with the same body withdraws it

Usernames have their whitespace collapsed and are limited to 40 characters. Nothing checks
who sends a request, so anyone can add or withdraw a pledge under any name. That is the
intended trade-off for a page with no login

## Deploy

`docker-compose.yml` builds the image and joins the external `caddy` network, where a
reverse proxy forwards to `wishlist:8000`. `config.toml` is mounted read-only and the SQLite
database lives in `./data`, which must be writable by uid 1000
