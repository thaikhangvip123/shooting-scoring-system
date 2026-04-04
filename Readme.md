# 🎯 Shooting Scoring System

A real-time automated shooting scoring system for 3D simulation environments.

## Architecture

```
3D Simulation Engine
       │  frames / RTSP
       ▼
Computer Vision (Python + OpenCV)   ← ArUco detection, homography, blob detection
       │  shot event (x_mm, y_mm)
       ▼
Backend API (FastAPI)               ← REST + WebSocket + Firebase
       ├─► Web Dashboard (React)    ← Target, heatmap, stats, export
       ├─► ESP32-S3 Client (LVGL)   ← LCD display
       └─► Reports (CSV / PDF)
```

## Quick Start

### 1. Backend

```bash
cd backend
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# Add Firebase credentials
cp serviceAccountKey.json.example serviceAccountKey.json
# → fill in your Firebase project credentials

uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

### 2. Web Dashboard

```bash
cd web
npm install
npm run dev          # → http://localhost:3000
```

### 3. Computer Vision

```bash
cd cv
pip install -r requirements.txt

# Run calibration first (point camera at ArUco board)
python calibration.py --output calibration.json

# Start live detection
python main.py --source 0               # webcam
python main.py --source rtsp://...      # RTSP stream
python main.py --source video.mp4       # video file
```

### 4. ESP32

```bash
cd esp32
idf.py set-target esp32s3
idf.py menuconfig              # set WiFi SSID/password + API URL
idf.py build flash monitor
```

## Environment Variables

| Variable         | Default                  | Description              |
|------------------|--------------------------|--------------------------|
| `VITE_API_URL`   | `/api` (proxied)         | Backend base URL         |
| `VITE_WS_URL`    | `ws://{host}/ws`         | WebSocket base URL       |
| `FIREBASE_CREDS` | `serviceAccountKey.json` | Firebase credentials path|

## Target Specification

The scoring target follows standard 10-ring geometry:

| Ring | Score | Radius (mm) |
|------|-------|-------------|
| X    | 10    | 11.25       |
| 10   | 10    | 22.5        |
| 9    | 9     | 45.0        |
| 8    | 8     | 67.5        |
| 7    | 7     | 90.0        |
| ...  | ...   | ...         |
| 1    | 1     | 225.0       |

## API Reference

See [docs/API.md](docs/API.md) for full endpoint documentation.

## Metrics

| Metric     | Description                              |
|------------|------------------------------------------|
| **CEP**    | Circular Error Probable – radius containing 50% of shots |
| **R50**    | Radius from group centroid containing 50% of shots       |
| **Group**  | Extreme spread – max distance between any two shots      |
| **Mean POI**| Mean point of impact (centroid)                         |

## Testing

```bash
# CV module tests
cd cv && pytest tests/ -v

# Backend tests
cd backend && pytest tests/ -v

# Load sample data into running backend
curl -X POST http://localhost:8000/shot \
  -H "Content-Type: application/json" \
  -d @data/sample_shots.json[0]
```

## License

MIT