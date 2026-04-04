# API Reference — Shooting Scoring System

Base URL: `http://localhost:8000`

---

## Shots

### `POST /shot`

Register a new shot from the CV pipeline.

**Request body:**
```json
{
  "x_mm": 12.4,
  "y_mm": -8.7,
  "timestamp": "2024-05-14T08:01:00Z",
  "session_id": "session-abc123",
  "metadata": {
    "frame_id": 1042,
    "confidence": 0.97
  }
}
```

**Response `201`:**
```json
{
  "id": "shot-uuid",
  "x_mm": 12.4,
  "y_mm": -8.7,
  "score": 9,
  "ring": "9",
  "radius_mm": 15.2,
  "timestamp": "2024-05-14T08:01:00Z",
  "session_id": "session-abc123"
}
```

---

### `GET /latest`

Returns the most recently registered shot.

**Response `200`:** Single shot object (same schema as POST response), or `null` if no shots yet.

---

### `GET /history`

Returns paginated shot history, newest first.

**Query params:**
| Param    | Type | Default | Description           |
|----------|------|---------|-----------------------|
| `limit`  | int  | 200     | Max records           |
| `offset` | int  | 0       | Pagination offset     |
| `session_id` | str | — | Filter by session   |

**Response `200`:**
```json
{
  "shots": [ /* array of shot objects */ ],
  "total": 42,
  "limit": 200,
  "offset": 0
}
```

---

### `DELETE /shots`

Deletes all shots in the current session (reset).

**Response `204`:** No content.

---

## Statistics

### `GET /stats`

Returns aggregated analytics for all shots (or filtered by session).

**Query params:** `session_id` (optional)

**Response `200`:**
```json
{
  "count": 20,
  "total_score": 164,
  "avg_score": 8.2,
  "cep_mm": 28.4,
  "r50_mm": 14.1,
  "group_size_mm": 182.3,
  "mean_poi": { "x_mm": 1.2, "y_mm": -3.4 },
  "hit_rate": 1.0,
  "ring_distribution": {
    "X": 2, "10": 3, "9": 4, "8": 2, "7": 3,
    "6": 2, "5": 2, "4": 1, "3": 1, "2": 0, "1": 0, "M": 0
  }
}
```

---

### `GET /heatmap`

Returns a 2D density grid of hit positions.

**Query params:**
| Param       | Type | Default | Description              |
|-------------|------|---------|--------------------------|
| `resolution`| int  | 50      | Grid cells per axis (NxN)|

**Response `200`:**
```json
{
  "resolution": 50,
  "target_radius_mm": 225,
  "grid": [ /* 50x50 array of hit counts */ ]
}
```

---

## WebSocket

### `WS /ws/shots`

Real-time push of new shot events. Connect once; the server pushes a JSON shot object for every new `POST /shot`.

**Message format:** Same as `POST /shot` response object.

**Example (JavaScript):**
```js
const ws = new WebSocket('ws://localhost:8000/ws/shots');
ws.onmessage = (e) => {
  const shot = JSON.parse(e.data);
  console.log('New shot:', shot.score, 'at', shot.x_mm, shot.y_mm);
};
```

---

## Errors

All errors return:
```json
{ "detail": "Human-readable error message" }
```

| Code | Meaning              |
|------|----------------------|
| 400  | Validation error     |
| 404  | Resource not found   |
| 422  | Unprocessable entity |
| 500  | Internal server error|