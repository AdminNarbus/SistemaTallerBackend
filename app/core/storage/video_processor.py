"""Validación y normalización de videos adjuntos (resolución máxima 720p)."""
import asyncio
import json
import logging
import os
import shutil
import tempfile
from dataclasses import dataclass
from typing import Final, Optional

from app.core.config import settings
from app.core.exceptions import BusinessRuleException

logger = logging.getLogger(__name__)

_ISOBMFF_EXTENSIONS: Final[set[str]] = {".mp4", ".mov", ".m4v", ".3gp"}
_WEB_FRIENDLY_VIDEO_CODECS: Final[set[str]] = {"h264", "vp8", "vp9"}
_DURATION_TOLERANCE_SECONDS: Final[float] = 1.0
_FPS_TOLERANCE: Final[float] = 0.5


@dataclass(frozen=True)
class VideoMetadata:
    width: int
    height: int
    fps: Optional[float]
    duration: Optional[float]
    codec_name: Optional[str]


def validate_video_magic_bytes(content: bytes, extension: str) -> None:
    """Verifica firmas mínimas de contenedor MP4/QuickTime/3GP o WebM."""
    ext = extension.lower()
    if ext in _ISOBMFF_EXTENSIONS:
        if len(content) < 12 or b"ftyp" not in content[:32]:
            raise BusinessRuleException(
                "El archivo de video está corrupto o no corresponde a un formato de video válido."
            )
        return
    if ext == ".webm":
        if not content.startswith(b"\x1a\x45\xdf\xa3"):
            raise BusinessRuleException(
                "El archivo WebM está corrupto o no corresponde a un formato de video válido."
            )
        return
    raise BusinessRuleException(f"Extensión de video no soportada: '{extension}'.")


