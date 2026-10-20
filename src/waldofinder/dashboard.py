"""Local experiment sessions, live events and independent human reviews."""

from __future__ import annotations

import hashlib
import json
import math
import re
import shutil
import threading
import time
from dataclasses import asdict
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from uuid import uuid4

from PIL import Image, ImageOps, UnidentifiedImageError

from . import __version__
from .geometry import Region, grid
from .provider import PROMPT, OpenRouter, model_is_2026, public_models
from .report import write_report
from .search import search

DEFAULTS = dict(
    strategy="grid",
    tiles=9,
    columns=None,
    overlap=0.08,
    max_depth=4,
    min_size=64,
    concurrency=4,
    max_requests=32,
    threshold=0.7,
    all_candidates=False,
    explore_negatives=False,
    max_tokens=2048,
    timeout=90,
    structured=True,
)
TERMINAL = {"completed", "cancelled", "failed", "interrupted"}
SAFE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,100}\Z")


class DashboardError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def now():
    return datetime.now(UTC).isoformat()


def save_json(path, value):
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")
    temporary.replace(path)


def validate_config(payload):
    if not isinstance(payload, dict):
        raise DashboardError("Search configuration must be an object.")
    unknown = set(payload) - set(DEFAULTS) - {"models", "image_id"}
    if unknown:
        raise DashboardError("Unknown search configuration field.")
    config = {**DEFAULTS, **{k: v for k, v in payload.items() if k in DEFAULTS}}
    limits = dict(
        tiles=(1, 256),
        max_depth=(1, 10),
        min_size=(1, 4096),
        concurrency=(1, 8),
        max_requests=(1, 256),
        max_tokens=(64, 8192),
    )
    for key, (minimum, maximum) in limits.items():
        value = config[key]
        if type(value) is not int or not minimum <= value <= maximum:
            raise DashboardError(f"{key.replace('_', ' ')} must be {minimum}–{maximum}.")
    for key, (minimum, maximum) in dict(
        overlap=(0, 0.5), threshold=(0, 1), timeout=(1, 180)
    ).items():
        value = config[key]
        if (
            type(value) not in (float, int)
            or not math.isfinite(value)
            or not minimum <= value <= maximum
        ):
            raise DashboardError(f"Invalid {key}.")
    for key in ("all_candidates", "explore_negatives", "structured"):
        if type(config[key]) is not bool:
            raise DashboardError(f"Invalid {key}.")
    if config["strategy"] not in ("grid", "binary"):
        raise DashboardError("Choose grid or binary search.")
    if config["columns"] is not None and (
        type(config["columns"]) is not int or config["columns"] < 1
    ):
        raise DashboardError("Columns must be a positive integer.")
    models = payload.get("models")
    if (
        not isinstance(models, list)
        or not 1 <= len(models) <= 4
        or any(not isinstance(m, str) or not 1 <= len(m) <= 200 for m in models)
        or len(set(models)) != len(models)
    ):
        raise DashboardError("Choose between one and four distinct models.")
    return config, models


