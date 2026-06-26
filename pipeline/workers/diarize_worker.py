"""Modal GPU worker: pyannote.audio speaker diarization."""
from __future__ import annotations

try:
    import modal
    _modal_available = True
except ImportError:  # not installed outside Modal container
    modal = None  # type: ignore[assignment]
    _modal_available = False

try:
    from pyannote.audio import Pipeline
except ImportError:  # only available inside Modal image
    class Pipeline:  # type: ignore[no-redef]
        """Stub so patch("workers.diarize_worker.Pipeline.from_pretrained") works in tests."""
        @classmethod
        def from_pretrained(cls, *args, **kwargs):
            raise ImportError("pyannote.audio not installed")

_SPEAKER_LABELS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"

if _modal_available:
    app = modal.App("sg-diarize")

    image = (
        modal.Image.from_registry("nvidia/cuda:12.4.1-cudnn-runtime-ubuntu22.04", add_python="3.12")
        .apt_install("ffmpeg", "libsndfile1")
        .pip_install(
            "torch==2.5.1", "torchaudio==2.5.1",
            "pyannote.audio==3.3.2", "speechbrain==1.0.2",
        )
    )

    models_volume = modal.Volume.from_name("sg-models", create_if_missing=True)
    secrets = [modal.Secret.from_name("sg-huggingface")]  # HF_TOKEN for pyannote

    @app.function(
        image=image,
        gpu="T4",
        volumes={"/models": models_volume},
        secrets=secrets,
        timeout=600,
    )
    def diarize(wav_path: str, num_speakers: int = 2) -> list[dict]:
        pipeline = Pipeline.from_pretrained(
            "pyannote/speaker-diarization-3.1",
            use_auth_token=True,
            cache_dir="/models/pyannote",
        )
        diarization = pipeline(wav_path, num_speakers=num_speakers)
        speaker_map: dict[str, str] = {}
        segments = []
        for turn, _, speaker in diarization.itertracks(yield_label=True):
            if speaker not in speaker_map:
                speaker_map[speaker] = _SPEAKER_LABELS[len(speaker_map)]
            segments.append({
                "start": round(turn.start, 3),
                "end": round(turn.end, 3),
                "speaker": speaker_map[speaker],
            })
        return segments

else:
    def diarize(wav_path: str, num_speakers: int = 2) -> list[dict]:  # type: ignore[misc]
        pipeline = Pipeline.from_pretrained(
            "pyannote/speaker-diarization-3.1",
            use_auth_token=True,
            cache_dir="/models/pyannote",
        )
        diarization = pipeline(wav_path, num_speakers=num_speakers)
        speaker_map: dict[str, str] = {}
        segments = []
        for turn, _, speaker in diarization.itertracks(yield_label=True):
            if speaker not in speaker_map:
                speaker_map[speaker] = _SPEAKER_LABELS[len(speaker_map)]
            segments.append({
                "start": round(turn.start, 3),
                "end": round(turn.end, 3),
                "speaker": speaker_map[speaker],
            })
        return segments
