"""Rezervni AI korak Autopilota: Claude Sonnet 5.5 za ekran koji lokalna pravila ne znaju.

Poziva se samo iz `autopilot.Autopilot._ai_step` -- kad lokalno pravilo ne
prepozna ekran ili kad ocekivani prelaz izostane posle ogranicenog broja
pokusaja. Salje jedan screenshot, trenutni korak i ocekivani ekran, a dobija
najvise jednu akciju (tap / cekaj / pauza). Kljuc se cita iz
`ANTHROPIC_API_KEY` (SDK ga sam cita) i nigde se ne loguje.
"""
from __future__ import annotations

import base64
import io
import json
import os
from dataclasses import dataclass, field
from pathlib import Path

# Sonnet 5.5: AI se zove retko (poznati ekrani idu lokalno), a bas tada
# su vazni precizan klik i prepoznavanje kupovine; razlika u ceni je ~0.4 centa
# po pozivu. MM_AUTOPILOT_MODEL=claude-haiku-5-5 vraca Haiku bez izmene koda.
MODEL = os.environ.get("MM_AUTOPILOT_MODEL", "claude-sonnet-5-5")
# Manja slika: dovoljno za citanje dugmadi, upola manje tokena od pune.
SEND_SIZE = (450, 800)
REQUEST_TIMEOUT_SECONDS = 60.0

SYSTEM_PROMPT = """You help an automation tool play the mobile game Match Masters unattended (portrait screen). The goal is simple: keep starting new matches. You see one screenshot, the current step, the screen the tool expected and sometimes a goal for this screen. Propose at most ONE action.

Actions:
- "tap": x, y in the pixel coordinates of the image you see (it is {w}x{h}).
- "scroll_down" / "scroll_up": drag a list to see what is further down / further up (e.g. the booster list). x, y = a point inside the list.
- "wait": loading, transition, animation or matchmaking; nothing to tap.
- "pause": you are not sure, or the only way forward costs something (see below).
If you do not know the screen but it is a pop-up/panel with a visible close X (usually a round X in a top corner), tap that X instead of pausing: closing is always free and brings back the lobby.

Free (always fine): closing pop-ups with X / Close / Later / No thanks, pressing Continue / OK / Collect / Claim (free) / Awesome, and choosing one of the player's OWN boosters or perks and pressing PLAY to start a match - using boosters is the point, it is not spending.
Costs (never tap): buttons with a coin/gem/money price, Buy, Purchase, Refill, Unlock Now, Spend, watching an ad, accepting terms, account or settings changes.
- spends_resources=true if the screen offers something that costs coins/gems/money (even if you tap X on it).
- tap_is_free=true only if the element you tap is itself free (X, Close, Continue, OK, Collect, Awesome, a booster card the player owns, PLAY). Never true for a priced button.
- confidence is 0..1: how sure you are that this one action is right and free."""

OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "action": {"type": "string", "enum": ["tap", "scroll_down", "scroll_up", "wait", "pause"]},
        "x": {"type": "integer"},
        "y": {"type": "integer"},
        "confidence": {"type": "number"},
        "screen": {"type": "string"},
        "reason": {"type": "string"},
        "spends_resources": {"type": "boolean"},
        "tap_is_free": {"type": "boolean"},
    },
    "required": ["action", "x", "y", "confidence", "screen", "reason", "spends_resources", "tap_is_free"],
    "additionalProperties": False,
}

ACTIONS = ("tap", "scroll_down", "scroll_up", "wait", "pause")


KEY_FILE = Path(__file__).resolve().parent / "autopilot" / "bluestacks autopilot api.txt"


def api_key() -> str | None:
    """`ANTHROPIC_API_KEY`, a ako ga nema, lokalni fajl (u .gitignore). Nikad se ne loguje."""
    key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if key:
        return key
    try:
        text = KEY_FILE.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return text.splitlines()[0].strip() if text else None


class AiUnavailable(RuntimeError):
    """AI se ne moze pozvati (nema kljuca, nema SDK-a, greska API-ja)."""


@dataclass
class AiProposal:
    action: str  # tap | scroll_down | scroll_up | wait | pause
    x: int = 0  # u koordinatama referentnog ekrana (900x1600)
    y: int = 0
    confidence: float = 0.0
    screen: str = ""
    reason: str = ""
    spends_resources: bool = False
    tap_is_free: bool = False
    meta: dict = field(default_factory=dict)


