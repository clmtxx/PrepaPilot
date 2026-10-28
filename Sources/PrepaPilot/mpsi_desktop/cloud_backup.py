"""Selective, immutable Drive snapshots with record and attachment deduplication.

No account credential is part of this format. Restores are staged locally and
validated by the same canonical-schema checks as portable archives.
"""
from __future__ import annotations
from .i18n import tr

from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import sqlite3
import tempfile

from . import transfers
from . import achievements
from .subject_store import validate_subjects

CATEGORIES = {
    "documents": "Documents et fichiers de cours",
    "grades": "Notes et évaluations",
    "sleep": "Données de sommeil",
    "activities": "Travail, sport et autres activités",
    "timetable": "Emploi du temps et vacances",
    "memories": "Repères et archives personnelles",
    "preferences": "Profil et préférences",
}
FORMAT, VERSION = "prepapilot-drive", 1
OBJECT = "object-v1"
SNAPSHOT = "snapshot-v1"
FOLDER = "application/vnd.google-apps.folder"
COMMON = {"desktop_subjects", "school_year", "school_years", "school_year_start", achievements.SETTING}
TIMETABLE = {"desktop_timetable", "desktop_schedule_labels", "time_semester_transitions", "time_holidays"}
ACTIVITIES = {"desktop_focus_session"}
PREFERENCES = {"desktop_name", "desktop_program", "desktop_theme", "desktop_reduced_motion",
               "desktop_welcomed", "desktop_tutorial_version", "desktop_progression_targets",
               "desktop_progression_acknowledgements"}
TABLE_CATEGORIES = {"grades": "grades", "documents": "documents", "document_folders": "documents", "summaries": "documents",
                    "document_migrations": "documents", "memories": "memories", "tasks": "memories",
                    "time_day_templates": "timetable"}
