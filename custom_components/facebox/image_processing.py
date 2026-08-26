"""Image processing platform for Machinebox Facebox."""
from __future__ import annotations

import base64
from http import HTTPStatus
import logging
from pathlib import Path
from typing import Any

import requests
import voluptuous as vol

from homeassistant.components.image_processing import (
    ATTR_CONFIDENCE,
    PLATFORM_SCHEMA,
    ImageProcessingFaceEntity,
)
from homeassistant.const import (
    ATTR_ENTITY_ID,
    ATTR_NAME,
    CONF_ENTITY_ID,
    CONF_IP_ADDRESS,
    CONF_NAME,
    CONF_PASSWORD,
    CONF_PORT,
    CONF_SOURCE,
    CONF_USERNAME,
)
from homeassistant.core import HomeAssistant, ServiceCall, split_entity_id
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType

from .const import (
    ATTR_BOUNDING_BOX,
    ATTR_IMAGE_ID,
    ATTR_MATCHED,
    CLASSIFIER,
    DATA_FACEBOX,
    DOMAIN,
    FILE_PATH,
    LEGACY_SERVICE_TEACH_FACE,
    REQUEST_TIMEOUT,
    SERVICE_TEACH_FACE,
)

_LOGGER = logging.getLogger(__name__)

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Required(CONF_IP_ADDRESS): cv.string,
        vol.Required(CONF_PORT): cv.port,
        vol.Optional(CONF_USERNAME): cv.string,
        vol.Optional(CONF_PASSWORD): cv.string,
    }
)

SERVICE_TEACH_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_ENTITY_ID): cv.entity_ids,
        vol.Required(ATTR_NAME): cv.string,
        vol.Required(FILE_PATH): cv.string,
    }
)


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


async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    async_add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None,
) -> None:
    """Set up Facebox image-processing entities from YAML."""
    del discovery_info
    classifiers = hass.data.setdefault(DATA_FACEBOX, [])

    ip_address = config[CONF_IP_ADDRESS]
    port = config[CONF_PORT]
    username = config.get(CONF_USERNAME)
    password = config.get(CONF_PASSWORD)

    hostname = await hass.async_add_executor_job(
        check_box_health,
        f"http://{ip_address}:{port}/healthz",
        username,
        password,
    )
    if hostname is None:
        return

    entities: list[FaceClassifyEntity] = []
    for camera in config[CONF_SOURCE]:
        entity = FaceClassifyEntity(
            ip_address,
            port,
            username,
            password,
            hostname,
            camera[CONF_ENTITY_ID],
            camera.get(CONF_NAME),
        )
        entities.append(entity)
        classifiers.append(entity)

    async_add_entities(entities)

    async def async_teach_face(service: ServiceCall) -> None:
        """Handle Facebox teach action."""
        requested = service.data.get(ATTR_ENTITY_ID)
        selected = classifiers
        if requested:
            selected = [entity for entity in classifiers if entity.entity_id in requested]

        name = service.data[ATTR_NAME]
        file_path = service.data[FILE_PATH]
        for entity in selected:
            await entity.async_teach(name, file_path)

    if not hass.services.has_service(DOMAIN, SERVICE_TEACH_FACE):
        hass.services.async_register(
            DOMAIN,
            SERVICE_TEACH_FACE,
            async_teach_face,
            schema=SERVICE_TEACH_SCHEMA,
        )

    # Preserve the historic action name for existing automations.
    if not hass.services.has_service("image_processing", LEGACY_SERVICE_TEACH_FACE):
        hass.services.async_register(
            "image_processing",
            LEGACY_SERVICE_TEACH_FACE,
            async_teach_face,
            schema=SERVICE_TEACH_SCHEMA,
        )


class FaceClassifyEntity(ImageProcessingFaceEntity):
    """Facebox image-processing entity."""

    _attr_should_poll = True

    def __init__(
        self,
        ip_address: str,
        port: int,
        username: str | None,
        password: str | None,
        hostname: str,
        camera_entity: str,
        name: str | None = None,
    ) -> None:
        """Initialize a Facebox classifier entity."""
        super().__init__()
        self._url_check = f"http://{ip_address}:{port}/{CLASSIFIER}/check"
        self._url_teach = f"http://{ip_address}:{port}/{CLASSIFIER}/teach"
        self._username = username
        self._password = password
        self._hostname = hostname
        self._attr_camera_entity = camera_entity
        camera_name = split_entity_id(camera_entity)[1]
        self._attr_name = name or f"Facebox {camera_name}"
        self._attr_unique_id = f"{hostname}_{camera_entity}"
        self._matched: dict[str, float] = {}

    def process_image(self, image: bytes) -> None:
        """Process an image with Facebox."""
        response = post_image(self._url_check, image, self._username, self._password)
        if response is None:
            self.total_faces = 0
            self.faces = []
            self._matched = {}
            return

        try:
            payload = response.json()
        except ValueError:
            _LOGGER.error("Facebox returned invalid JSON")
            return

        if not payload.get("success"):
            _LOGGER.warning("Facebox did not successfully process the image")
            return

        faces = parse_faces(payload.get("faces", []))
        self._matched = get_matched_faces(faces)
        self.process_faces(faces, int(payload.get("facesCount", len(faces))))

    async def async_teach(self, name: str, file_path: str) -> None:
        """Teach Facebox a face without blocking Home Assistant's event loop."""
        if not self.hass.config.is_allowed_path(file_path) or not valid_file_path(file_path):
            _LOGGER.error("Facebox cannot access image file: %s", file_path)
            return
        await self.hass.async_add_executor_job(
            teach_file,
            self._url_teach,
            name,
            file_path,
            self._username,
            self._password,
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return Facebox-specific state attributes."""
        return {
            "hostname": self._hostname,
            "matched_faces": self._matched,
            "total_matched_faces": len(self._matched),
        }
