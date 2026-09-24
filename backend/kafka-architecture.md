# FireLink — Kafka Architecture & Context Retrieval

Developer-facing reference for how Kafka is used within FireLink, the mechanics
of reading the latest N messages, and why this pattern matters for the
AI-agent context pipeline.

---

## Kafka core concepts

FireLink uses Kafka as an append-only, durable message log for streaming
real-time fire-incident and weather data. Three concepts are essential:

### Topic

A named, append-only stream of messages. FireLink defines three topics:

| Topic | Producer | Message shape |
|---|---|---|
| `firelink.fire` | `calfire-producer` | `{id, name, latitude, longitude, acres, containment, status, timestamp}` |
| `firelink.weather` | `noaa-producer` | `{id, event, severity, area, description, wind_mph, humidity_pct, onset, expires, timestamp}` |
| `firelink.recommendations` | `recommendation-agent` | `{advisory, reasoning, risk_level, generated_at}` |

Think of a topic as a continuously growing list: producers **append** messages
to the end, consumers **read** from any position.

### Partition

A topic is divided into 1+ partitions for parallelism and scalability. Each
partition is an independent, ordered log. Messages within a single partition
are strictly ordered by arrival; across partitions, ordering is not guaranteed.

FireLink runs a **single-partition** setup (the Kafka default with
`KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR: 1` in `docker-compose.yml`), so every
message lands in partition 0 in the exact order it was produced. This keeps the
replay timeline chronologically consistent — important for an incident feed
where time-ordering matters.

### Offset

Every message within a partition receives a monotonically increasing integer
ID called its **offset**, starting at 0. The first message is offset 0, the
second is offset 1, and so on.

The **end offset** (log-end offset) is the next offset that *would* be written
— effectively the total number of messages ever produced to that partition.
If 250 messages have been published, the end offset is `250` and valid
messages exist at offsets `0` through `249`.

```
Partition 0:  [msg][msg][msg][msg] ... [msg][msg][msg]
Offsets:       0    1    2    3   ...  247  248  249   ← end_offset = 250
```

Offsets are durable — they persist across broker restarts and allow consumers
to seek to any arbitrary position in the log without replaying from the
beginning.

---

## FireLink's data flow

```
JSON data files                     Containers                  Kafka topics
────────────────────                ──────────────────          ──────────────────────
fire_incidents.json  ──────►  calfire-producer    ──────►  firelink.fire
weather_alerts.json  ──────►  noaa-producer       ──────►  firelink.weather
                                                      │
                   recommendation-agent (every 60s) ──► firelink.recommendations
                                                      │
                                                      ▼
                                          context_service reads
                                          last 10 per topic
                                                      │
                                                      ▼
                                    /context/latest  +  Help Agent  +  MCP server
```

Producers replay 199 real CAL FIRE Eaton Fire updates and Open-Meteo weather
observations (one record every 10 seconds) into Kafka. Each message is also
upserted into SQLite for persistence, but the **live read path goes through
Kafka**, not the database.

---

## How the latest 10 messages are retrieved

The core logic lives in `app/services/context_service.py`, in the
`_read_latest()` function. This is called by both `get_latest_context()` (the
`/context/latest` endpoint) and the Help Agent pipeline.

### Step-by-step walkthrough

```python
# app/services/context_service.py:21
async def _read_latest(topic: str, n: int) -> list[dict]:
    consumer = AIOKafkaConsumer(
        topic,
        bootstrap_servers=KAFKA_BOOTSTRAP,
        auto_offset_reset="earliest",
        enable_auto_commit=False,
    )
    await consumer.start()
```

A fresh, stateless `AIOKafkaConsumer` is created for each call.
`enable_auto_commit=False` means the consumer never persists its read position
to Kafka — this is intentional, since we want an ad-hoc tail read, not a
continuous subscription.

```python
    partitions = [TopicPartition(topic, p) for p in consumer.partitions_for_topic(topic) or [0]]
```

**1. Discover partitions.** The consumer queries Kafka for the topic's
partition IDs. In our single-partition setup this returns `[0]`. The fallback
`or [0]` handles the case where the topic exists but no metadata is available
yet.

```python
    end_offsets = await consumer.end_offsets(partitions)
```

**2. Get end offsets.** `end_offsets()` returns a mapping of
`{TopicPartition → next_offset_to_be_written}` for each partition. If 250
messages have been produced to partition 0, this returns
`{TopicPartition(topic, 0): 250}`.

```python
    messages = []
    for tp in partitions:
        end = end_offsets[tp]
        if end == 0:
            continue
        start = max(0, end - n)
        consumer.seek(tp, start)
```

**3. Seek backward.** For the latest `n` messages (n=10 by default), the
start offset is calculated as `end - n`. If the end offset is 250, then
`start = 240`. `consumer.seek(tp, start)` moves the consumer's read cursor to
offset 240 — an O(1) operation regardless of how many total messages exist.

If the topic has fewer than `n` messages (e.g., only 3 produced so far),
`max(0, end - n)` clamps the start to 0 and all available messages are read.

```python
        for _ in range(end - start):
            try:
                msg = await asyncio.wait_for(consumer.getone(tp), timeout=2.0)
                messages.append(json.loads(msg.value))
            except asyncio.TimeoutError:
                logger.warning("Timeout reading from topic %s partition %d", topic, tp.partition)
                break
```

