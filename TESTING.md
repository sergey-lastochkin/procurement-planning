# Testing

After the README test install, run `.venv/bin/python -m pytest -q`. The deterministic suite covers available/projected/shortage arithmetic; incoming and reservations; MOQ, pack and minimum value; freshness; future observations; stock and lead limits; locked and preferred semantics; reliability scoring; currency rejection; invalid values; ties; evidence; approval; rejection; idempotent draft creation; stable IDs; and the 500-SKU generator.
