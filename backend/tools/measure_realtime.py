from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import time
from datetime import datetime, timezone

import httpx
import websockets


def _percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = min(len(ordered) - 1, max(0, int(round((len(ordered) - 1) * p))))
    return ordered[idx]


async def main() -> None:
    parser = argparse.ArgumentParser(description="Measure POST /shot + WebSocket realtime latency.")
    parser.add_argument("--api-url", default="http://127.0.0.1:8000", help="Backend base URL")
    parser.add_argument("--ws-url", default="ws://127.0.0.1:8000/ws/shots", help="WebSocket feed URL")
    parser.add_argument("--count", type=int, default=20, help="Number of synthetic shots to send")
    parser.add_argument("--interval-ms", type=int, default=250, help="Delay between shots")
    parser.add_argument("--session-id", default="latency-benchmark", help="Session ID for generated shots")
    args = parser.parse_args()

    post_rtts: list[float] = []
    backend_ms: list[float] = []
    ws_delivery_ms: list[float] = []
    end_to_end_ms: list[float] = []
    persisted_ms: list[float] = []
    pending_by_id: dict[str, dict] = {}
    pending_by_seq: dict[int, dict] = {}

    async with httpx.AsyncClient(base_url=args.api_url, timeout=10.0) as client:
        async with websockets.connect(args.ws_url) as ws:
            first = json.loads(await ws.recv())
            print(f"Connected to WebSocket: {first}")

            async def receiver() -> None:
                while len(end_to_end_ms) < args.count:
                    raw = await ws.recv()
                    data = json.loads(raw)
                    if data.get("type") in {"connected", "ping"}:
                        continue

                    shot_id = data.get("id")
                    received_at_ms = int(time.time() * 1000)
                    eval_meta = ((data.get("metadata") or {}).get("eval") or {})
                    sequence = eval_meta.get("sequence")
                    state = pending_by_id.get(shot_id)
                    if state is None and sequence is not None:
                        state = pending_by_seq.get(int(sequence))
                    if state is None:
                        continue

                    broadcast_at = eval_meta.get("backend_broadcast_at_ms")
                    persisted_at = eval_meta.get("backend_persisted_at_ms")
                    client_sent_at = eval_meta.get("client_sent_at_ms")

                    if broadcast_at is not None:
                        ws_delivery_ms.append(received_at_ms - float(broadcast_at))
                    if persisted_at is not None and client_sent_at is not None:
                        persisted_ms.append(float(persisted_at) - float(client_sent_at))
                    if client_sent_at is not None:
                        end_to_end_ms.append(received_at_ms - float(client_sent_at))

                    state["ws_received"] = True

            recv_task = asyncio.create_task(receiver())

            for idx in range(args.count):
                client_sent_at_ms = int(time.time() * 1000)
                pending_by_seq[idx] = {
                    "sequence": idx,
                    "client_sent_at_ms": client_sent_at_ms,
                    "ws_received": False,
                }
                payload = {
                    "x_px": float(1240 + (idx % 10) * 5),
                    "y_px": float(1754 + (idx % 5) * -3),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "shotID": idx,
                    "scores": 10,
                    "session_id": args.session_id,
                    "metadata": {
                        "source": "latency_probe",
                        "target_type": "TRON",
                        "eval": {
                            "client_sent_at_ms": client_sent_at_ms,
                            "sequence": idx,
                        },
                    },
                }

                started = time.perf_counter()
                response = await client.post("/shot", json=payload)
                post_rtt = (time.perf_counter() - started) * 1000.0
                response.raise_for_status()

                body = response.json()
                shot_id = body["id"]
                state = pending_by_seq[idx]
                state.update(body)
                pending_by_id[shot_id] = state
                post_rtts.append(post_rtt)

                header_ms = response.headers.get("X-Process-Time-Ms")
                if header_ms is not None:
                    backend_ms.append(float(header_ms))

                await asyncio.sleep(args.interval_ms / 1000.0)

            try:
                await asyncio.wait_for(recv_task, timeout=max(10.0, args.count * args.interval_ms / 1000.0 + 5.0))
            except asyncio.TimeoutError:
                recv_task.cancel()
                received = sum(1 for item in pending_by_seq.values() if item.get("ws_received"))
                print(f"Warning: timed out waiting for all WS events. Received {received}/{args.count}.")

    def print_metric(name: str, values: list[float]) -> None:
        print(f"\n{name}")
        print(f"  count : {len(values)}")
        if not values:
            return
        print(f"  mean  : {statistics.mean(values):.2f} ms")
        print(f"  p50   : {statistics.median(values):.2f} ms")
        print(f"  p95   : {_percentile(values, 0.95):.2f} ms")
        print(f"  min   : {min(values):.2f} ms")
        print(f"  max   : {max(values):.2f} ms")

    print_metric("POST /shot round-trip", post_rtts)
    print_metric("Backend processing (header)", backend_ms)
    print_metric("Client->persisted", persisted_ms)
    print_metric("WebSocket delivery", ws_delivery_ms)
    print_metric("End-to-end (client send -> WS receive)", end_to_end_ms)


if __name__ == "__main__":
    asyncio.run(main())
