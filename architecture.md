# 🎯 System Architecture & Detailed Workflow

## Overview

This document provides a comprehensive technical description of the **Shooting Scoring System** architecture, explaining how each component works together to create a real-time automated shooting scoring pipeline.

The system pipeline flows as follows:
```
3D Simulation Engine → Computer Vision → Backend API → Web Dashboard
                                             ↓
                                         Database
                                             ↓
                                         ESP32 Device
```

---

## Table of Contents

1. [System Components](#system-components)
2. [Data Flow Pipeline](#data-flow-pipeline)
3. [Component Details](#component-details)
4. [Communication Protocols](#communication-protocols)
5. [Key Design Patterns](#key-design-patterns)

---

## System Components

### 1. **Computer Vision Module** (`cv/DetectBullets/`)
- **Purpose**: Detects bullet impacts on targets from video streams
- **Input**: Video frames (webcam, RTSP stream, or recorded video)
- **Output**: Bullet coordinates (x_mm, y_mm) with metadata
- **Technology**: Python + OpenCV + ArUco markers

### 2. **Backend API** (`backend/`)
- **Purpose**: Receives shots from CV, scores them, stores in database, broadcasts to clients
- **Framework**: FastAPI (async Python web framework)
- **Port**: 8000
- **Endpoints**: REST + WebSocket
- **Database**: Firebase Firestore (with in-memory fallback)

### 3. **Web Dashboard** (`web/`)
- **Purpose**: Real-time visualization of shots, statistics, heatmaps, and reports
- **Framework**: React + Vite
- **Port**: 3000 (dev) / 5173 (build)
- **Communication**: HTTP REST + WebSocket for live updates

### 4. **ESP32-S3 Device** (`esp/`)
- **Purpose**: Embedded client that displays real-time scoring statistics on an LCD screen
- **Display**: 170×320 LVGL UI with SH8601 LCD controller
- **Connectivity**: WiFi (planned for WebSocket communication with backend)
- **Status**: Currently has test UI; network integration in progress

---

## Data Flow Pipeline

### Complete Workflow Sequence

#### **Phase 1: Bullet Detection (CV Module)**

```
Input Video Stream (30 FPS)
        ↓
[ArUco Board Detection]
    - Detects 4 ArUco markers defining target corners
    - Calculates homography matrix for perspective correction
        ↓
[Thread Pool - Per Target]
    - 3 parallel workers: BIA_TRON, BIA_IPSC, BIA_NGUOI
        ↓
[Layer 1: Background Subtraction & Masking]
    - Separates foreground (bullet holes) from background
    - Identifies dark spots where bullets impacted
        ↓
[Layer 2: Blob Detection & Hough Transform]
    - Detects circular shapes in masked regions
    - Refines circle candidates using circle fitting
        ↓
[Layer 3: Hungarian Tracking]
    - Tracks bullets across frames
    - Assigns unique IDs to each bullet
    - Prevents duplicate detections
        ↓
[Score Calculation]
    - Computes (x_mm, y_mm) coordinates from circle center
    - Calculates ring score (10-point scale)
    - Generates bullet metadata (confidence, frame_id, etc.)
        ↓
Output: Bullet Event
{
    "bullet_id": 1,
    "x_mm": -15.3,
    "y_mm": 8.7,
    "score": 8,
    "ring": "8",
    "timestamp": "2026-05-06T10:30:45Z",
    "metadata": {
        "frame_id": 1024,
        "confidence": 0.98,
        "radius_mm": 67.2
    }
}
```

**Key Functions**:
- [layer1.py](cv/DetectBullets/layer1.py) — Background subtraction & candidate detection
- [layer2.py](cv/DetectBullets/layer2.py) — Circle detection & fitting
- [layer3.py](cv/DetectBullets/layer3.py) — Hungarian algorithm tracking
- [scoring.py](cv/DetectBullets/scoring.py) — Score & ring calculation
- [worker.py](cv/DetectBullets/worker.py) — Multi-threaded processing

---

#### **Phase 2: Backend Processing & Storage**

```
CV Module sends POST /shot
{
    "x_mm": -15.3,
    "y_mm": 8.7,
    "timestamp": "2026-05-06T10:30:45Z",
    "session_id": "session_abc123",
    "metadata": { ... }
}
        ↓
[Shots Router - POST /shot]
        ↓
[Shot Service - register_shot()]
    ├─ Validate coordinates (finite numbers)
    ├─ Score calculation
    │   └─ Compute radius = sqrt(x² + y²)
    │   └─ Find ring from RING_TABLE (10 rings + miss)
    │   └─ Return (score, ring_label, radius_mm)
    │
    ├─ Duplicate Detection
    │   └─ If shot within 2mm of previous shot
    │   └─ AND arrived within 500ms → REJECT
    │   └─ Prevents sensor noise artifacts
    │
    └─ Persistence
        └─ Store in Firebase Firestore (or in-memory)
        └─ Generate unique shot ID (UUID)
        └─ Return ShotResponse with full metadata
                ↓
[WebSocket Broadcast]
    - Shot service triggers ws_manager.broadcast()
    - Message sent to ALL connected clients simultaneously
    - Format: Full ShotResponse as JSON
                ↓
Storage: Firestore Database
{
    "shot_id": "uuid-xxxx-xxxx",
    "x_mm": -15.3,
    "y_mm": 8.7,
    "score": 8,
    "ring": "8",
    "radius_mm": 67.2,
    "timestamp": "2026-05-06T10:30:45Z",
    "session_id": "session_abc123",
    "created_at": "2026-05-06T10:30:45Z"
}
```

**Ring Scoring Table** (via [shot_service.py](backend/services/shot_service.py)):
```
Radius (mm) | Score | Ring Label
─────────────────────────────────
≤  11.25    |  10   | X
≤  22.5     |  10   | 10
≤  45.0     |   9   | 9
≤  67.5     |   8   | 8
≤  90.0     |   7   | 7
≤ 112.5     |   6   | 6
≤ 135.0     |   5   | 5
≤ 157.5     |   4   | 4
≤ 180.0     |   3   | 3
≤ 202.5     |   2   | 2
≤ 225.0     |   1   | 1
>  225.0    |   0   | M (Miss)
```

**Key Functions**:
- [main.py](backend/main.py) — FastAPI app factory, middleware, WebSocket integration
- [shots.py](backend/routers/shots.py) — REST endpoints (POST /shot, GET /latest, GET /history, DELETE /shots)
- [shot_service.py](backend/services/shot_service.py) — Core business logic (scoring, deduplication, persistence)
- [firebase.py](backend/db/firebase.py) — Database abstraction layer
- [websocket.py](backend/routers/websocket.py) — WebSocket manager & broadcast

---

#### **Phase 3: Web Dashboard Reception & Display**

```
Web Client connects via WebSocket: /ws/shots
        ↓
[WebSocket Connection Manager]
    - Client added to ConnectionManager._connections list
    - Server sends {"type": "connected", "clients": N}
        ↓
[Real-time Shot Stream]
    - For each new shot from backend:
    - Server broadcasts ShotResponse to all connected clients
    - Client receives JSON message
    - Parsed by ws.onmessage handler
        ↓
[React State Update]
    - New shot added to shots array
    - Statistics recalculated
    - UI components re-render
        ↓
Dashboard Display Updates:
    ├─ Live Shot List
    │   └─ Latest shots scrolling list with score & ring
    ├─ Target Visualization
    │   └─ Real-time plot of shot positions on target
    ├─ Heatmap
    │   └─ Hit density distribution (N×N grid)
    ├─ Statistics Panel
    │   ├─ CEP (Circular Error Probable)
    │   ├─ R50 (Radius containing 50% of shots)
    │   ├─ Group (extreme spread)
    │   ├─ Mean POI (centroid)
    │   ├─ Total shots & aggregate score
    │   └─ Ring distribution
    └─ Export Options
        ├─ CSV download
        ├─ PDF report generation
        └─ Session management

[Heartbeat Mechanism]
    - If no messages for 20 seconds
    - Server sends {"type": "ping", "ts": "..."}
    - Keeps connection alive (prevents timeout)
```

**WebSocket Message Types**:
```javascript
// Control message (connection established)
{ "type": "connected", "clients": 3 }

// Control message (heartbeat)
{ "type": "ping", "ts": "2026-05-06T10:30:45Z" }

// Shot data (actual scoring event)
{
    "shot_id": "uuid-xxxx",
    "x_mm": -15.3,
    "y_mm": 8.7,
    "score": 8,
    "ring": "8",
    "radius_mm": 67.2,
    "timestamp": "2026-05-06T10:30:45Z",
    "session_id": "session_abc123"
    // ... more fields
}
```

**Key Files**:
- [client.js](web/src/api/client.js) — Axios HTTP client + WebSocket factory
- [App.jsx](web/src/App.jsx) — Main React component & WebSocket lifecycle
- API hooks — State management for shots, stats, heatmap

---

#### **Phase 4: ESP32 Display Integration (In Progress)**

Current Status: **UI layout complete, networking planned**

**Architecture**:
```
ESP32-S3 Device
    ├─ WiFi Module (to be connected)
    │   └─ Configured via IDF menuconfig
    │       ├─ WiFi SSID & password
    │       ├─ Backend API URL
    │       └─ WebSocket endpoint
    │
    ├─ HTTP Client (to be implemented)
    │   └─ POST requests to backend
    │   └─ Optional: Pull initial state
    │
    ├─ WebSocket Client (to be implemented)
    │   └─ Long-lived connection to /ws/shots
    │   └─ Receive real-time shot events
    │   └─ Parse JSON shot data
    │
    └─ LVGL UI (currently implemented)
        ├─ SPI LCD Display (170×320, SH8601 controller)
        ├─ Header: Total shots + Total score (fixed)
        ├─ Shot List: Scrollable list of recent shots
        ├─ Button Events:
        │   ├─ Single click → Test add shot (score 1)
        │   ├─ Double click → Test add shot (score 3)
        │   └─ Long press → Reset session
        └─ Update Callbacks
            └─ When shot received from backend
                ├─ Add shot entry to list
                ├─ Update total score
                ├─ Update total shots counter
                └─ Auto-scroll to latest

Data Flow to ESP32:
    Backend shot event → WebSocket broadcast
                ↓
    ESP32 WebSocket client receives message
                ↓
    Parse JSON shot data
                ↓
    Update LVGL UI (thread-safe with mutex)
                ↓
    LCD displays updated statistics
```

**Implementation Plan** (Next Steps):
1. Initialize WiFi in `app_main()`
2. Create HTTP client helper functions
3. Implement WebSocket client task (FreeRTOS task)
4. Add message handler to parse shot events
5. Integrate with LVGL UI update callbacks (protected by mutex)
6. Add configuration menu for WiFi credentials

**Key Files**:
- [main.c](esp/main/main.c) — Main application, LVGL UI, button handling
- [CMakeLists.txt](esp/CMakeLists.txt) — Build configuration
- [idf_component.yml](esp/main/idf_component.yml) — Dependency management

---

## Component Details

### Backend Models & Data Structures

#### **ShotCreate** (Request from CV)
```python
class ShotCreate(BaseModel):
    x_mm: float              # X offset from center (mm)
    y_mm: float              # Y offset from center (mm)
    timestamp: datetime      # UTC timestamp (auto-generated if None)
    session_id: str | None   # Optional session grouping
    metadata: dict | None    # CV pipeline metadata (frame_id, confidence, etc.)
```

#### **ShotResponse** (API response)
```python
class ShotResponse(BaseModel):
    shot_id: str             # UUID
    x_mm: float              # X coordinate
    y_mm: float              # Y coordinate
    score: int               # Ring score (0-10)
    ring: str                # Ring label ("X", "10", "9", ... "1", "M")
    radius_mm: float         # Distance from center
    timestamp: datetime      # When shot occurred
    session_id: str | None   # Session ID
    created_at: datetime     # Server-side creation timestamp
```

#### **ShotHistoryResponse** (Paginated history)
```python
class ShotHistoryResponse(BaseModel):
    shots: list[ShotResponse]
    total: int               # Total shots in session
    offset: int              # Pagination offset
    limit: int               # Pagination limit
```

### Backend API Endpoints

| Method | Endpoint         | Purpose                                    |
|--------|------------------|--------------------------------------------|
| POST   | `/shot`          | Register new shot from CV pipeline         |
| GET    | `/latest`        | Get most recent shot                       |
| GET    | `/history`       | Get paginated shot history (with filters)  |
| GET    | `/stats`         | Get aggregated statistics (CEP, R50, etc.) |
| GET    | `/heatmap`       | Get hit density grid (for visualization)   |
| DELETE | `/shots`         | Delete all shots (reset session)           |
| GET    | `/export/csv`    | Export shots as CSV file                   |
| GET    | `/export/pdf`    | Export PDF report                          |
| WS     | `/ws/shots`      | WebSocket: real-time shot feed             |

### Scoring Service Features

**1. Ring Scoring**
- 11 distinct scoring rings (X, 10, 9, 8, 7, 6, 5, 4, 3, 2, 1) + Miss
- Based on Euclidean distance from center
- Follows IPSC/standard 10-ring geometry

**2. Duplicate Detection** (via [DuplicateGuard](backend/services/shot_service.py))
- **Spatial threshold**: 2.0 mm minimum distance
- **Temporal threshold**: 500 ms time window
- **Purpose**: Prevents sensor noise from being counted as multiple shots
- **Note**: For multi-process deployments, move state to Redis

**3. Statistics Calculation** (via [analytics_service.py](backend/services/analytics_service.py))
- **CEP** (Circular Error Probable): Radius containing 50% of shots
- **R50**: Alternative CEP calculation method
- **Group** (Extreme Spread): Maximum distance between any two shots
- **Mean POI**: Centroid of all shot positions
- **Ring Distribution**: Count of hits per ring
- **Grouping**: Standard deviation of cluster radius

### Database Layer

**Firebase Integration** (via [firebase.py](backend/db/firebase.py)):
```python
class FirebaseStore:
    async def save_shot(shot: ShotRecord) -> ShotRecord
    async def get_latest_shot() -> ShotRecord | None
    async def get_history(limit, offset, session_id) -> (list, total)
    async def get_stats(session_id) -> dict
    async def delete_all_shots() -> int (deleted count)
```

**Fallback In-Memory Store**:
- Used when `use_firebase=False`
- Data persists during session
- Resets on server restart

---

## Communication Protocols

### 1. CV → Backend (HTTP POST)

**Request**:
```bash
POST http://localhost:8000/shot
Content-Type: application/json

{
    "x_mm": -15.3,
    "y_mm": 8.7,
    "timestamp": "2026-05-06T10:30:45Z",
    "session_id": "session_abc123",
    "metadata": {
        "frame_id": 1024,
        "confidence": 0.98
    }
}
```

**Response** (201 Created):
```json
{
    "shot_id": "550e8400-e29b-41d4-a716-446655440000",
    "x_mm": -15.3,
    "y_mm": 8.7,
    "score": 8,
    "ring": "8",
    "radius_mm": 67.2,
    "timestamp": "2026-05-06T10:30:45Z",
    "session_id": "session_abc123",
    "created_at": "2026-05-06T10:30:45Z"
}
```

### 2. Backend → Web Dashboard (WebSocket)

**Connection**:
```javascript
const ws = new WebSocket('ws://localhost:8000/ws/shots');
```

**Events**:
```javascript
// On connection
{ "type": "connected", "clients": 3 }

// On new shot (broadcast to all clients)
{
    "shot_id": "550e8400-e29b-41d4-a716-446655440000",
    "x_mm": -15.3,
    "y_mm": 8.7,
    "score": 8,
    "ring": "8",
    "radius_mm": 67.2,
    "timestamp": "2026-05-06T10:30:45Z",
    "session_id": "session_abc123",
    "created_at": "2026-05-06T10:30:45Z"
}

// Heartbeat (every 20 seconds if idle)
{ "type": "ping", "ts": "2026-05-06T10:30:45Z" }
```

### 3. Backend → ESP32 (WebSocket - Planned)

**Same as web dashboard**:
```
ESP32 connects to /ws/shots
Receives same ShotResponse messages
Updates local LVGL UI
```

**Implementation Strategy**:
- Use `esp_http_client` library for HTTP communication
- Use `esp_websocket_client` library for WebSocket
- Create FreeRTOS task for network communication
- Thread-safe UI updates using LVGL mutex

---

## Key Design Patterns

### 1. **Async Processing Pipeline**

The backend uses **async/await** for non-blocking I/O:

```python
async def register_shot(payload: ShotCreate) -> ShotResponse:
    # Validate & score (CPU-bound, but small)
    score, ring, radius = compute_score(payload.x_mm, payload.y_mm)
    
    # Check duplicates
    if _guard.is_duplicate(payload):
        raise ValueError("Duplicate shot detected")
    
    # Persist to database (I/O-bound, non-blocking)
    record = await get_store().save_shot(...)
    
    # Broadcast to WebSocket clients (fire-and-forget async)
    if ws_manager.client_count > 0:
        asyncio.create_task(ws_manager.broadcast(result.model_dump()))
    
    return ShotResponse.from_record(record)
```

**Benefits**:
- Single-threaded event loop handles many concurrent connections
- No blocking on database I/O
- Efficient resource utilization
- Built-in scalability

### 2. **Dependency Injection & Monkey-Patching**

Backend integrates WebSocket broadcasting without circular imports:

```python
# In main.py
_original_register = _ss.register_shot

async def _register_and_broadcast(payload) -> ShotResponse:
    result = await _original_register(payload)
    if ws_manager.client_count > 0:
        asyncio.create_task(ws_manager.broadcast(result.model_dump(mode="json")))
    return result

_ss.register_shot = _register_and_broadcast  # monkey-patch
```

**Why**: Avoids circular import between `shot_service` and `websocket` modules

### 3. **Multi-threaded CV Processing**

Computer Vision uses **thread pool** for parallel target processing:

```python
target_sets = {"BIA_TRON": [...], "BIA_IPSC": [...], "BIA_NGUOI": [...]}
input_queues = {name: queue.Queue(maxsize=2) for name in target_sets}
output_queue = queue.Queue(maxsize=10)

# Spawn 3 worker threads (one per target)
for name in target_sets.keys():
    t = threading.Thread(
        target=target_worker_thread, 
        args=(name, app_tracked_state[name], app_bg_state, input_queues[name], output_queue)
    )
    t.daemon = True
    t.start()
```

**Benefits**:
- Processes multiple targets in parallel
- Main thread handles video I/O at 30 FPS
- Workers handle expensive layer1/2/3 processing
- Queue-based communication (thread-safe)

### 4. **Event-Driven Architecture**

System components communicate via events:
- **CV Module** → Backend: HTTP POST (shot event)
- **Backend** → Web Dashboard: WebSocket (broadcast)
- **Backend** → ESP32: WebSocket (broadcast)
- **Dashboard** → Backend: HTTP GET (history, stats)

Each component is loosely coupled and can operate independently.

### 5. **Deduplication & Validation**

Multiple layers protect data integrity:
1. **CV Module** (layer3): Hungarian tracking prevents duplicate IDs
2. **Backend** (DuplicateGuard): Spatial + temporal filtering
3. **Database**: Unique shot_id (UUID)
4. **API**: Pydantic validation of all inputs

---

## Configuration & Deployment

### Backend Configuration (via environment variables)

See [config.py](backend/config.py):

```python
# Server
APP_NAME = "Shooting Scoring System"
APP_VERSION = "1.0.0"
DEBUG = False
HOST = "0.0.0.0"
PORT = 8000

# Firebase
FIREBASE_CREDS_PATH = "backend/serviceAccountKey.json"
FIREBASE_DB_URL = "https://your-project.firebaseio.com"
USE_FIREBASE = True  # False to use in-memory store

# Target geometry
TARGET_RADIUS_MM = 225.0
RINGS_MM = [11.25, 22.5, 45.0, 67.5, 90.0, ...]

# Duplicate detection
DUPLICATE_MIN_MM = 2.0
DUPLICATE_MAX_MS = 500

# CORS
CORS_ORIGINS = ["http://localhost:3000", "http://localhost:5173"]
```

### ESP32 Configuration

Via `idf.py menuconfig`:
```
Project Config
├─ WiFi SSID
├─ WiFi Password
├─ Backend API URL
├─ WebSocket URL
└─ Display settings
```

---

## System Metrics & Performance

### Throughput
- **CV Module**: 30 FPS (depends on video source)
- **Backend**: ~1000 shots/sec (single instance, async)
- **WebSocket**: Broadcasts to all clients in <10ms

### Latency
- **CV → Detection**: ~100-150ms (per frame, 30 FPS)
- **Detection → Backend**: ~5-10ms (network)
- **Backend → Dashboard**: <10ms (WebSocket broadcast)
- **Total End-to-End**: ~120-170ms

### Storage
- **Per shot**: ~500 bytes (JSON record)
- **100 shots**: ~50 KB
- **10,000 shots**: ~5 MB

---

## Testing & Validation

### Load Sample Data
```bash
# Create a test shot
curl -X POST http://localhost:8000/shot \
  -H "Content-Type: application/json" \
  -d '{
    "x_mm": -15.3,
    "y_mm": 8.7,
    "session_id": "test"
  }'

# Retrieve history
curl http://localhost:8000/history

# Export as CSV
curl http://localhost:8000/export/csv > shots.csv
```

### Unit Tests
```bash
# Backend tests
cd backend && pytest tests/ -v

# CV module tests
cd cv && pytest tests/ -v
```

---

## Future Enhancements

1. **Multi-instance deployment** (horizontal scaling)
   - Move DuplicateGuard to Redis
   - Distribute WebSocket connections across instances
   - Load balance with Nginx

2. **Advanced analytics**
   - Grouping trend analysis
   - Ballistic correction models
   - Machine learning-based anomaly detection

3. **Extended ESP32 features**
   - WiFi configuration UI
   - Network diagnostics
   - OTA firmware updates
   - Battery monitoring

4. **Real-time video streaming**
   - RTMP/RTSP from CV module to dashboard
   - Live annotated target visualization

5. **Multi-user sessions**
   - User authentication
   - Session management & permissions
   - Shooter profiles & historical analysis

---

## Quick Reference: Function Map

### Computer Vision (`cv/DetectBullets/`)
| File | Purpose |
|------|---------|
| `main.py` | Entry point, camera capture, ArUco detection |
| `worker.py` | Multi-threaded target processing |
| `layer1.py` | Background subtraction, candidate detection |
| `layer2.py` | Circle detection (RANSAC/Hough) |
| `layer3.py` | Hungarian tracking, ID assignment |
| `scoring.py` | Score calculation from coordinates |
| `state.py` | Worker state management |
| `config.py` | CV pipeline parameters |

### Backend (`backend/`)
| File | Key Functions |
|------|---------------|
| `main.py` | App factory, middleware, WebSocket integration |
| `routers/shots.py` | REST endpoints (POST/GET/DELETE /shot, /history, /export) |
| `routers/websocket.py` | WebSocket manager, broadcast |
| `services/shot_service.py` | `register_shot()`, `get_history()`, scoring logic |
| `services/analytics_service.py` | CEP, R50, grouping, stats |
| `services/export_service.py` | CSV/PDF generation |
| `db/firebase.py` | Database abstraction (Firebase or in-memory) |
| `models/shot.py` | Pydantic models (ShotCreate, ShotResponse, etc.) |
| `config.py` | Settings from environment variables |

### Web Dashboard (`web/src/`)
| File | Purpose |
|------|---------|
| `api/client.js` | HTTP client (Axios) + WebSocket factory |
| `App.jsx` | Main component, WebSocket lifecycle |
| `pages/` | Dashboard pages (shots, stats, heatmap, etc.) |
| `components/` | Reusable React components |
| `hooks/` | Custom React hooks (useState, useEffect patterns) |
| `utils/` | Helper functions |

### ESP32 (`esp/`)
| File | Purpose |
|------|---------|
| `main/main.c` | App main, LVGL UI, button handling |
| `main/CMakeLists.txt` | Build config, component linking |
| `main/idf_component.yml` | Dependency versions |
| `components/button_bsp/` | Button driver |
| `components/esp_lcd_sh8601/` | SH8601 LCD driver |

---

## Debugging & Monitoring

### Backend Logs
```bash
# Watch backend logs
tail -f backend.log

# Enable verbose logging
export LOG_LEVEL=DEBUG
uvicorn backend.main:app --log-level debug
```

### WebSocket Debugging (Browser DevTools)
```javascript
// In browser console
ws.addEventListener('message', (e) => console.log('WS:', e.data));
```

### CV Module Visualization
```bash
# Run with OpenCV windows showing detection layers
python cv/DetectBullets/main.py --debug
```

---

## License & Attribution

See [Readme.md](Readme.md) for license information and quick start guides.
