from unittest.mock import patch, MagicMock

def test_transcribe_returns_segments():
    mock_segment = MagicMock()
    mock_segment.start = 0.0
    mock_segment.end = 2.5
    mock_segment.text = "안녕하세요"
    mock_segment.avg_logprob = -0.3

    mock_model = MagicMock()
    mock_model.transcribe.return_value = ([mock_segment], MagicMock(language="ko"))

    with patch("workers.whisper_worker.WhisperModel", return_value=mock_model):
        from workers.whisper_worker import transcribe
        result = transcribe("/tmp/test.wav")

    assert len(result) == 1
    assert result[0]["text"] == "안녕하세요"
    assert result[0]["start"] == 0.0
    assert result[0]["end"] == 2.5

def test_diarize_returns_speaker_segments():
    mock_pipeline = MagicMock()
    mock_turn = MagicMock()
    mock_turn.start = 0.0
    mock_turn.end = 3.0
    mock_diarization = mock_pipeline.return_value.return_value
    mock_diarization.itertracks.return_value = [(mock_turn, None, "SPEAKER_00")]

    with patch("workers.diarize_worker.Pipeline.from_pretrained", return_value=mock_pipeline()):
        from workers.diarize_worker import diarize
        result = diarize("/tmp/test.wav")

    assert len(result) == 1
    assert result[0]["speaker"] == "A"
    assert result[0]["start"] == 0.0
