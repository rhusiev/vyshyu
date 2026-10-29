# wishlist

A small wishlist page in English and Ukrainian. The items, their descriptions and how much
each one is wanted come from a config file. Visitors open an item and mark it as something
they are going to gift. The first time someone marks an item they type a name, and a cookie
keeps it on that device. Several devices can use the same name, and several people can mark
the same item. Every name gets an identicon generated from a hash of it

The page picks its language from the browser and remembers the visitor's choice of the
EN/УК switch in `localStorage`. Interface strings live in `static/i18n.js`

## Google sign-in

Signing in is optional. A signed-in visitor reserves a name: from then on nobody else can
pledge or withdraw under it, in any letter case, and their pledges follow the account to
any device. The server keeps only Google's account id (`sub`), never the email. The visitor
can rename themselves, which moves their pledges to the new name

A name can be reserved only while nobody else uses it: if another account has it, or anyone
pledged under it without signing in (in any letter case), the reservation is refused. Those
pledges are never taken over, since nothing records whose they are

To enable it, create an OAuth client of type "Web application" in the Google Cloud console
(APIs & Services, Credentials) with `https://wishlist.r1a.nl` as an authorized JavaScript
origin. No redirect URI is needed. Then put this in `.env` next to `docker-compose.yml`:

```sh
GOOGLE_CLIENT_ID=<id>.apps.googleusercontent.com
WISHLIST_SECRET_KEY=<output of: python3 -c "import secrets; print(secrets.token_urlsafe(32))">
```

The secret key signs the session cookie. Changing it signs everyone out. Without
`GOOGLE_CLIENT_ID` the Google button is hidden and everything else works the same.
wishlist.r1a.nl runs without it for now: Google keeps a new OAuth app in testing mode, where
only test users added by hand can sign in

## Config

Copy `config.example.toml` to `config.toml`. The comments in the example describe every
field, including how to give text in both languages and how to group items. A group is a
foldable section with its own heading. `folded = true` starts it closed. A visitor's own
folding lasts until they reload the page. Items outside any group come first, with no heading. The app re-reads the file on the next request after it changes, so edits need no
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
point the app at its files. The session cookie is HTTPS-only unless
`WISHLIST_SECURE_COOKIES=0`, which plain-HTTP local runs need for sign-in to stick

## API

- `GET /api/wishlist` returns the config as `groups`, each `{"id", "label", "folded",
  "items"}`. The ungrouped items, if any, come first as a group with `id` and `label` null.
  Each item carries its `givers`, oldest pledge first, as `{"username", "protected"}`
- `POST /api/items/{id}/pledges` with `{"username": "..."}` adds a pledge. Repeating it does
  nothing. Signed-in visitors always pledge under their reserved name, whatever the body says
- `DELETE /api/items/{id}/pledges` with the same body withdraws it
- Both return 403 for an anonymous request under a reserved name
- `GET /api/usernames/{name}` returns `{"reserved": bool}`
- `GET /api/session` returns `google_client_id`, `signed_in` and the reserved `username`
- `POST /api/session/google` with `{"credential": "<ID token>"}` signs in
- `PUT /api/session/username` with `{"username": "..."}` reserves or changes the name. 409
  if another account has it or anyone else pledged under it
- `DELETE /api/session` signs out

Usernames have their whitespace collapsed and are limited to 40 characters. Names that no
account reserved are unprotected: anyone can add or withdraw a pledge under them

## Deploy

`docker-compose.yml` builds the image and joins the external `caddy` network, where a
reverse proxy forwards to `wishlist:8000`. `config.toml` is mounted read-only and the SQLite
database lives in `./data`, which must be writable by uid 1000
