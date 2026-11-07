"""Start-up screen: plays the intro video centred on a white background, then fades it out."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QEasingCurve, QRectF, QSize, Qt, QTimer, QUrl, QVariantAnimation, pyqtSignal
from PyQt6.QtGui import QColor, QImage, QPainter
from PyQt6.QtMultimedia import QAudioOutput, QMediaPlayer, QVideoFrame, QVideoSink
from PyQt6.QtWidgets import QWidget

from frontend import theme

BACKGROUND = QColor(theme.SPLASH_BG)
WHITE_LIFT = QColor(6, 6, 6)
# The video takes this share of the smaller screen side.
VIDEO_SCREEN_SHARE = 0.62
HOLD_LAST_FRAME_MS = 250
FADE_OUT_MS = 900
SKIP_FADE_MS = 350
# Give up waiting for the video after this long (e.g. a missing codec), so the app never hangs here.
SAFETY_TIMEOUT_MS = 20_000


class SplashView(QWidget):
    """Paints the frames itself (through a QVideoSink) so it can centre, scale and fade them freely.

    Emits ``finished`` exactly once: after the fade-out, when the user skips (click / Esc / Space /
    Enter), or straight away if the video cannot be played.
    """

    finished = pyqtSignal()

    def __init__(self, video_path: Path, parent: QWidget | None = None):
        super().__init__(parent)
        self._video_path = video_path
        self._frame: QImage | None = None
        self._opacity = 1.0
        self._done = False
        self._fading = False

        self.setAutoFillBackground(True)
        palette = self.palette()
        palette.setColor(self.backgroundRole(), BACKGROUND)
        self.setPalette(palette)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("Click to skip")

        self._audio = QAudioOutput(self)
        self._audio.setVolume(0.6)
        self._sink = QVideoSink(self)
        self._sink.videoFrameChanged.connect(self._on_frame)
        self._player = QMediaPlayer(self)
        self._player.setAudioOutput(self._audio)
        self._player.setVideoSink(self._sink)
        self._player.mediaStatusChanged.connect(self._on_status)
        self._player.errorOccurred.connect(lambda *_: self._finish())

        self._fade = QVariantAnimation(self)
        self._fade.setStartValue(1.0)
        self._fade.setEndValue(0.0)
        self._fade.setEasingCurve(QEasingCurve.Type.InOutQuad)
        self._fade.valueChanged.connect(self._set_opacity)
        self._fade.finished.connect(self._finish)

        self._safety = QTimer(self, singleShot=True, interval=SAFETY_TIMEOUT_MS)
        self._safety.timeout.connect(self._finish)

    # ------------------------------------------------------------------ control
    def start(self) -> None:
        if not self._video_path.exists():
            QTimer.singleShot(0, self._finish)
            return
        self._safety.start()
        self._player.setSource(QUrl.fromLocalFile(str(self._video_path)))
        self._player.play()
        self.setFocus()

    def skip(self) -> None:
        self._fade_out(SKIP_FADE_MS)

    # ------------------------------------------------------------------ events
    def mousePressEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        self.skip()

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() in (Qt.Key.Key_Escape, Qt.Key.Key_Space, Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.skip()
        else:
            super().keyPressEvent(event)

    def sizeHint(self) -> QSize:
        return QSize(900, 700)

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.fillRect(self.rect(), BACKGROUND)
        if self._frame is None or self._frame.isNull():
            return
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.setOpacity(self._opacity)
        target = self._target_rect()
        painter.drawImage(target, self._frame)
        # The video's background is off-white (RGB 249-253), which shows as a faint square on the
        # pure white window. Lifting every channel a little turns it pure white; the logo itself
        # changes by ~2%, which is not visible.
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
        painter.fillRect(target, WHITE_LIFT)

    # ------------------------------------------------------------------ internals
    def _target_rect(self) -> QRectF:
        """Largest rect with the video's aspect ratio that fits the share of the screen, centred."""
        box = min(self.width(), self.height()) * VIDEO_SCREEN_SHARE
        frame_w, frame_h = self._frame.width(), self._frame.height()
        scale = min(box / frame_w, box / frame_h)
        w, h = frame_w * scale, frame_h * scale
        return QRectF((self.width() - w) / 2, (self.height() - h) / 2, w, h)

    def _on_frame(self, frame: QVideoFrame) -> None:
        if not frame.isValid():
            return  # keep showing the last good frame (the backend may send an empty one at the end)
        image = frame.toImage()
        if not image.isNull():
            self._frame = image
            self.update()

    def _on_status(self, status: QMediaPlayer.MediaStatus) -> None:
        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            QTimer.singleShot(HOLD_LAST_FRAME_MS, lambda: self._fade_out(FADE_OUT_MS))
        elif status == QMediaPlayer.MediaStatus.InvalidMedia:
            self._finish()

    def _fade_out(self, duration_ms: int) -> None:
        if self._fading or self._done:
            return
        self._fading = True
        self._fade.setDuration(duration_ms)
        self._fade.start()

    def _set_opacity(self, value: float) -> None:
        self._opacity = float(value)
        self._audio.setVolume(0.6 * self._opacity)
        self.update()

    def _finish(self) -> None:
        if self._done:
            return
        self._done = True
        self._safety.stop()
        self._player.stop()
        self._frame = None
        self.update()
        self.finished.emit()
