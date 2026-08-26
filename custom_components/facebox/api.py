"""HTTP and parsing helpers for the Machinebox Facebox API."""
from __future__ import annotations

import base64
from http import HTTPStatus
import logging
from pathlib import Path
from typing import Any

import requests

from .const import (
    ATTR_BOUNDING_BOX,
    ATTR_IMAGE_ID,
    ATTR_MATCHED,
    REQUEST_TIMEOUT,
)

_LOGGER = logging.getLogger(__name__)

ATTR_CONFIDENCE = "confidence"
ATTR_NAME = "name"


def _auth(username: str | None, password: str | None) -> Any | None:
    """Return HTTP basic authentication when configured."""
    if not username:
        return None
    return requests.auth.HTTPBasicAuth(username, password or "")


def check_box_health(url: str, username: str | None, password: str | None) -> str | None:
    """Check Facebox health and return its hostname when healthy."""
    try:
        response = requests.get(
            url,
            auth=_auth(username, password),
            timeout=REQUEST_TIMEOUT,
        )
    except requests.RequestException as err:
        _LOGGER.error("Unable to connect to Facebox: %s", err)
        return None

    if response.status_code == HTTPStatus.UNAUTHORIZED:
        _LOGGER.error("Facebox authentication failed")
        return None
    if response.status_code != HTTPStatus.OK:
        _LOGGER.error("Facebox health check failed with HTTP %s", response.status_code)
        return None

    try:
        return str(response.json()["hostname"])
    except (KeyError, TypeError, ValueError):
        _LOGGER.error("Facebox health response did not contain a hostname")
        return None


def encode_image(image: bytes) -> str:
    """Base64 encode image bytes for the Facebox API."""
    return base64.b64encode(image).decode("ascii")


def get_matched_faces(faces: list[dict[str, Any]]) -> dict[str, float]:
    """Return matched face names and confidence percentages."""
    return {
        str(face[ATTR_NAME]): round(float(face[ATTR_CONFIDENCE]), 2)
        for face in faces
        if face.get(ATTR_MATCHED) and face.get(ATTR_NAME)
    }


def parse_faces(api_faces: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Parse raw Facebox faces into Home Assistant face information."""
    faces: list[dict[str, Any]] = []
    for entry in api_faces:
        matched = bool(entry.get("matched"))
        confidence = round(100.0 * float(entry.get("confidence", 0)), 2)
        faces.append(
            {
                ATTR_NAME: entry.get("name") if matched else None,
                ATTR_IMAGE_ID: entry.get("id") if matched else None,
                ATTR_CONFIDENCE: confidence,
                ATTR_MATCHED: matched,
                ATTR_BOUNDING_BOX: entry.get("rect", {}),
            }
        )
    return faces


def post_image(
    url: str,
    image: bytes,
    username: str | None,
    password: str | None,
) -> requests.Response | None:
    """Post an image to Facebox."""
    try:
        response = requests.post(
            url,
            json={"base64": encode_image(image)},
            auth=_auth(username, password),
            timeout=REQUEST_TIMEOUT,
        )
    except requests.RequestException as err:
        _LOGGER.error("Unable to send image to Facebox: %s", err)
        return None

    if response.status_code == HTTPStatus.UNAUTHORIZED:
        _LOGGER.error("Facebox authentication failed")
        return None
    return response


def teach_file(
    url: str,
    name: str,
    file_path: str,
    username: str | None,
    password: str | None,
) -> bool:
    """Teach Facebox a face from a local image file."""
    try:
        with Path(file_path).open("rb") as open_file:
            response = requests.post(
                url,
                data={ATTR_NAME: name, "id": file_path},
                files={"file": open_file},
                auth=_auth(username, password),
                timeout=REQUEST_TIMEOUT,
            )
    except (OSError, requests.RequestException) as err:
        _LOGGER.error("Unable to teach Facebox from %s: %s", file_path, err)
        return False

    if response.status_code == HTTPStatus.UNAUTHORIZED:
        _LOGGER.error("Facebox authentication failed")
        return False
    if response.status_code == HTTPStatus.BAD_REQUEST:
        _LOGGER.error("Facebox rejected %s: %s", file_path, response.text)
        return False
    if not response.ok:
        _LOGGER.error("Facebox teaching failed with HTTP %s", response.status_code)
        return False
    return True


def valid_file_path(file_path: str) -> bool:
    """Return whether a path points to a supported local image file."""
    path = Path(file_path)
    return path.is_file() and path.suffix.lower() in {".jpg", ".jpeg", ".png"}