class Session:
    def __init__(self, folder, state):
        self.folder, self.state = folder, state
        self.condition = threading.Condition(threading.RLock())
        self.cancel = threading.Event()
        self.events = []
        self.state.setdefault("seq", 0)

    def snapshot(self):
        with self.condition:
            return json.loads(json.dumps(self.state))

    def emit(self, kind, payload=None):
        payload = payload or {}
        with self.condition:
            self.state["seq"] += 1
            event = {"seq": self.state["seq"], "type": kind, "at": now(), "payload": payload}
            self.events.append(event)
            if "model_index" in payload:
                model = self.state["models"][payload["model_index"]]
                if kind == "model_started":
                    model["status"] = "running"
                elif kind.startswith("region_"):
                    if kind == "region_finished":
                        record = payload["observation"]
                        key = record["region"]["id"]
                        model["regions"].setdefault(key, {}).update(record, phase="done")
                    elif kind == "region_resolved":
                        model["regions"][payload["region_id"]]["resolution"] = payload["resolution"]
                    else:
                        key = payload["region"]["id"]
                        model["regions"].setdefault(key, {}).update(
                            {k: v for k, v in payload.items() if k != "model_index"},
                            phase="processing" if kind == "region_started" else "queued",
                        )
                elif kind == "model_finished":
                    model.update(
                        status="cancelled" if self.cancel.is_set() else "completed",
                        summary=payload["summary"],
                    )
            if kind == "run_finished":
                self.state.update(status=payload["status"], finished_at=now())
            elif kind == "run_error":
                self.state.update(status="failed", error=payload["message"], finished_at=now())
            save_json(self.folder / "session.json", self.state)
            with (self.folder / "events.jsonl").open("a") as file:
                file.write(json.dumps(event, allow_nan=False) + "\n")
            self.condition.notify_all()


