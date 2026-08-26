# Machinebox Facebox for Home Assistant

A Home Assistant custom integration for face detection and recognition using a local [Machinebox Facebox](https://machinebox.io/) service.

This repository is packaged for HACS and uses Home Assistant's `image_processing` building-block integration. Configuration remains YAML-based because Facebox provides image-processing platform entities sourced from camera entities.

## Installation

### HACS

1. Add this repository to HACS as a custom repository with category **Integration**.
2. Install **Machinebox Facebox**.
3. Restart Home Assistant.

### Manual

Copy `custom_components/facebox` into your Home Assistant `custom_components` directory, then restart Home Assistant.

## Configuration

Add a Facebox image-processing platform to `configuration.yaml`:

```yaml
image_processing:
  - platform: facebox
    ip_address: 192.168.0.10
    port: 8080
    username: my_username   # optional
    password: my_password   # optional
    source:
      - entity_id: camera.front_door
        name: Front Door Facebox
```

`ip_address` is the host or IP address of the Facebox service. `port` is the HTTP port, normally `8080`. `username` and `password` are optional HTTP Basic Auth credentials. `source` contains one or more Home Assistant camera entities.

The resulting `image_processing` entity reports Facebox detections and exposes `faces`, `matched_faces`, `total_faces`, `total_matched_faces`, and the Facebox hostname. Home Assistant fires `image_processing.detect_face` events for detected faces that meet the configured confidence threshold.

## Scan on demand

Home Assistant's image-processing building block polls by default. For motion-triggered cameras you can set a long `scan_interval` and explicitly call `image_processing.scan` when a fresh image is available.

```yaml
image_processing:
  - platform: facebox
    ip_address: 192.168.0.10
    port: 8080
    scan_interval: 10000
    source:
      - entity_id: camera.front_door
```

Then call:

```yaml
action: image_processing.scan
target:
  entity_id: image_processing.front_door_facebox
```

## Teach a face

The preferred action is `facebox.teach_face`:

```yaml
action: facebox.teach_face
data:
  entity_id: image_processing.front_door_facebox
  name: Ringo_Starr
  file_path: /config/images/ringo.jpg
```

The image path must be allowed by Home Assistant and must be a `.jpg`, `.jpeg`, or `.png` file. The historical `image_processing.facebox_teach_face` action is also registered for compatibility with existing automations.

## Example recognition automation

```yaml
- alias: Notify when Ringo is recognised
  triggers:
    - trigger: event
      event_type: image_processing.detect_face
      event_data:
        name: Ringo_Starr
  actions:
    - action: notify.notify
      data:
        title: Door camera
        message: >-
          Ringo Starr recognised with confidence
          {{ trigger.event.data.confidence }}
```

## Running Facebox

A typical container invocation is:

```bash
docker run -p 8080:8080 -e "MB_KEY=$MB_KEY" machinebox/facebox
```

With HTTP Basic Auth:

```bash
docker run \
  -e "MB_BASICAUTH_USER=my_username" \
  -e "MB_BASICAUTH_PASS=my_password" \
  -e "MB_KEY=$MB_KEY" \
  -p 8080:8080 \
  machinebox/facebox
```

Machinebox Facebox itself is an external project and may have its own licensing, availability, or maintenance constraints. This integration only connects Home Assistant to a running compatible Facebox API.

## Development and validation

Pull requests run Python compilation, pyflakes, pytest, Home Assistant hassfest, HACS validation, and a manifest/tag synchronization gate. Merging a pull request to `master` creates the next semantic patch release automatically.
