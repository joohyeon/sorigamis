from __future__ import annotations


def compute_quality(segments: list[dict]) -> dict:
    probs = [s["avg_logprob"] for s in segments if "avg_logprob" in s]
    avg = round(sum(probs) / len(probs), 4) if probs else 0.0
    score = "good" if avg >= -0.5 else ("fair" if avg >= -0.8 else "poor")
    low = sorted(
        [s for s in segments if s.get("avg_logprob", 0.0) < -1.0],
        key=lambda s: s.get("avg_logprob", 0.0),
    )[:10]
    duration = max((s.get("end", 0.0) for s in segments), default=0.0)
    return {
        "transcript_score": score,
        "avg_logprob": avg,
        "low_confidence_count": sum(1 for s in segments if s.get("avg_logprob", 0.0) < -1.0),
        "low_confidence_segments": [
            {
                "start_sec": s.get("start", 0.0),
                "end_sec": s.get("end", 0.0),
                "text": s.get("text", ""),
                "avg_logprob": s.get("avg_logprob", 0.0),
            }
            for s in low
        ],
        "diarization_degraded": False,
        "segment_count": len(segments),
        "duration_sec": round(duration, 3),
    }


def with_diarization_degraded(quality: dict, degraded: bool) -> dict:
    return {**quality, "diarization_degraded": degraded}
