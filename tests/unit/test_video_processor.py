import io
from unittest.mock import AsyncMock, patch
import pytest

from app.core.exceptions import BusinessRuleException
from app.core.storage.video_processor import (
    VideoMetadata,
    calcular_dimensiones_objetivo,
    normalize_video_if_needed,
    parse_frame_rate,
    validate_video_magic_bytes,
)


def test_calcular_dimensiones_objetivo_respeta_orientacion():
    assert calcular_dimensiones_objetivo(1280, 720) == (1280, 720)
    assert calcular_dimensiones_objetivo(720, 1280) == (720, 1280)
    assert calcular_dimensiones_objetivo(3840, 2160) == (1280, 720)
    assert calcular_dimensiones_objetivo(1080, 1920) == (720, 1280)
    assert calcular_dimensiones_objetivo(640, 480) == (640, 480)


def test_parse_frame_rate():
    assert pytest.approx(parse_frame_rate("30000/1001"), 0.01) == 29.97
    assert parse_frame_rate("60/1") == 60.0
    assert parse_frame_rate("0/0") is None
    assert parse_frame_rate(None) is None
    assert parse_frame_rate("invalid") is None


def test_validate_video_magic_bytes():
    valid_mp4 = b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom" + b"\x00" * 32
    valid_webm = b"\x1a\x45\xdf\xa3" + b"\x00" * 32

    validate_video_magic_bytes(valid_mp4, ".mp4")
    validate_video_magic_bytes(valid_webm, ".webm")

    with pytest.raises(BusinessRuleException, match="corrupto"):
        validate_video_magic_bytes(b"not_a_video_content_at_all", ".mp4")

    with pytest.raises(BusinessRuleException, match="corrupto"):
        validate_video_magic_bytes(b"not_a_webm_file", ".webm")


@pytest.mark.asyncio
async def test_normalize_video_acepta_video_largo_y_60fps_en_720p():
    valid_mp4 = b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom" + b"\x00" * 32
    meta = VideoMetadata(width=1280, height=720, fps=60.0, duration=180.0, codec_name="h264")

    with (
        patch("app.core.storage.video_processor.shutil.which", return_value="/usr/bin/ffprobe"),
        patch("app.core.storage.video_processor.probe_video_metadata", AsyncMock(return_value=meta)),
    ):
        out_bytes, out_ext, out_mime = await normalize_video_if_needed(valid_mp4, ".mp4", "video/mp4")

    assert out_bytes == valid_mp4
    assert out_ext == ".mp4"
    assert out_mime == "video/mp4"


@pytest.mark.asyncio
async def test_normalize_video_transcodifica_si_supera_720p():
    valid_mp4 = b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom" + b"\x00" * 32
    meta = VideoMetadata(width=1920, height=1080, fps=60.0, duration=120.0, codec_name="h264")

    async def fake_transcode(_bin, _in_path, out_path, target_w, target_h, duration=None):
        assert (target_w, target_h) == (1280, 720)
        assert duration == 120.0
        with open(out_path, "wb") as fh:
            fh.write(valid_mp4)

    with (
        patch("app.core.storage.video_processor.shutil.which", return_value="/usr/bin/ffmpeg"),
        patch("app.core.storage.video_processor.probe_video_metadata", AsyncMock(return_value=meta)),
        patch("app.core.storage.video_processor._transcode_video", side_effect=fake_transcode) as mock_trans,
    ):
        out_bytes, out_ext, out_mime = await normalize_video_if_needed(valid_mp4, ".mov", "video/quicktime")

    mock_trans.assert_called_once()
    assert out_ext == ".mp4"
    assert out_mime == "video/mp4"
    assert out_bytes == valid_mp4