**4. Read forward.** The consumer reads exactly `end - start` messages in
order. `getone(tp)` blocks until a single message is available from that
specific partition. A 2-second per-message timeout guards against a stalled
broker — if any read times out, the loop breaks and returns whatever was
collected so far.

```python
    finally:
        await consumer.stop()
```

**5. Cleanup.** The consumer is closed in a `finally` block, releasing its
Kafka connection. Since no offsets were committed, this call leaves no
consumer-group state behind.

### Visual summary

```
Partition 0:  [msg][msg][msg][msg] ... [msg][msg][msg]
Offsets:       0    1    2    3   ...  247  248  249   ← end_offset = 250
                                           ↑
                                       seek to 240
                                       read 240 → 249 = last 10 messages
```

### The orchestrator

`get_latest_context()` (`context_service.py:55`) fans out two `_read_latest()`
calls in parallel with a 10-second overall timeout:

```python
weather, fire = await asyncio.wait_for(
    asyncio.gather(
        _read_latest(TOPICS["weather"], MESSAGES_PER_TOPIC),  # 10
        _read_latest(TOPICS["fire"], MESSAGES_PER_TOPIC),     # 10
    ),
    timeout=10.0,
)
```

The result is a snapshot dict:

```json
{
  "weather": [ ...last 10 weather alerts... ],
  "fire":    [ ...last 10 fire incidents... ],
  "fetched_at": "2025-01-08T05:46:00Z"
}
```

A similar single-message tail read (`get_latest_recommendation()`,
`context_service.py:74`) seeks to `end - 1` to grab just the most recent
advisory from `firelink.recommendations`.

---

## Why this matters

### 1. Live context for AI agents

The Help Agent (`app/services/agents/help_agent.py`) and the MCP server
(`app/mcp_server.py`) both call `get_latest_context()` before generating any
response. By always reading the tail of the Kafka log, the agent gets a
**fresh, time-ordered snapshot** of the 10 most recent fire incidents and
weather alerts — never stale data, never the full 199-message history.

This snapshot is serialized into the Claude prompt alongside RAG chunks, user
profile, shelter data, and the latest advisory, grounding the LLM's response
in current conditions.

### 2. O(1) tail read regardless of history size

Because Kafka offsets are sequential integers backed by an on-disk log,
seeking to `end - N` and reading forward is constant-time. Whether the topic
has 10 messages or 10 million, the latest-10 read takes the same number of
network round-trips. This is fundamentally different from querying a
relational database with `ORDER BY timestamp DESC LIMIT 10`, which requires an
index scan and sort.

### 3. Decoupled producer/consumer lifecycle

Producers (`calfire-producer`, `noaa-producer`) run as independent containers
that continuously append to Kafka. The context service creates ephemeral
consumers on demand — no long-lived consumer group, no offset persistence, no
rebalance overhead. This stateless read pattern is simple to reason about and
avoids the complexity of consumer-group coordination for a demo-scale system.

### 4. Idempotent replays

Producers replay from static JSON files on restart. Because the SQLite layer
upserts on `id` (via `db.merge()` in `base_producer.py`), and Kafka offsets
are deterministic, restarting the stack and replaying the same 199 records
produces identical state. The context read always returns the same tail
window for a given replay position.

---

## Configuration reference

| Setting | Value | Location |
|---|---|---|
| Bootstrap server (in-container) | `kafka:9092` | `docker-compose.yml`, `app/core/kafka.py` |
| Bootstrap server (host-side) | `localhost:9092` | `docker-compose.yml` port mapping |
| Messages read per topic | 10 | `MESSAGES_PER_TOPIC` in `context_service.py` |
| Overall context fetch timeout | 10s | `asyncio.wait_for` in `get_latest_context()` |
| Per-message read timeout | 2s | `asyncio.wait_for` in `_read_latest()` |
| Producer replay interval | 10s | `interval = 10` in producer classes |
| Recommendation agent interval | 60s | `INTERVAL = 60` in `recommendation_agent.py` |

---

## Observability

Use the Makefile targets to inspect the streams directly:

```bash
make topics                      # list all Kafka topics
make stream-fire                 # live tail: firelink.fire
make stream-weather              # live tail: firelink.weather
make stream-recommendations      # live tail: firelink.recommendations
make context                     # pretty-print GET /context/latest
make logs-calfire                # follow CAL FIRE producer logs
make logs-noaa                   # follow NOAA producer logs
```

Or inspect Kafka directly inside the broker container:

```bash
docker exec firelink-kafka kafka-topics --bootstrap-server localhost:9092 --list
docker exec firelink-kafka kafka-console-consumer --bootstrap-server localhost:9092 --topic firelink.fire --from-beginning
```

---

## Production considerations

The current stateless-consumer-per-request pattern is intentionally simple and
works well for a hackathon demo. For a production system, consider:

- **Materialized view / cache layer** — maintain a rolling window of the last
  N messages in Redis or an in-memory store updated by a long-lived consumer,
  avoiding a Kafka round-trip on every `/context/latest` call.
- **Consumer groups for streaming agents** — the recommendation agent could
  consume from a committed consumer group instead of re-tailing on each cycle,
  enabling exactly-once processing and horizontal scaling.
- **Multi-partition scaling** — if message volume grows, partition by
  geography (e.g., ZIP prefix) and adjust `_read_latest()` to aggregate across
  partitions by timestamp rather than relying on single-partition ordering.
