"""Tests for the Facebox API helpers."""
from http import HTTPStatus

import requests
import requests_mock

from custom_components.facebox import api as facebox

MOCK_HEALTH = {"success": True, "hostname": "facebox-host"}
MOCK_FACE = {
    "confidence": 0.5812028911604818,
    "id": "john.jpg",
    "matched": True,
    "name": "John Lennon",
    "rect": {"height": 75, "left": 63, "top": 262, "width": 74},
}


def test_encode_image() -> None:
    """Binary image data is encoded for the Facebox API."""
    assert facebox.encode_image(b"test") == "dGVzdA=="


def test_parse_faces_and_matches() -> None:
    """Raw API faces are converted to Home Assistant face information."""
    parsed = facebox.parse_faces([MOCK_FACE])
    assert parsed == [
        {
            "name": "John Lennon",
            "image_id": "john.jpg",
            "confidence": 58.12,
            "matched": True,
            "bounding_box": MOCK_FACE["rect"],
        }
    ]
    assert facebox.get_matched_faces(parsed) == {"John Lennon": 58.12}


def test_unmatched_face_hides_identity() -> None:
    """Unmatched faces do not expose a Facebox name or image id."""
    raw = dict(MOCK_FACE, matched=False)
    parsed = facebox.parse_faces([raw])[0]
    assert parsed["name"] is None
    assert parsed["image_id"] is None
    assert parsed["matched"] is False


def test_check_box_health(requests_mock: requests_mock.Mocker) -> None:
    """A healthy Facebox instance returns its hostname."""
    url = "http://192.0.2.1:8080/healthz"
    requests_mock.get(url, status_code=HTTPStatus.OK, json=MOCK_HEALTH)
    assert facebox.check_box_health(url, None, None) == "facebox-host"


def test_check_box_health_auth_failure(requests_mock: requests_mock.Mocker) -> None:
    """Authentication failures are rejected cleanly."""
    url = "http://192.0.2.1:8080/healthz"
    requests_mock.get(url, status_code=HTTPStatus.UNAUTHORIZED)
    assert facebox.check_box_health(url, "user", "pass") is None


def test_check_box_health_connection_failure(
    requests_mock: requests_mock.Mocker,
) -> None:
    """Connection failures are rejected cleanly."""
    url = "http://192.0.2.1:8080/healthz"
    requests_mock.get(url, exc=requests.ConnectionError("offline"))
    assert facebox.check_box_health(url, None, None) is None