class Dashboard:
    def __init__(self, args, provider_factory=OpenRouter, model_loader=public_models):
        self.args = args
        self.root = args.runs_dir.resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.uploads = self.root / ".uploads"
        self.uploads.mkdir(exist_ok=True)
        self.sample = args.image.resolve() if args.image else None
        self.provider_factory, self.model_loader = provider_factory, model_loader
        self.sessions = {}
        self.lock = threading.RLock()
        self.catalog = {}
        self.catalog_at = 0

    def models(self):
        with self.lock:
            if not self.catalog or time.monotonic() - self.catalog_at > 300:
                try:
                    self.catalog = {
                        key: row for key, row in self.model_loader().items() if model_is_2026(row)
                    }
                    self.catalog_at = time.monotonic()
                except Exception:
                    raise DashboardError(
                        "OpenRouter model catalog unavailable. Try refreshing models.", 502
                    ) from None
            return [
                {
                    "id": name,
                    "name": row.get("name", name),
                    "structured": "structured_outputs" in row.get("supported_parameters", []),
                    "released": datetime.fromtimestamp(row["created"], UTC).date().isoformat(),
                }
                for name, row in sorted(self.catalog.items())
            ]

    def image(self, image_id):
        if image_id == "sample" and self.sample and self.sample.is_file():
            return self.sample
        if isinstance(image_id, str) and re.fullmatch(r"[0-9a-f]{32}", image_id):
            path = self.uploads / f"{image_id}.png"
            if path.is_file():
                return path
        if isinstance(image_id, str) and image_id.startswith("run:"):
            return self.get(image_id[4:]).folder / "input.png"
        raise DashboardError("Choose an image first.", 404)

    def image_info(self, image_id, name=None):
        path = self.image(image_id)
        with Image.open(path) as source:
            image = ImageOps.exif_transpose(source)
            w, h = image.size
        return {
            "id": image_id,
            "name": name or ("Beach scene" if image_id == "sample" else "Uploaded scene"),
            "width": w,
            "height": h,
            "url": f"/api/images/{image_id}",
        }

    def upload(self, raw, name):
        try:
            with Image.open(BytesIO(raw)) as source:
                if source.width * source.height > 40_000_000:
                    raise ValueError
                image = ImageOps.exif_transpose(source).convert("RGB")
        except (ValueError, OSError, UnidentifiedImageError, Image.DecompressionBombError):
            raise DashboardError(
                "Use a valid PNG, JPEG or WebP image, up to 40 megapixels."
            ) from None
        image_id = uuid4().hex
        image.save(self.uploads / f"{image_id}.png")
        return self.image_info(image_id, Path(name).name[:100])

    def preview(self, payload):
        config, _ = validate_config(payload)
        info = self.image_info(payload.get("image_id"))
        size = info["width"], info["height"]
        regions = (
            grid(size, config["tiles"], config["columns"])
            if config["strategy"] == "grid"
            else (Region("root", (0, 0, *size)).split() or [Region("root", (0, 0, *size))])
        )
        return {
            "regions": [
                {
                    "region": asdict(r),
                    "crop_box": r.padded(size, config["overlap"]),
                    "phase": "preview",
                }
                for r in regions
            ]
        }

    def _folder(self, run_id):
        if not isinstance(run_id, str) or not SAFE_ID.fullmatch(run_id):
            raise DashboardError("Run not found.", 404)
        folder = (self.root / run_id).resolve()
        if folder.parent != self.root or not folder.is_dir() or folder.is_symlink():
            raise DashboardError("Run not found.", 404)
        return folder

    def get(self, run_id):
        with self.lock:
            if run_id in self.sessions:
                return self.sessions[run_id]
            folder = self._folder(run_id)
            try:
                if (folder / "session.json").is_file():
                    state = json.loads((folder / "session.json").read_text())
                    if state["status"] not in TERMINAL:
                        state["status"] = "interrupted"
                        state["error"] = (
                            "Server stopped before this run finished. Completed observations are preserved."
                        )
                else:
                    result = json.loads((folder / "results.json").read_text())
                    state = dict(
                        id=run_id,
                        status="completed",
                        source="cli",
                        seq=0,
                        created_at=result["created_at"],
                        config=result["config"],
                        image={
                            "id": f"run:{run_id}",
                            "name": "Saved scene",
                            "url": f"/api/runs/{run_id}/files/input.png",
                            "width": result["image_size"][0],
                            "height": result["image_size"][1],
                        },
                        models=[],
                        image_sha256=result["image_sha256"],
                    )
                    for index, model in enumerate(result["models"]):
                        regions = {}
                        for row in model["observations"]:
                            key = row["region"]["id"]
                            resolution = (
                                "candidate"
                                if key in model["candidates"]
                                else "pruned"
                                if key in model.get("pruned", [])
                                else row.get("decision", "error")
                            )
                            regions[key] = {**row, "phase": "done", "resolution": resolution}
                        state["models"].append(
                            dict(
                                model=model["model"],
                                index=index,
                                status="completed",
                                regions=regions,
                                summary=model,
                                released=model.get("released"),
                            )
                        )
                if (folder / "review.json").exists():
                    state["review"] = json.loads((folder / "review.json").read_text())
                state.setdefault("review", {"target": None, "labels": {}})
            except (ValueError, OSError, KeyError, TypeError):
                raise DashboardError("This run could not be loaded.", 404) from None
            session = Session(folder, state)
            self.sessions[run_id] = session
            return session

    def history(self):
        rows = []
        for folder in self.root.iterdir():
            if folder.name.startswith(".") or not folder.is_dir():
                continue
            try:
                state = self.get(folder.name).snapshot()
                eligible = bool(state["models"]) and all(
                    str(m.get("released", "")).startswith("2026-") or m["model"] in self.catalog
                    for m in state["models"]
                )
                if not eligible:
                    continue
                rows.append(
                    {
                        k: state.get(k)
                        for k in ("id", "status", "source", "created_at", "config", "image")
                    }
                    | {"models": [m["model"] for m in state["models"]]}
                )
            except DashboardError:
                pass
        return sorted(rows, key=lambda r: r["created_at"], reverse=True)[:30]

    def sample_run(self):
        for row in self.history():
            session = self.get(row["id"])
            state = session.snapshot()
            if (
                state.get("source") != "replay"
                and state["status"] == "completed"
                and any(
                    r.get("phase") == "done" for m in state["models"] for r in m["regions"].values()
                )
            ):
                return session
        return None

    def start(self, payload, replay=False):
        config, models = validate_config(payload)
        with self.lock:
            if any(
                s.state["status"] in {"queued", "running", "stopping"}
                for s in self.sessions.values()
            ):
                raise DashboardError(
                    "An experiment is already running. Stop it or wait for it to finish.", 409
                )
            if not replay:
                self.models()
            source = self.sample_run() if replay else None
            if replay and source is None:
                raise DashboardError(
                    "No recorded 2026-model sample is available yet. Run a live search first.", 404
                )
            if source:
                original = source.snapshot()
                config = original["config"]
                models = [m["model"] for m in original["models"]]
                image_path = source.folder / "input.png"
            else:
                image_path = self.image(payload.get("image_id"))
                self.preview(payload)
                catalog = {m["id"]: m for m in self.models()}
                if any(m not in catalog for m in models):
                    raise DashboardError(
                        "Choose vision models released in 2026 from the current OpenRouter catalog."
                    )
                if config["structured"] and any(not catalog[m]["structured"] for m in models):
                    raise DashboardError(
                        "A selected model does not advertise structured output support."
                    )
            run_id = f"web-{uuid4().hex}"
            folder = self.root / run_id
            folder.mkdir()
            raw = image_path.read_bytes()
            with Image.open(BytesIO(raw)) as loaded:
                image = ImageOps.exif_transpose(loaded).convert("RGB")
                image.save(folder / "input.png")
            state = dict(
                id=run_id,
                seq=0,
                status="running",
                source="replay" if replay else "live",
                created_at=now(),
                config=config,
                image_sha256=hashlib.sha256(raw).hexdigest(),
                image={
                    "id": f"run:{run_id}",
                    "name": "Beach scene"
                    if payload.get("image_id") == "sample"
                    else "Search scene",
                    "width": image.width,
                    "height": image.height,
                    "url": f"/api/runs/{run_id}/files/input.png",
                },
                models=[
                    dict(
                        model=m,
                        index=i,
                        status="queued",
                        regions={},
                        released=original["models"][i].get("released")
                        if source
                        else datetime.fromtimestamp(self.catalog[m]["created"], UTC)
                        .date()
                        .isoformat(),
                    )
                    for i, m in enumerate(models)
                ],
                review={"target": None, "labels": {}},
            )
            session = Session(folder, state)
            self.sessions[run_id] = session
            save_json(folder / "session.json", state)
            worker = self._replay if replay else self._run
            threading.Thread(
                target=worker, args=(session, source) if replay else (session,), daemon=True
            ).start()
            return session.snapshot()

    def _run(self, session):
        provider = None
        try:
            args = type(
                "Settings",
                (),
                {**vars(self.args), **session.state["config"], "model_capabilities": self.catalog},
            )()
            provider = self.provider_factory(args)
            state = session.snapshot()
            result = dict(
                version=__version__,
                created_at=state["created_at"],
                image_sha256=state["image_sha256"],
                image_size=[state["image"]["width"], state["image"]["height"]],
                config=state["config"],
                prompt=PROMPT,
                models=[],
            )
            session.emit("run_started")
            with Image.open(session.folder / "input.png") as image:
                image.load()  # Decode once before crop workers share the immutable source.
                for index, model in enumerate(state["models"]):
                    if session.cancel.is_set():
                        break
                    session.emit("model_started", {"model_index": index})
                    folder = session.folder / f"model-{index:02d}"
                    folder.mkdir()
                    summary = search(
                        image,
                        model["model"],
                        provider,
                        state["config"],
                        folder,
                        on_event=lambda kind, value, i=index: session.emit(
                            kind, {**value, "model_index": i}
                        ),
                        cancel=session.cancel,
                    )
                    summary["artifact_dir"] = folder.name
                    result["models"].append(summary)
                    write_report(image, result, session.folder)
                    session.emit("model_finished", {"model_index": index, "summary": summary})
            session.emit(
                "run_finished", {"status": "cancelled" if session.cancel.is_set() else "completed"}
            )
        except Exception:
            session.emit(
                "run_error",
                {
                    "message": "Search could not finish. Check Infisical access and connectivity. Completed observations are preserved."
                },
            )
        finally:
            if provider:
                provider.close()

    def _replay(self, session, source):
        try:
            original = source.snapshot()
            session.emit("run_started")
            for index, model in enumerate(original["models"]):
                if session.cancel.is_set():
                    break
                session.emit("model_started", {"model_index": index})
                folder = session.folder / f"model-{index:02d}"
                folder.mkdir()
                source_folder = source.folder / f"model-{index:02d}"
                if (source_folder / "crops").is_dir():
                    shutil.copytree(source_folder / "crops", folder / "crops")
                for record in model["regions"].values():
                    if session.cancel.is_set():
                        break
                    context = dict(
                        model_index=index, region=record["region"], crop_box=record["crop_box"]
                    )
                    session.emit("region_queued", context)
                    session.emit("region_started", context | {"crop": record.get("crop")})
                    session.cancel.wait(0.6)  # Finish the displayed in-flight replay crop.
                    session.emit("region_finished", {"model_index": index, "observation": record})
                    session.emit(
                        "region_resolved",
                        {
                            "model_index": index,
                            "region_id": record["region"]["id"],
                            "resolution": record.get("resolution", "uncertain"),
                        },
                    )
                summary = model.get("summary", {})
                if session.cancel.is_set():
                    completed = [
                        r
                        for r in session.snapshot()["models"][index]["regions"].values()
                        if r.get("phase") == "done"
                    ]
                    summary = {
                        "model": model["model"],
                        "requests": len(completed),
                        "stop_reason": "cancelled",
                        "wall_seconds": 0,
                        "candidates": [
                            r["region"]["id"]
                            for r in completed
                            if r.get("resolution") == "candidate"
                        ],
                    }
                session.emit("model_finished", {"model_index": index, "summary": summary})
            session.emit(
                "run_finished", {"status": "cancelled" if session.cancel.is_set() else "completed"}
            )
        except Exception:
            session.emit("run_error", {"message": "The recorded sample could not be replayed."})

    def stop(self, run_id):
        session = self.get(run_id)
        with session.condition:
            if session.state["status"] not in TERMINAL:
                session.cancel.set()
                session.state["status"] = "stopping"
                session.emit("run_stopping")
        return session.snapshot()

    def review(self, run_id, payload):
        if not isinstance(payload, dict) or set(payload) - {"target", "label"} or not payload:
            raise DashboardError("Invalid review update.")
        session = self.get(run_id)
        with session.condition:
            review = json.loads(json.dumps(session.state["review"]))
            if "target" in payload:
                point = payload["target"]
                image = session.state["image"]
                if point is not None and (
                    not isinstance(point, list)
                    or len(point) != 2
                    or any(type(c) is not int for c in point)
                    or not 0 <= point[0] < image["width"]
                    or not 0 <= point[1] < image["height"]
                ):
                    raise DashboardError("Mark a point inside the image.")
                review["target"] = point
            if "label" in payload:
                label = payload["label"]
                if (
                    not isinstance(label, dict)
                    or set(label) != {"model_index", "region_id", "verdict"}
                    or type(label["model_index"]) is not int
                    or not 0 <= label["model_index"] < len(session.state["models"])
                    or label["verdict"] not in ("present", "absent", "unsure", "clear")
                ):
                    raise DashboardError("Invalid review label.")
                index, key = label["model_index"], label["region_id"]
                if not isinstance(key, str):
                    raise DashboardError("Invalid region.")
                record = session.state["models"][index]["regions"].get(key)
                if not record or record.get("phase") != "done":
                    raise DashboardError("Review a completed region.")
                label_id = f"{index}:{key}"
                if label["verdict"] == "clear":
                    review["labels"].pop(label_id, None)
                else:
                    review["labels"][label_id] = {"verdict": label["verdict"], "updated_at": now()}
            review.update(image_sha256=session.state["image_sha256"], updated_at=now(), version=1)
            save_json(session.folder / "review.json", review)
            session.state["review"] = review
            session.emit("review_updated", {"review": review})
        return review