HASH = re.compile(r"[a-f0-9]{64}")
MD5 = re.compile(r"[a-f0-9]{32}")


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def _decode(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError(tr('La sauvegarde contient des champs dupliqués.'))
            result[key] = value
        return result
    try:
        return json.loads(raw, object_pairs_hook=pairs,
                          parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
    except (ValueError, TypeError, UnicodeError, RecursionError) as exc:
        raise ValueError(tr('Le contenu de la sauvegarde est invalide.')) from exc


def _selection(value):
    if not isinstance(value, (list, tuple, set, frozenset)) or not value or any(not isinstance(key, str) or key not in CATEGORIES for key in value):
        raise ValueError(tr('Choisis au moins une catégorie à sauvegarder.'))
    return sorted(set(value))


def _check_cancel(cancel):
    if cancel is not None and cancel.is_set():
        raise ValueError(tr('Sauvegarde ou restauration annulée.'))


def _report(progress, message):
    if progress:
        progress(message)


def _settings(selection):
    return (COMMON | (TIMETABLE if "timetable" in selection else set())
            | (PREFERENCES if "preferences" in selection else set())
            | (ACTIVITIES if "activities" in selection else set()))


def _selected(table, row, selection):
    if table == "settings":
        return row["key"] in _settings(selection)
    if table == "time_entries":
        return ("sleep" if row["category"] == "sommeil" else "activities") in selection
    return TABLE_CATEGORIES.get(table) in selection


def _hashes(path):
    sha, md5, size = hashlib.sha256(), hashlib.md5(), 0
    with Path(path).open("rb") as source:
        for block in iter(lambda: source.read(transfers.BLOCK), b""):
            sha.update(block)
            md5.update(block)
            size += len(block)
    return sha.hexdigest(), md5.hexdigest(), size


def _folder(client, identity):
    value = client.get_file(identity)
    if value.get("mimeType") != FOLDER or value.get("trashed") or value.get("appProperties", {}).get("prepapilot") != "backup-v1":
        raise ValueError(tr('Choisis un dossier de sauvegarde PrépaPilot accessible sur Google Drive.'))


def _snapshot_summary(item):
    properties = item.get("appProperties", {})
    if properties.get("prepapilot") != SNAPSHOT or item.get("mimeType") == FOLDER:
        return None
    try:
        created = properties["created_at"]
        datetime.fromisoformat(created)
        selection = _selection(properties["categories"].split(","))
        counts = {key: int(properties.get("count_" + key, "0")) for key in selection}
        if any(not 0 <= value <= transfers.MAX_FILES for value in counts.values()):
            raise ValueError
        return {"id": item["id"], "created_at": created, "categories": selection, "counts": counts}
    except (KeyError, TypeError, ValueError):
        return None


def list_snapshots(client, folder_id):
    _folder(client, folder_id)
    values = [_snapshot_summary(item) for item in client.list_children(folder_id)]
    return sorted((value for value in values if value), key=lambda value: value["created_at"], reverse=True)


def _content(manifest):
    return {key: manifest[key] for key in ("selection", "records", "files")}


def _manifest(client, folder_id, snapshot_id, temporary):
    item = client.get_file(snapshot_id)
    summary = _snapshot_summary(item)
    if folder_id not in item.get("parents", []) or not summary:
        raise ValueError(tr('Cette sauvegarde n’appartient pas au dossier sélectionné.'))
    path = temporary / "manifest.json"
    client.download_file(snapshot_id, path, transfers.MAX_MANIFEST)
    if path.stat().st_size > transfers.MAX_MANIFEST:
        raise ValueError(tr('La sauvegarde dépasse la taille autorisée.'))
    value = _decode(path.read_bytes())
    if not isinstance(value, dict) or value.get("format") != FORMAT or type(value.get("version")) is not int or value["version"] != VERSION:
        raise ValueError(tr('Cette version de sauvegarde Google Drive n’est pas prise en charge.'))
    selection = _selection(value.get("selection"))
    if selection != value["selection"] or not isinstance(value.get("records"), dict) or not isinstance(value.get("files"), dict) or not isinstance(value.get("objects"), dict):
        raise ValueError(tr('Le manifeste de sauvegarde est invalide.'))
    try:
        datetime.fromisoformat(value["created_at"])
    except (KeyError, TypeError, ValueError):
        raise ValueError(tr('La date de sauvegarde est invalide.')) from None
    counts = value.get("counts")
    if not isinstance(counts, dict) or set(counts) != set(selection) or any(type(count) is not int or not 0 <= count <= transfers.MAX_FILES for count in counts.values()):
        raise ValueError(tr('Le décompte des données sauvegardées est invalide.'))
    if summary["categories"] != selection or summary["created_at"] != value["created_at"] or summary["counts"] != counts:
        raise ValueError(tr('Les informations de la sauvegarde sont incohérentes.'))
    if any(table not in {*TABLE_CATEGORIES, "settings", "time_entries"} for table in value["records"]):
        raise ValueError(tr('La sauvegarde contient une catégorie de données inconnue.'))
    references = set()
    record_count = 0
    for hashes in value["records"].values():
        if not isinstance(hashes, list) or any(not isinstance(key, str) or not HASH.fullmatch(key) for key in hashes) or len(hashes) != len(set(hashes)):
            raise ValueError(tr('La liste des données sauvegardées est invalide.'))
        references.update(hashes)
        record_count += len(hashes)
    paths = set()
    for relative, spec in value["files"].items():
        parsed = transfers._safe_name(relative)
        if relative.casefold() in paths or len(parsed.parts) != 2 or parsed.parts[0] != "documents" or not isinstance(spec, dict) or not isinstance(spec.get("hash"), str) or not HASH.fullmatch(spec["hash"]):
            raise ValueError(tr('Un document sauvegardé est invalide.'))
        paths.add(relative.casefold())
        references.add(spec["hash"])
    if len(references) > transfers.MAX_FILES or record_count + len(paths) > transfers.MAX_FILES or references != set(value["objects"]):
        raise ValueError(tr('La sauvegarde est incomplète ou contient trop de données.'))
    total = 0
    identities = set()
    for key, spec in value["objects"].items():
        if not isinstance(spec, dict) or not isinstance(spec.get("id"), str) or not spec["id"] or spec["id"] in identities or type(spec.get("size")) is not int or not 0 <= spec["size"] <= transfers.MAX_FILE or not isinstance(spec.get("md5"), str) or not MD5.fullmatch(spec["md5"]):
            raise ValueError(tr('Une référence de sauvegarde est invalide.'))
        total += spec["size"]
        identities.add(spec["id"])
    expanded = sum(value["objects"][spec["hash"]]["size"] for spec in value["files"].values())
    expanded += sum(value["objects"][digest]["size"] for hashes in value["records"].values() for digest in hashes)
    if max(total, expanded) > transfers.MAX_TOTAL:
        raise ValueError(tr('La sauvegarde dépasse la limite de 2 Go.'))
    if hashlib.sha256(_json(_content(value))).hexdigest() != value.get("fingerprint") or item.get("appProperties", {}).get("fingerprint") != value.get("fingerprint"):
        raise ValueError(tr('Le manifeste de sauvegarde a été modifié.'))
    return value


def backup_to_drive(ctx, client, folder_id, selection, progress=None, cancel=None):
    selection = _selection(selection)
    _check_cancel(cancel)
    _folder(client, folder_id)
    with tempfile.TemporaryDirectory(prefix="prepapilot-drive-export-") as directory:
        temporary = Path(directory)
        database = temporary / "data.sqlite3"
        files, records, objects, counts = {}, {}, {}, {key: 0 for key in selection}
        expanded_size = 0
        _report(progress, tr('Préparation des données sélectionnées…'))
        with ctx.db._lock:
            achievements.reconcile(ctx.db)
            transfers._snapshot(Path(ctx.data_dir) / "mpsi.sqlite3", database)
            with closing(sqlite3.connect(database)) as connection:
                connection.row_factory = sqlite3.Row
                for table in transfers._schema(connection):
                    _check_cancel(cancel)
                    for raw in connection.execute(f'SELECT * FROM "{table}" ORDER BY 1'):
                        row = dict(raw)
                        if not _selected(table, row, selection):
                            continue
                        payload = _json({"table": table, "values": row})
                        if len(payload) > transfers.MAX_DATABASE:
                            raise ValueError(tr('Un enregistrement dépasse la limite de taille.'))
                        expanded_size += len(payload)
                        digest = hashlib.sha256(payload).hexdigest()
                        path = temporary / digest
                        path.write_bytes(payload)
                        objects[digest] = {"path": path, "size": len(payload), "md5": hashlib.md5(payload).hexdigest()}
                        records.setdefault(table, []).append(digest)
                        group = "sleep" if table == "time_entries" and row["category"] == "sommeil" else "activities" if table == "time_entries" else TABLE_CATEGORIES.get(table)
                        if group in counts and table not in {"summaries", "document_migrations", "document_folders"}:
                            counts[group] += 1
                        if table == "documents":
                            relative = row["stored_path"]
                            parsed = transfers._safe_name(relative)
                            if len(parsed.parts) != 2 or parsed.parts[0] != "documents":
                                raise ValueError(tr('Le chemin d’un document est invalide.'))
                            source = Path(ctx.data_dir).joinpath(*parsed.parts)
                            if source.is_symlink() or source.parent.is_symlink() or not source.is_file():
                                raise ValueError(tr('Un document est absent ou est un lien externe.'))
                            copy = temporary / ("document-" + str(row["id"]))
                            shutil.copyfile(source, copy)
                            file_hash, md5, size = _hashes(copy)
                            if size != row["size_bytes"]:
                                raise ValueError(tr('Un document est incomplet. Vérifie son fichier avant de sauvegarder.'))
                            files[relative] = {"hash": file_hash}
                            expanded_size += size
                            objects.setdefault(file_hash, {"path": copy, "size": size, "md5": md5})
        if sum(len(values) for values in records.values()) + len(files) > transfers.MAX_FILES or expanded_size > transfers.MAX_TOTAL or any(spec["size"] > transfers.MAX_FILE for spec in objects.values()):
            raise ValueError(tr('La sauvegarde dépasse 2 Go, 10 000 éléments ou 512 Mo par fichier.'))
        for hashes in records.values():
            hashes.sort()
        created = datetime.now(timezone.utc).isoformat()
        manifest = {"format": FORMAT, "version": VERSION, "created_at": created,
                    "selection": selection, "records": records, "files": files, "objects": {}, "counts": counts}
        manifest["fingerprint"] = hashlib.sha256(_json(_content(manifest))).hexdigest()
        children = client.list_children(folder_id)
        indexed = {}
        for child in children:
            indexed.setdefault(child.get("name"), []).append(child)
        uploaded = reused = 0
        for index, (digest, spec) in enumerate(objects.items(), 1):
            _check_cancel(cancel)
            _report(progress, tr('Vérification et sauvegarde : {v0} / {v1}', v0=index, v1=len(objects)))
            previous = next((item for item in indexed.get(digest, [])
                             if item.get("mimeType") != FOLDER and item.get("appProperties", {}).get("prepapilot") == OBJECT
                             and str(item.get("size")) == str(spec["size"]) and item.get("md5Checksum") == spec["md5"]), None)
            if previous:
                uploaded_item = previous
                reused += 1
            else:
                uploaded_item = client.upload_file(folder_id, digest, spec["path"], properties={"prepapilot": OBJECT})
                if str(uploaded_item.get("size")) != str(spec["size"]) or uploaded_item.get("md5Checksum") != spec["md5"]:
                    raise ValueError(tr('Google Drive n’a pas confirmé l’intégrité d’un fichier envoyé.'))
                uploaded += 1
            manifest["objects"][digest] = {"id": uploaded_item["id"], "size": spec["size"], "md5": spec["md5"]}
        # A retry can reuse successfully uploaded objects from an interrupted run.
        # Publish the snapshot only after every referenced object is confirmed.
        for child in children:
            if child.get("appProperties", {}).get("fingerprint") == manifest["fingerprint"] and _snapshot_summary(child):
                previous = _manifest(client, folder_id, child["id"], temporary)
                if _content(previous) == _content(manifest) and previous["objects"] == manifest["objects"]:
                    return {"uploaded": uploaded, "reused": reused, "changed": False,
                            "snapshot_id": child["id"], "created_at": previous["created_at"], "verified_at": created}
        _check_cancel(cancel)
        payload = _json(manifest)
        if len(payload) > transfers.MAX_MANIFEST:
            raise ValueError(tr('La sauvegarde contient trop de références.'))
        target = temporary / "snapshot.json"
        target.write_bytes(payload)
        properties = {"prepapilot": SNAPSHOT, "created_at": created, "categories": ",".join(selection),
                      "fingerprint": manifest["fingerprint"], **{"count_" + key: str(value) for key, value in counts.items()}}
        result = client.upload_file(folder_id, f"sauvegarde-{created.replace(':', '-')}.json", target,
                                    mime_type="application/json", properties=properties)
        if result.get("md5Checksum") != hashlib.md5(payload).hexdigest():
            raise ValueError(tr('Google Drive n’a pas confirmé le manifeste de sauvegarde.'))
        return {"uploaded": uploaded, "reused": reused, "changed": True,
                "snapshot_id": result["id"], "created_at": created, "verified_at": created}


def _subject_merge(local, incoming):
    """Keep local labels; assign stable imported IDs for genuinely different subjects."""
    local, incoming = validate_subjects(local), validate_subjects(incoming)
    merged = list(local)
    identities = {row["id"]: row for row in merged}
    names = {row["name"].casefold() for row in merged}
    remap = {}
    for row in incoming:
        original = row["id"]
        existing = identities.get(original)
        if existing and existing["name"].casefold() == row["name"].casefold():
            remap[original] = original
            continue
        identity = original if not existing else "subject_" + hashlib.sha256(_json(row)).hexdigest()[:32]
        if identity in identities:
            remap[original] = identity
            continue
        name, suffix = row["name"], 1
        while name.casefold() in names:
            tail = " (import)" if suffix == 1 else f" (import {suffix})"
            name = row["name"][:60-len(tail)] + tail
            suffix += 1
        item = {**row, "id": identity, "name": name}
        merged.append(item)
        identities[identity] = item
        names.add(name.casefold())
        remap[original] = identity
    return validate_subjects(merged), remap


def _remap_slots(slots, remap):
    return [{**slot, "category": remap.get(slot["category"], slot["category"])} for slot in slots]


def _prepare_merge(ctx, folder, rows, selection):
    source = folder / "data.sqlite3"
    with closing(sqlite3.connect(source)) as connection, connection:
        connection.row_factory = sqlite3.Row
        expected = transfers._schema(connection)
        for table, values in rows.items():
            if table == "documents":
                legacy = set(expected["documents"]) - {"folder_id"}
                for row in values:
                    if set(row) == legacy:
                        row["folder_id"] = None
            if table == "grades":
                # Older snapshots have exactly the historical fields. Missing
                # comparisons mean unknown, never zero or an invented rank.
                legacy = set(expected["grades"]) - set(transfers.GRADE_COMPARISON_COLUMNS)
                for row in values:
                    if set(row) == legacy:
                        row.update(dict.fromkeys(transfers.GRADE_COMPARISON_COLUMNS))
            if table not in expected or any(set(row) != set(expected[table]) for row in values):
                raise ValueError(tr('La structure des données sauvegardées est incompatible.'))
            if any(not _selected(table, row, selection) for row in values):
                raise ValueError(tr('La sauvegarde contient des données non sélectionnées.'))
            if table == "grades":
                for row in values:
                    transfers._check_grade_comparison(row["scale"], row["class_average"], row["rank"], row["class_size"])
        if "documents" in selection:
            transfers._validate_document_folders(rows.get("document_folders", []), rows.get("documents", []))
        incoming = {row["key"]: _decode(row["value"]) for row in rows.get("settings", [])}
        if "desktop_subjects" not in incoming:
            raise ValueError(tr('Le catalogue des matières manque dans la sauvegarde.'))
        local = {row["key"]: _decode(row["value"]) for row in connection.execute("SELECT * FROM settings")}
        if achievements.SETTING in incoming:
            # Trophies are permanent, even when only a subset of the journal is
            # restored. A second import must never duplicate a reward or its XP.
            saved = achievements.validate_state(incoming[achievements.SETTING])
            current = achievements.validate_state(local.get(achievements.SETTING, {"version": 1, "awards": {}}))
            awards = dict(current["awards"])
            for identity, earned in saved["awards"].items():
                previous = awards.get(identity)
                if previous is None or earned["earned_at"] < previous["earned_at"]:
                    awards[identity] = earned
            incoming[achievements.SETTING] = achievements.validate_state({"version": 1, "awards": awards})
        if set(selection) == set(CATEGORIES):
            subjects = validate_subjects(incoming["desktop_subjects"])
            remap = {row["id"]: row["id"] for row in subjects}
        else:
            subjects, remap = _subject_merge(local["desktop_subjects"], incoming["desktop_subjects"])
        for table, group in TABLE_CATEGORIES.items():
            if group in selection:
                connection.execute(f'DELETE FROM "{table}"')
        if "sleep" in selection:
            connection.execute("DELETE FROM time_entries WHERE category='sommeil'")
        if "activities" in selection:
            connection.execute("DELETE FROM time_entries WHERE category!='sommeil'")
        if "timetable" in selection:
            # The remaining activities belong to excluded categories. Retain
            # their future lessons even when ensure_day sees the restored plan.
            connection.execute("UPDATE time_entries SET manual_override=1 WHERE source='timetable' AND end_at>?",
                               (datetime.now().isoformat(timespec="minutes"),))
        for group, keys in (("preferences", PREFERENCES), ("timetable", TIMETABLE), ("activities", ACTIVITIES)):
            if group in selection:
                connection.executemany("DELETE FROM settings WHERE key=?", [(key,) for key in keys])
        entry_remap = {}
        for table, values in rows.items():
            if table == "settings":
                continue
            for original in values:
                row = dict(original)
                for key in ("subject", "category"):
                    if key in row:
                        row[key] = remap.get(row[key], row[key])
                if table == "time_day_templates":
                    row["slots_json"] = _json(_remap_slots(_decode(row["slots_json"]), remap)).decode("utf-8")
                if table == "time_entries":
                    if connection.execute("SELECT 1 FROM time_entries WHERE id=?", (row["id"],)).fetchone():
                        row["id"] = connection.execute("SELECT coalesce(max(id),0)+1 FROM time_entries").fetchone()[0]
                    entry_remap[original["id"]] = row["id"]
                    if row["template_key"] and connection.execute("SELECT 1 FROM time_entries WHERE template_key=?", (row["template_key"],)).fetchone():
                        row.update(template_key=None, source="manual", manual_override=1)
                    elif "timetable" not in selection and row["source"] == "timetable":
                        row["manual_override"] = 1
                columns = expected[table]
                names = ",".join(f'"{key}"' for key in columns)
                connection.execute(f'INSERT INTO "{table}" ({names}) VALUES ({",".join("?" for _ in columns)})',
                                   [row[key] for key in columns])
        if "desktop_timetable" in incoming:
            timetable = incoming["desktop_timetable"]
            if not isinstance(timetable, dict) or not isinstance(timetable.get("semesters"), dict):
                raise ValueError(tr('L’emploi du temps sauvegardé est invalide.'))
            incoming["desktop_timetable"] = {**timetable, "semesters": {key: _remap_slots(slots, remap) for key, slots in timetable["semesters"].items()}}
        if "desktop_focus_session" in incoming:
            from .focus_session import validate_focus_session
            draft = validate_focus_session(incoming["desktop_focus_session"],
                                           categories={"permanence", *(row["id"] for row in validate_subjects(incoming["desktop_subjects"]))})
            if draft is not None:
                draft = {**draft, "category": remap.get(draft["category"], draft["category"]),
                         "entry_ids": [entry_remap.get(identity, identity) for identity in draft["entry_ids"]]}
            incoming["desktop_focus_session"] = draft
        incoming["desktop_subjects"] = subjects
        # Keep the years that still own data in categories excluded from restore.
        incoming["school_years"] = sorted(set(local.get("school_years", [])) | set(incoming.get("school_years", [])))
        if "timetable" in selection and "desktop_timetable" not in incoming:
            raise ValueError(tr('L’emploi du temps manque dans la sauvegarde.'))
        incoming["setup_completed"] = True
        for key, value in incoming.items():
            connection.execute("INSERT OR REPLACE INTO settings(key,value) VALUES (?,?)", (key, _json(value).decode("utf-8")))


def prepare_drive_restore(ctx, client, folder_id, snapshot_id, progress=None, cancel=None):
    _check_cancel(cancel)
    _folder(client, folder_id)
    temporary = tempfile.TemporaryDirectory(prefix="prepapilot-drive-restore-")
    folder = Path(temporary.name)
    try:
        manifest = _manifest(client, folder_id, snapshot_id, folder)
        selection = manifest["selection"]
        downloaded, rows = {}, {}
        for index, (digest, spec) in enumerate(manifest["objects"].items(), 1):
            _check_cancel(cancel)
            _report(progress, tr('Récupération et vérification : {v0} / {v1}', v0=index, v1=len(manifest['objects'])))
            metadata = client.get_file(spec["id"])
            if folder_id not in metadata.get("parents", []) or metadata.get("name") != digest or metadata.get("appProperties", {}).get("prepapilot") != OBJECT or str(metadata.get("size")) != str(spec["size"]) or metadata.get("md5Checksum") != spec["md5"]:
                raise ValueError(tr('Un élément de la sauvegarde manque ou a été modifié sur Google Drive.'))
            path = folder / digest
            client.download_file(spec["id"], path, spec["size"])
            sha, md5, size = _hashes(path)
            if (sha, md5, size) != (digest, spec["md5"], spec["size"]):
                raise ValueError(tr('Un élément de la sauvegarde est incomplet ou corrompu.'))
            downloaded[digest] = path
        for table, hashes in manifest["records"].items():
            values = []
            keys = set()
            for digest in hashes:
                path = downloaded[digest]
                if path.stat().st_size > transfers.MAX_DATABASE:
                    raise ValueError(tr('Un enregistrement de sauvegarde est trop volumineux.'))
                record = _decode(path.read_bytes())
                if not isinstance(record, dict) or set(record) != {"table", "values"} or record["table"] != table or not isinstance(record["values"], dict):
                    raise ValueError(tr('Un enregistrement de sauvegarde est invalide.'))
                row = record["values"]
                identity = row.get("key") if table in {"settings", "memories"} else row.get("day") if table == "time_day_templates" else row.get("summary_id") if table == "document_migrations" else row.get("id")
                if not isinstance(identity, (str, int)) or isinstance(identity, bool) or identity in keys:
                    raise ValueError(tr('Une donnée de sauvegarde est présente plusieurs fois.'))
                keys.add(identity)
                values.append(row)
            rows[table] = values
        actual_counts = {key: 0 for key in selection}
        for table, values in rows.items():
            for row in values:
                group = "sleep" if table == "time_entries" and row.get("category") == "sommeil" else "activities" if table == "time_entries" else TABLE_CATEGORIES.get(table)
                if group in actual_counts and table not in {"summaries", "document_migrations", "document_folders"}:
                    actual_counts[group] += 1
        if actual_counts != manifest["counts"]:
            raise ValueError(tr('Le décompte des données sauvegardées est incohérent.'))
        document_paths = {row.get("stored_path") for row in rows.get("documents", [])}
        if document_paths != set(manifest["files"]) or ("documents" not in selection and manifest["files"]):
            raise ValueError(tr('La liste des documents de la sauvegarde est incohérente.'))
        _check_cancel(cancel)
        _report(progress, tr('Préparation de la restauration, sans modifier tes données…'))
        with ctx.db._lock:
            transfers._snapshot(Path(ctx.data_dir) / "mpsi.sqlite3", folder / "data.sqlite3")
            revision = (ctx.db, ctx.db._connection.total_changes)
            if "documents" not in selection:
                for relative, path in transfers._document_files(ctx.data_dir):
                    target = folder / relative
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(path, target)
        for relative, spec in manifest["files"].items():
            target = folder / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(downloaded[spec["hash"]], target)
        _prepare_merge(ctx, folder, rows, selection)
        _check_cancel(cancel)
        validated = folder / "validated.sqlite3"
        counts = transfers._canonical_database(folder / "data.sqlite3", validated, type(ctx.db), folder)
        validated.replace(folder / "data.sqlite3")
        signatures = transfers._signatures(folder)
        if len(signatures) > transfers.MAX_FILES or signatures["data.sqlite3"]["size"] > transfers.MAX_DATABASE or sum(item["size"] for item in signatures.values()) > transfers.MAX_TOTAL:
            raise ValueError(tr('Les données à restaurer dépassent la taille autorisée.'))
        plan = transfers.ImportPlan(temporary, folder, counts, manifest["created_at"], signatures)
        plan.cloud_selection = selection
        plan.cloud_counts = manifest.get("counts", {})
        plan.cloud_revision = revision
        plan.cloud_preserved_documents = ({key: value for key, value in signatures.items() if key != 'data.sqlite3'}
                                          if 'documents' not in selection else None)
        return plan
    except (sqlite3.Error, KeyError, TypeError, RecursionError, OverflowError) as exc:
        temporary.cleanup()
        raise ValueError(tr('Les données de la sauvegarde sont invalides ou incompatibles avec les données conservées sur ce PC.')) from exc
    except BaseException:
        temporary.cleanup()
        raise


def validate_restore_target(ctx, plan):
    """Call on the UI thread immediately before applying the confirmed plan."""
    with ctx.db._lock:
        if plan.closed or getattr(plan, "cloud_revision", None) != (ctx.db, ctx.db._connection.total_changes):
            draft = ctx.db.get_setting("desktop_focus_session")
            advice = tr(' Mets la séance de travail en pause avant de réessayer.') if isinstance(draft, dict) and draft.get("status") == "running" else ""
            raise ValueError(tr('Tes données ont changé pendant la préparation. Recharge cette sauvegarde avant de l’importer.') + advice)
        preserved = getattr(plan, 'cloud_preserved_documents', None)
        if preserved is not None:
            current = {name: {'size': path.stat().st_size, 'sha256': transfers._digest(path)}
                       for name, path in transfers._document_files(ctx.data_dir)}
            if current != preserved:
                raise ValueError(tr('Un document conservé a changé pendant la préparation. Recharge cette sauvegarde avant de l’importer.'))