def _downscaled_png(png: bytes) -> tuple[bytes, tuple[int, int]]:
    from PIL import Image
    image = Image.open(io.BytesIO(png)).convert("RGB")
    original = image.size
    image = image.resize(SEND_SIZE)
    out = io.BytesIO()
    image.save(out, format="PNG", optimize=True)
    return out.getvalue(), original


def parse_proposal(text: str, scale: tuple[float, float]) -> AiProposal:
    data = json.loads(text)
    action = str(data.get("action", "pause"))
    if action not in ACTIONS:
        action = "pause"
    return AiProposal(
        action=action,
        x=int(round(float(data.get("x", 0)) * scale[0])),
        y=int(round(float(data.get("y", 0)) * scale[1])),
        confidence=float(data.get("confidence", 0.0)),
        screen=str(data.get("screen", ""))[:200],
        reason=str(data.get("reason", ""))[:400],
        spends_resources=bool(data.get("spends_resources", False)),
        tap_is_free=bool(data.get("tap_is_free", False)),
    )


class ClaudeAdvisor:
    """Jedan poziv = jedan screenshot = najvise jedna predlozena akcija."""

    def __init__(self, model: str = MODEL):
        self.model = model
        self._client = None

    def _get_client(self):
        if self._client is None:
            key = api_key()
            if not key:
                raise AiUnavailable(f"ANTHROPIC_API_KEY nije postavljen (a nema ni {KEY_FILE.name})")
            try:
                import anthropic
            except ImportError as exc:
                raise AiUnavailable("paket 'anthropic' nije instaliran (pip install anthropic)") from exc
            self._client = anthropic.Anthropic(api_key=key, timeout=REQUEST_TIMEOUT_SECONDS, max_retries=1)
        return self._client

    def propose(self, png: bytes, *, step: str, expected: list[str], why: str,
                last_screen: str | None, hint: str = "") -> AiProposal:
        import anthropic
        client = self._get_client()
        small, original = _downscaled_png(png)
        scale = (original[0] / SEND_SIZE[0], original[1] / SEND_SIZE[1])
        prompt = (
            f"Current step: {step}\n"
            f"Expected screen(s): {', '.join(expected) or 'any menu screen that leads back to the lobby'}\n"
            f"Last recognised screen: {last_screen or 'none'}\n"
            f"Why you are asked: {why}\n"
            + (f"Goal on this screen: {hint}\n" if hint else "")
            + "Propose one action."
        )
        try:
            # Server-side fallback (ako Sonnet odbije zahtev) postoji samo za
            # Sonnet/Opus na Claude API-ju; Haiku ide bez njega.
            fallback = ({"betas": ["server-side-fallback-2026-07-01"],
                         "extra_body": {"fallbacks": "default"}}
                        if "haiku" not in self.model else {})
            create = client.beta.messages.create if fallback else client.messages.create
            response = create(
                model=self.model,
                max_tokens=4000,
                **fallback,
                system=SYSTEM_PROMPT.format(w=SEND_SIZE[0], h=SEND_SIZE[1]),
                output_config={"effort": "low", "format": {"type": "json_schema", "schema": OUTPUT_SCHEMA}},
                messages=[{"role": "user", "content": [
                    {"type": "image", "source": {"type": "base64", "media_type": "image/png",
                                                 "data": base64.standard_b64encode(small).decode("ascii")}},
                    {"type": "text", "text": prompt},
                ]}],
            )
        except anthropic.APIConnectionError as exc:
            raise AiUnavailable(f"mreza: {exc}") from exc
        except anthropic.APIStatusError as exc:
            raise AiUnavailable(f"API {exc.status_code}: {exc.message}") from exc
        meta = {
            "request_id": getattr(response, "_request_id", None),
            "model": getattr(response, "model", self.model),
            "stop_reason": response.stop_reason,
            "input_tokens": getattr(response.usage, "input_tokens", None),
            "output_tokens": getattr(response.usage, "output_tokens", None),
        }
        if response.stop_reason == "refusal":
            return AiProposal("pause", reason="model je odbio zahtev", meta=meta)
        text = next((b.text for b in response.content if b.type == "text"), "")
        try:
            proposal = parse_proposal(text, scale)
        except (ValueError, TypeError) as exc:
            return AiProposal("pause", reason=f"neispravan odgovor: {exc}", meta=meta)
        proposal.meta = meta
        return proposal