def calcular_dimensiones_objetivo(
    width: int,
    height: int,
    max_long: int = 1280,
    max_short: int = 720,
) -> tuple[int, int]:
    """Escala dimensiones manteniendo orientación (horizontal o vertical) y múltiplos pares."""
    if width <= 0 or height <= 0:
        return width, height
    long_side = max(width, height)
    short_side = min(width, height)
    if long_side <= max_long and short_side <= max_short:
        return width, height

    scale = min(max_long / long_side, max_short / short_side)
    scaled_w = max(2, (int(width * scale) // 2) * 2)
    scaled_h = max(2, (int(height * scale) // 2) * 2)
    return scaled_w, scaled_h


def parse_frame_rate(raw_rate: Optional[str]) -> Optional[float]:
    """Convierte tasas de cuadros 'num/den' o decimales de ffprobe sin evaluar expresiones."""
    if not raw_rate or not isinstance(raw_rate, str):
        return None
    cleaned = raw_rate.strip()
    if not cleaned:
        return None
    if "/" in cleaned:
        parts = cleaned.split("/", 1)
        try:
            num = float(parts[0])
            den = float(parts[1])
        except ValueError:
            return None
        if den <= 0:
            return None
        rate = num / den
        return rate if rate > 0 else None
    try:
        rate = float(cleaned)
        return rate if rate > 0 else None
    except ValueError:
        return None


async def probe_video_metadata(file_path: str) -> Optional[VideoMetadata]:
    """Extrae metadatos del flujo de video principal usando ffprobe si está instalado."""
    ffprobe_bin = shutil.which("ffprobe")
    if not ffprobe_bin:
        return None

    proc = await asyncio.create_subprocess_exec(
        ffprobe_bin,
        "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=width,height,avg_frame_rate,r_frame_rate,codec_name:format=duration",
        "-of", "json",
        file_path,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=15.0)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        raise BusinessRuleException("No se pudo analizar el video en el tiempo esperado.")

    if proc.returncode != 0:
        logger.warning("[VIDEO_PROCESSOR] ffprobe falló (rc=%s): %s", proc.returncode, stderr.decode(errors="ignore"))
        raise BusinessRuleException("El archivo de video está dañado o no contiene una pista válida.")

    payload = json.loads(stdout.decode("utf-8", errors="ignore") or "{}")
    streams = payload.get("streams") or []
    if not streams:
        raise BusinessRuleException("El archivo no contiene una pista de video válida.")

    stream = streams[0]
    width = int(stream.get("width") or 0)
    height = int(stream.get("height") or 0)
    fps = parse_frame_rate(stream.get("avg_frame_rate")) or parse_frame_rate(stream.get("r_frame_rate"))
    raw_duration = (payload.get("format") or {}).get("duration")
    try:
        duration = float(raw_duration) if raw_duration is not None else None
    except (TypeError, ValueError):
        duration = None
    codec_name = (stream.get("codec_name") or "").lower().strip() or None

    return VideoMetadata(
        width=width,
        height=height,
        fps=fps,
        duration=duration,
        codec_name=codec_name,
    )


async def _transcode_video(
    ffmpeg_bin: str,
    input_path: str,
    output_path: str,
    target_w: int,
    target_h: int,
    duration: Optional[float] = None,
) -> None:
    """Transcodifica un video a MP4 H.264/AAC hasta 720p conservando sus frames y duración originales."""
    cmd = [
        ffmpeg_bin,
        "-y",
        "-i", input_path,
        "-vf", f"scale={target_w}:{target_h}:flags=lanczos",
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-crf", "23",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "128k",
        "-movflags", "+faststart",
        output_path,
    ]
    timeout_sec = max(300.0, (duration or 60.0) * 10.0)
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        _, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout_sec)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        raise BusinessRuleException("La optimización del video excedió el tiempo límite.")

    if proc.returncode != 0:
        logger.error("[VIDEO_PROCESSOR] ffmpeg falló (rc=%s): %s", proc.returncode, stderr.decode(errors="ignore"))
        raise BusinessRuleException("No fue posible procesar el video seleccionado.")


async def normalize_video_if_needed(
    content: bytes,
    extension: str,
    content_type: str,
) -> tuple[bytes, str, str]:
    """
    Valida formato y normaliza resolución cuando excede 720p
    o usa un contenedor/códec no estándar para reproducción web.
    """
    ext = extension.lower()
    validate_video_magic_bytes(content, ext)

    if not shutil.which("ffprobe"):
        logger.warning(
            "[VIDEO_PROCESSOR] ffprobe no está disponible en PATH; omitiendo inspección/transcodificación local."
        )
        return content, ext, content_type

    input_path: Optional[str] = None
    output_path: Optional[str] = None
    try:
        with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp_in:
            tmp_in.write(content)
            input_path = tmp_in.name

        meta = await probe_video_metadata(input_path)
        if meta is None:
            return content, ext, content_type

        max_duration = settings.MAX_VIDEO_DURATION_SECONDS
        if (
            max_duration is not None
            and max_duration > 0
            and meta.duration is not None
            and meta.duration > max_duration + _DURATION_TOLERANCE_SECONDS
        ):
            raise BusinessRuleException(
                f"El video supera la duración máxima permitida de {max_duration} segundos."
            )

        target_w, target_h = calcular_dimensiones_objetivo(
            meta.width,
            meta.height,
            max_long=settings.MAX_VIDEO_WIDTH,
            max_short=settings.MAX_VIDEO_HEIGHT,
        )
        excede_resolucion = (target_w, target_h) != (meta.width, meta.height)
        max_fps = settings.MAX_VIDEO_FPS
        excede_fps = (
            max_fps is not None
            and max_fps > 0
            and meta.fps is not None
            and meta.fps > max_fps + _FPS_TOLERANCE
        )
        formato_no_web = ext in {".mov", ".3gp"} or (
            meta.codec_name is not None and meta.codec_name not in _WEB_FRIENDLY_VIDEO_CODECS
        )

        if not (excede_resolucion or excede_fps or formato_no_web):
            return content, ext, content_type

        ffmpeg_bin = shutil.which("ffmpeg")
        if not settings.VIDEO_TRANSCODE_ENABLED or not ffmpeg_bin:
            if excede_resolucion:
                raise BusinessRuleException(
                    "El video supera la resolución máxima permitida de 720p."
                )
            if excede_fps:
                raise BusinessRuleException(
                    f"El video supera el máximo permitido de {max_fps} fps."
                )
            return content, ext, content_type

        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp_out:
            output_path = tmp_out.name

        await _transcode_video(
            ffmpeg_bin,
            input_path,
            output_path,
            target_w,
            target_h,
            duration=meta.duration,
        )

        with open(output_path, "rb") as out_file:
            normalized = out_file.read()

        if not normalized:
            raise BusinessRuleException("No se pudo generar el video optimizado.")
        max_video_bytes = settings.MAX_VIDEO_UPLOAD_SIZE_BYTES
        if max_video_bytes is not None and max_video_bytes > 0 and len(normalized) > max_video_bytes:
            max_mb = max_video_bytes // (1024 * 1024)
            raise BusinessRuleException(
                f"El video optimizado supera el tamaño máximo permitido de {max_mb} MB."
            )
        return normalized, ".mp4", "video/mp4"
    finally:
        for path in (input_path, output_path):
            if path and os.path.exists(path):
                try:
                    os.remove(path)
                except OSError:
                    pass


__all__ = [
    "VideoMetadata",
    "validate_video_magic_bytes",
    "calcular_dimensiones_objetivo",
    "parse_frame_rate",
    "probe_video_metadata",
    "normalize_video_if_needed",
]
