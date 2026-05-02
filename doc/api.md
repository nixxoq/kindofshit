# Kilogram Backend API

## Entities

### User

- Internal backend entity used for account management and message ownership.
- Fields:
  - `id`: snowflake `int64`
  - `username`: unique string
  - `display_name`: string
  - `hashed_password`: string (Argon2 hash)
  - `is_test_user`: boolean

### AuthToken

- Bearer token used for session authentication.
- Stores only a server-side hash of the token.
- Fields:
  - `id`: snowflake `int64`
  - `user_id`
  - `public_id`: token lookup prefix
  - `token_hash`
  - `name`
  - `last_used_at`
  - `revoked_at`

### DirectMessage

- Private dialog between exactly two users.
- Fields:
  - `id`: snowflake `int64`
  - `user_low_id`
  - `user_high_id`
  - `created_at`
  - `updated_at`

### Message

- Stored encrypted at rest.
- Fields:
  - `id`: snowflake `int64`
  - `dm_id`
  - `author_id`
  - `ciphertext`
  - `nonce`
  - `key_version`
  - `created_at`

## ID format

Kilogram uses a Discord-like snowflake:

- `41 bits`: milliseconds since custom epoch `2024-01-01T00:00:00Z`
- `10 bits`: worker identifier
- `12 bits`: per-millisecond sequence

## Auth token format

Bearer tokens use this format:

```text
kgm_<public_id>.<secret>
```

Rules:
- clients send the full token in `Authorization: Bearer <token>`
- server verifies the full token using a keyed hash
- raw tokens are never stored in the database

## Encryption

Message content is encrypted using `AES-GCM` with a 12-byte random nonce before storage. Transport security is handled via HTTPS/WSS.

## REST API

### `GET /api/health`
Returns service and database status.

### `POST /api/register`
Create a new user account. Returns an auth token immediately.

Request:
```json
{
  "username": "alice",
  "display_name": "Alice Liddell",
  "password": "super-secret-password"
}
```

Response (`201 Created`):
```json
{
  "id": 123456789012345678,
  "created_at": "2026-05-02T12:00:00Z",
  "token": "kgm_publicid.secretpart"
}
```

### `POST /api/login`
Authenticate an existing user and receive a new auth token. Logging in via this endpoint revokes previous tokens for this user.

Request:
```json
{
  "username": "alice",
  "password": "super-secret-password"
}
```

Response (`200 OK`):
```json
{
  "user_id": 123456789012345678,
  "username": "alice",
  "token": "kgm_newpublicid.newsecretpart"
}
```

### `POST /api/dms/open`
Open or fetch an existing DM with another user.

Request:
```json
{
  "recipient_id": 123456789012345678
}
```

Response:
```json
{
  "id": 123456789012345679,
  "peer_user_id": 123456789012345678,
  "created_at": "2026-05-02T12:00:00Z"
}
```

### `GET /api/dms`
List DMs for the current user.

### `GET /api/dms/{dm_id}/messages`
Fetch message history in newest-first order.
Query: `limit` (max 100), `before` (snowflake cursor).

### `POST /api/dms/{dm_id}/messages`
Send a message into a DM.

Request:
```json
{
  "content": "hello"
}
```

## WebSocket API

### `GET /ws`
Realtime event stream. Requires `Authorization: Bearer <token>`.

Lifecycle:
1. Client connects.
2. Server validates token.
3. Server replies with `ready` event.
4. Server pushes `message.created` events.

## Migrations

Kilogram uses the built-in Tortoise migration system.

```bash
tortoise makemigrations
tortoise migrate
```