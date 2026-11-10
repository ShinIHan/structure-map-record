#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 ShinIHan
#
# Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation
# files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy,
# modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software
# is furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES
# OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE
# LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR
# IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
"""verify_record.py — independent verifier for the structure-map forward record (stdlib only, no network).

Usage (from a clone of the public repository):
    python verify_record.py                      # working tree: file hashes vs manifest, frozen docs vs sidecars
    python verify_record.py --history            # walk the whole git history: hash chain, append-only, meta write-once,
                                                 #   column evolution, anchors immutable, sidecars append-only
    python verify_record.py --find-row wave_log 1023   # first commit (and anchor) that contains a given row
Exit code 0 = everything verified, 1 = a check failed (the first failing check is printed), 2 = usage / git error.

Record contract (see README.md):
  * data/forward/wave_log_YYYY-MM.jsonl and chart_log_YYYY-MM.jsonl: one file per UTC calendar month of the rows' logged_at;
    data/forward/wave_log_quarantine.jsonl: one file. One JSON object per row, keys in manifest.columns[table] order, UTF-8,
    LF only; inside a file rows are ordered by their key (id / wave_id). JSONL is split on b"\\n" only (never str.splitlines()).
  * data/forward/manifest.json: schema 1; manifest.files lists every data file (sha256, bytes, rows) and nothing else belongs to
    the record; prev_manifest_sha256 = sha256 of the previous manifest.json (null for the first snapshot) -> hash chain over the
    whole history.
  * Every line is canonical: exactly json.dumps(row, ensure_ascii=False, separators=(",", ":"), allow_nan=False) of its parsed row, so one row has one
    byte form (a duplicate JSON key, which readers resolve differently, is refused). meta.json and manifest.json likewise: exactly
    json.dumps(obj, ensure_ascii=False, indent=1 (meta) or 2 (manifest), sort_keys=True, allow_nan=False) + LF.
  * A sidecar's first line reads exactly '<64 lowercase hex digits>  docs/<the sidecar's own name>.md'.
  * Append-only: every row of an earlier snapshot must exist unchanged (cell by cell, projected onto the earlier snapshot's
    column list) in every later snapshot; wave_log/chart_log ids are AUTOINCREMENT so new ids must exceed the previous max_id
    (gaps are normal: INSERT OR IGNORE bumps the sequence); meta keys are write-once; appended columns are allowed (reported),
    removed/renamed columns or tables are a failure. A new table needs a new version of this file.
  * One row per key: the key column (id / wave_id) is the PRIMARY KEY of every row table, also of wave_log_quarantine and across
    monthly files, so a snapshot must list every key once and each file must list its keys in increasing order.
  * data/forward/anchors/<generated_at>.manifest.json is a byte copy of the published manifest with that generated_at_utc; its .ots is the
    OpenTimestamps proof (the only files that legitimately change: upgrades). An anchor (a file of exactly that name form) and a sidecar never
    leave the tree once they are in it, and an anchor manifest's bytes never change (a wrong file mode is a stray entry and can be repaired).
  * Nothing else lives under data/forward at the tip: every direct child is a record file or anchors/, every entry is a regular file (mode 100644).
    One new commit repairs it: remove a file that is not part of the record; an entry that is part of it (a record file the manifest lists, an
    anchor) is never removed but restored as a regular file with the same bytes (mode 100644), and a link or gitlink at an anchor .ots gets a
    regular file back. A gitlink at a record file, or an anchor manifest whose bytes changed (a gitlink there with other bytes included), is a
    failure no commit repairs. In the middle of the history it changed no row and is reported as a warning. In a working tree, files your own system writes
    there (.DS_Store, desktop.ini) are only reported. An anchor-named .ots without its manifest is legal and, like every anchor, permanent.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from collections import OrderedDict
from datetime import datetime, timedelta, timezone

MANIFEST = "manifest.json"
REQUIRED_FILES = ("wave_log_quarantine.jsonl", "meta.json", "schema.sql")
SINGLE_ROW_FILES = {"wave_log_quarantine.jsonl": "wave_log_quarantine"}
ROW_TABLE_KEYS = {"wave_log": "id", "chart_log": "id", "wave_log_quarantine": "wave_id"}
PARTITIONED_TABLES = ("wave_log", "chart_log")  # one file per UTC calendar month of logged_at
PARTITION_RE = re.compile(r"(wave_log|chart_log)_([0-9]{4}-(?:0[1-9]|1[0-2]))\.jsonl")
ANCHOR_RE = re.compile(r"([0-9]{8}T[0-9]{6}Z)\.manifest\.json(\.ots)?")
ID_TABLES = PARTITIONED_TABLES                  # AUTOINCREMENT: new ids must exceed the previous max_id
LATE_THRESHOLD_S = 300
DATA_DIR = "data/forward"
ANCHOR_DIR = DATA_DIR + "/anchors"
FROZEN_SIDECARS = ("docs/structure_wave_forward_prereg.sha256", "docs/structure_chart_forward_prereg.sha256")
SIDECAR_LINE_RE = re.compile(rb"([0-9a-f]{64})  (.+)")
_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


class RecordError(Exception):
    """A record-integrity check failed (the message names table / key / file)."""


class StrayAtTip(RecordError):
    """A file that is not part of the record, or a non-regular entry, under data/forward at the tip. Unlike every other failure one new commit
    repairs it: removing a file that is not part of the record, or restoring as a regular file an entry that is - an anchor or a record file
    the manifest lists - which must never be removed (R11-REC-01, R12-REC-01: removing it breaks the history for good). The same bytes are kept
    (update-index --cacheinfo 100644,<blob>,<path>), except for a link or gitlink at an anchor .ots, which holds no proof: the real file goes
    back there (R12-REC-02). In the middle of the history it is only a warning."""

    def __init__(self, path: str, anchor: bool, permanent: bool = None, mode: str = "", oid: str = ""):
        self.path, self.anchor, self.mode, self.oid = path, anchor, mode, oid
        self.permanent = anchor if permanent is None else permanent
        if not self.permanent:
            repair = "remove it in a new commit, it is not part of the record"
        elif path.endswith(".ots") and mode in ("160000", "120000"):
            repair = ("put a regular file back there (mode 100644) in a new commit - the proof it held earlier, or a new one; it is part of the "
                      "record and removing it breaks the history for good, and a link or gitlink holds no proof")
        else:
            repair = (f"restore mode 100644 with the same bytes in a new commit (git update-index --cacheinfo 100644,{oid or '<blob id>'},{path}) - "
                      "it is part of the record and removing it breaks the history for good, do not remove it")
        super().__init__(f"{path} does not belong to the record (at the tip: {repair}; in the middle of the history it is only a warning)")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canon(value) -> str:
    """Canonical JSON of one cell (type-faithful: 1 and 1.0 differ, as they do in SQLite)."""
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def canon_document(obj, indent: int) -> bytes:
    """The one byte form of meta.json (indent 1) and manifest.json (indent 2), exactly what the exporter writes. A duplicate key, another number
    spelling or another layout is another byte string, so a first-wins and a last-wins JSON reader can never be shown different values."""
    return json.dumps(obj, ensure_ascii=False, indent=indent, sort_keys=True, allow_nan=False).encode("utf-8") + b"\n"


def parse_iso(s: str) -> int:
    return int(datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).timestamp())


def month_of(epoch: int) -> str:
    """UTC calendar month of a Unix time, 'YYYY-MM' (timedelta instead of fromtimestamp: Windows refuses negative times)."""
    d = _EPOCH + timedelta(seconds=epoch)
    return f"{d.year:04d}-{d.month:02d}"


def partition_file(table: str, logged_at: int) -> str:
    """The file a row of a partitioned table belongs to."""
    return f"{table}_{month_of(logged_at)}.jsonl"


def row_file(name: str):
    """(table, key, month) of a row file name, month None for a single-file table; None for any other name."""
    m = PARTITION_RE.fullmatch(name)
    if m:
        return m.group(1), ROW_TABLE_KEYS[m.group(1)], m.group(2)
    if name in SINGLE_ROW_FILES:
        table = SINGLE_ROW_FILES[name]
        return table, ROW_TABLE_KEYS[table], None
    return None


def is_record_file(name: str) -> bool:
    """A file name that belongs directly under data/forward (the anchors/ sub-directory is separate)."""
    return name == MANIFEST or name in REQUIRED_FILES or row_file(name) is not None


def parse_jsonl(data: bytes, name: str) -> list:
    """Split on LF only. U+2028/U+2029 may appear raw inside JSON strings (ensure_ascii=False) and must not split rows."""
    if not data:
        return []
    if b"\r" in data:
        raise RecordError(f"{name}: CR byte found (CRLF conversion? clone with -c core.autocrlf=false)")
    if not data.endswith(b"\n"):
        raise RecordError(f"{name}: missing trailing LF")
    rows = []
    for i, line in enumerate(data.split(b"\n")[:-1], 1):
        if not line:
            raise RecordError(f"{name}: empty line {i}")
        try:
            rows.append(json.loads(line.decode("utf-8"), object_pairs_hook=OrderedDict))
        except (UnicodeDecodeError, ValueError, RecursionError) as e:
            raise RecordError(f"{name}: line {i} is not valid UTF-8 JSON: {e}") from None
    return rows


def parse_row_file(fname: str, data: bytes, cols: list, key: str, month) -> tuple:
    """One row file -> (rows, keys). Keys in column order, integer keys in increasing order, every row in the right month."""
    rows = parse_jsonl(data, fname)
    for n, (r, line) in enumerate(zip(rows, data.split(b"\n")), 1):
        if not isinstance(r, dict) or list(r.keys()) != cols:
            raise RecordError(f"{fname}: line {n} keys differ from manifest.columns")
        try:
            canonical = canon(r).encode("utf-8")
        except (ValueError, RecursionError):                                   # NaN, Infinity, a lone surrogate, hostile nesting
            canonical = None
        if canonical != line:
            raise RecordError(f"{fname}: line {n} is not in canonical form (a duplicate key, another number spelling, extra spaces)")
    keys = [r[key] for r in rows]
    if any(not isinstance(k, int) or isinstance(k, bool) for k in keys):
        raise RecordError(f"{fname}: non-integer {key}")
    if any(b <= a for a, b in zip(keys, keys[1:])):
        raise RecordError(f"{fname}: {key} values not strictly increasing (duplicate or unordered {key})")
    if month is not None:
        for r in rows:
            at = r.get("logged_at")
            if not isinstance(at, int) or isinstance(at, bool):
                raise RecordError(f"{fname}: {key}={r[key]} has no integer logged_at")
            try:
                inside = month_of(at) == month
            except OverflowError:
                inside = False
            if not inside:
                raise RecordError(f"{fname}: {key}={r[key]} logged_at {at} is outside {month}")
    return rows, keys


def load_snapshot(files: dict, cache: dict = None, digests: dict = None) -> dict:
    """files: {name: bytes} for data/forward/*. Validates manifest <-> files internal consistency. cache / digests are only
    speed-ups for --history: parsed row files by (name, sha256, columns), and the sha256 of files already hashed.
    Returns {"manifest", "manifest_bytes", "manifest_sha256", "tables": {table: {"columns", "key", "parts", "digests"}}, "meta"};
    parts = {file name: rows}, digests = {file name: sha256}."""
    mb = files.get(MANIFEST)
    if mb is None:
        raise RecordError("manifest.json missing")
    try:
        m = json.loads(mb.decode("utf-8"))
    except (UnicodeDecodeError, ValueError, RecursionError) as e:
        raise RecordError(f"manifest.json unreadable: {e}") from None
    if not isinstance(m, dict) or type(m.get("schema")) is not int or m["schema"] != 1:          # 1.0 and true equal 1 in Python
        raise RecordError(f"manifest schema {m.get('schema') if isinstance(m, dict) else m!r} unsupported (expected 1)")
    for k in ("generated_at_utc", "date_utc", "row_counts", "max_id", "files", "columns", "prev_manifest_sha256"):
        if k not in m:
            raise RecordError(f"manifest.json: key {k!r} missing")
    for k in ("row_counts", "max_id", "files", "columns"):
        if not isinstance(m[k], dict):
            raise RecordError(f"manifest.json: {k} is not an object")
    if any(not isinstance(info, dict) for info in m["files"].values()):
        raise RecordError("manifest.json: an entry of files is not an object")
    try:
        parse_iso(m["generated_at_utc"])
    except (TypeError, ValueError):
        raise RecordError(f"manifest.json: unreadable generated_at_utc {m['generated_at_utc']!r}") from None
    for required in REQUIRED_FILES:
        if required not in m["files"]:
            raise RecordError(f"manifest.json: file {required} not listed")
    for fname in sorted(files):
        if fname != MANIFEST and fname not in m["files"]:
            raise RecordError(f"{fname}: present but not listed in manifest.json")
    tables = {}
    for table, key in ROW_TABLE_KEYS.items():
        cols = m["columns"].get(table)
        if not isinstance(cols, list) or not all(isinstance(c, str) for c in cols) or key not in cols:
            raise RecordError(f"manifest.columns[{table}] missing or without key {key}")
        tables[table] = {"columns": cols, "key": key, "parts": {}, "digests": {}}
    all_keys = {table: [] for table in tables}
    meta = None
    for fname in sorted(m["files"]):
        info = m["files"][fname]
        data = files.get(fname)
        if data is None:
            raise RecordError(f"{fname}: listed in manifest but missing")
        digest = digests[fname] if digests and fname in digests else sha256(data)
        if digest != info.get("sha256"):
            raise RecordError(f"{fname}: sha256 mismatch against manifest")
        if len(data) != info.get("bytes"):
            raise RecordError(f"{fname}: byte length {len(data)} != manifest {info.get('bytes')}")
        spec = row_file(fname)
        if spec is not None:
            table, key, month = spec
            cols = tables[table]["columns"]
            memo = (fname, digest, tuple(cols))
            parsed = cache.get(memo) if cache is not None else None
            if parsed is None:
                parsed = parse_row_file(fname, data, cols, key, month)
                if cache is not None:
                    cache[memo] = parsed
            rows, keys = parsed
            if info.get("rows") != len(rows):
                raise RecordError(f"{fname}: row count {len(rows)} != manifest {info.get('rows')}")
            tables[table]["parts"][fname] = rows
            tables[table]["digests"][fname] = digest
            all_keys[table].extend(keys)
        elif fname == "meta.json":
            try:
                meta = json.loads(data.decode("utf-8"), object_pairs_hook=OrderedDict)
            except (UnicodeDecodeError, ValueError, RecursionError) as e:
                raise RecordError(f"meta.json unreadable: {e}") from None
            if not isinstance(meta, dict) or list(meta.keys()) != sorted(meta.keys()):
                raise RecordError("meta.json: not an object with sorted keys")
            meta_bytes = data
            if info.get("rows") != len(meta) or m["row_counts"].get("meta") != len(meta):
                raise RecordError(f"meta.json: {len(meta)} keys != manifest rows")
        elif fname != "schema.sql":
            raise RecordError(f"{fname}: not a record file name")
    for table, keys in all_keys.items():
        key = tables[table]["key"]
        if len(set(keys)) != len(keys):
            raise RecordError(f"{table}: {key} values not unique across its files")
        if m["row_counts"].get(table) != len(keys):
            raise RecordError(f"{table}: row count {len(keys)} != manifest.row_counts {m['row_counts'].get(table)}")
        want_max = max(keys) if keys else None
        if m["max_id"].get(table) != want_max:
            raise RecordError(f"{table}: max {key} {want_max} != manifest.max_id {m['max_id'].get(table)}")
    if meta is None:
        raise RecordError("meta.json missing")
    # R9-REC-01: one byte form for meta.json and manifest.json, checked last so every check above keeps its sharper message. A duplicated key
    # ('"wave_T0": "1", "wave_T0": "2"') is read one way by a first-wins reader (SQLite json_extract) and another way by a last-wins one (Python)
    for name, data, obj, indent in (("meta.json", meta_bytes, meta, 1), (MANIFEST, mb, m, 2)):
        try:
            canonical = canon_document(obj, indent)
        except (ValueError, RecursionError):
            canonical = None
        if canonical != data:
            raise RecordError(f"{name} is not in canonical form (a duplicate key, another number spelling or another layout than "
                              f"json.dumps(indent={indent}, sort_keys=True, ensure_ascii=False) + LF)")
    return {"manifest": m, "manifest_bytes": mb, "manifest_sha256": sha256(mb), "tables": tables, "meta": meta}


def project(row: dict, cols: list) -> tuple:
    return tuple(canon(row.get(c)) for c in cols)


def check_pair(prev: dict, cur: dict) -> dict:
    """prev/cur from load_snapshot. Raises RecordError on chain break, deletion, rewrite, removed column/table,
    insertion below the previous max_id, meta rewrite. Returns a report with warnings (late rows etc.).
    A file with the same name, bytes and columns in both snapshots holds the same rows, so only the other files are compared:
    keys are unique per snapshot, so a row of a changed earlier file can only continue in a changed or new later file."""
    report = {"warnings": [], "appended_columns": {}, "new_rows": {}, "late_rows": {}}
    pm, cm = prev["manifest"], cur["manifest"]
    if cm.get("prev_manifest_sha256") != prev["manifest_sha256"]:
        raise RecordError(f"chain broken: prev_manifest_sha256 {str(cm.get('prev_manifest_sha256'))[:12]}... != sha256 of the previous "
                          f"manifest {prev['manifest_sha256'][:12]}... (generated {pm['generated_at_utc']})")
    if parse_iso(cm["generated_at_utc"]) < parse_iso(pm["generated_at_utc"]):
        raise RecordError(f"generated_at_utc moved backwards: {pm['generated_at_utc']} -> {cm['generated_at_utc']}")
    pgen = parse_iso(pm["generated_at_utc"])
    for table, pinfo in prev["tables"].items():
        cinfo = cur["tables"].get(table)
        if cinfo is None:
            raise RecordError(f"record deleted: table {table} removed")
        pcols, ccols = pinfo["columns"], cinfo["columns"]
        missing = [c for c in pcols if c not in ccols]
        if missing:
            raise RecordError(f"record rewritten: {table} column removed/renamed: {missing}")
        appended = [c for c in ccols if c not in pcols]
        if appended:
            report["appended_columns"][table] = appended
        key = pinfo["key"]
        same = {f for f, d in pinfo["digests"].items() if cinfo["digests"].get(f) == d} if pcols == ccols else set()
        prev_rows = [r for f, rows in pinfo["parts"].items() if f not in same for r in rows]
        cur_rows = [r for f, rows in cinfo["parts"].items() if f not in same for r in rows]
        cur_index = {r[key]: project(r, pcols) for r in cur_rows}          # one row per key (load_snapshot rejects duplicates)
        for r in prev_rows:
            k = r[key]
            have = cur_index.get(k)
            if have is None:
                raise RecordError(f"record deleted: {table} {key}={k}")
            if have != project(r, pcols):
                raise RecordError(f"record rewritten: {table} {key}={k}")
        prev_keys = {r[key] for r in prev_rows}
        new_rows = [r for r in cur_rows if r[key] not in prev_keys]
        report["new_rows"][table] = len(new_rows)
        if table in ID_TABLES:
            pmax = pm["max_id"].get(table)
            if pmax is not None:
                for r in new_rows:
                    if r[key] <= pmax:
                        raise RecordError(f"record rewritten: {table} id={r[key]} inserted below previous max_id {pmax}")
            late = sum(1 for r in new_rows if isinstance(r.get("logged_at"), int) and r["logged_at"] < pgen - LATE_THRESHOLD_S)
            report["late_rows"][table] = late
            if late:
                report["warnings"].append(f"{table}: {late} new row(s) carry logged_at older than the previous snapshot "
                                          f"({pm['generated_at_utc']} - {LATE_THRESHOLD_S}s): self-reported times, see README")
    for k, v in prev["meta"].items():
        if k not in cur["meta"]:
            raise RecordError(f"record deleted: meta key {k}")
        if canon(cur["meta"][k]) != canon(v):
            raise RecordError(f"record rewritten: meta key {k}")
    return report


def sidecar_doc(sc: str, data: bytes) -> tuple:
    """(sha256, path) of the document a sidecar freezes. The first line reads exactly '<64 lowercase hex digits>  docs/<same name>.md': the path
    is pinned to the sidecar's own name, so a look-alike name (one Cyrillic letter) planted in the first publication cannot stand in for the
    frozen document while the real one is rewritten later (R9-REC-05)."""
    want = sc[:-len(".sha256")] + ".md" if sc.endswith(".sha256") else None
    m = SIDECAR_LINE_RE.fullmatch(data.split(b"\n", 1)[0])
    if want is None or m is None or m.group(2) != want.encode("utf-8"):
        raise RecordError(f"{sc}: first line is not '<sha256>  {want}' (64 lowercase hex digits, two spaces, the .md beside the sidecar)")
    return m.group(1).decode("ascii"), want


def check_frozen_docs(get_bytes, sidecar_paths) -> list:
    """Each sidecar's first line names the .md beside it (sidecar_doc). Returns the list of (md, sha) verified."""
    out = []
    for sc in sidecar_paths:
        data = get_bytes(sc)
        if data is None:
            raise RecordError(f"{sc}: missing")
        token, md = sidecar_doc(sc, data)
        mdb = get_bytes(md)
        if mdb is None:
            raise RecordError(f"{sc}: frozen doc {md} missing")
        if sha256(mdb) != token:
            raise RecordError(f"frozen doc {md}: sha256 {sha256(mdb)[:12]}... != sidecar {token[:12]}...")
        out.append((md, token))
    return out


# ----------------------------------------------------------------------------------------------------- git helpers
def _git(repo: str, *args, binary: bool = False):
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0", GIT_PAGER="cat", GIT_NO_REPLACE_OBJECTS="1")   # the objects themselves, never a replace ref
    r = subprocess.run(["git", "--no-pager", *args], cwd=repo, capture_output=True, env=env, timeout=600)
    if r.returncode != 0:
        return None
    return r.stdout if binary else r.stdout.decode("utf-8", "replace")


def git_show(repo: str, rev: str, path: str):
    return _git(repo, "cat-file", "blob", f"{rev}:{path}", binary=True)


def git_batch(repo: str, specs: list) -> list:
    """Contents of many '<rev>:<path>' specs through ONE 'git cat-file --batch'; None where a spec names no blob. A failed git is OSError."""
    if not specs:
        return []
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0", GIT_PAGER="cat", GIT_NO_REPLACE_OBJECTS="1")
    r = subprocess.run(["git", "--no-pager", "cat-file", "--batch"], cwd=repo, input="".join(sp + "\n" for sp in specs).encode("utf-8"),
                       capture_output=True, env=env, timeout=600)
    if r.returncode != 0:
        raise OSError("git cat-file --batch failed")
    out, pos, res = r.stdout, 0, []
    try:
        for _spec in specs:
            nl = out.index(b"\n", pos)
            header = out[pos:nl].split()
            pos = nl + 1
            if len(header) == 3 and header[1] in (b"blob", b"tree", b"commit", b"tag") and header[2].isdigit():
                size = int(header[2])
                res.append(out[pos:pos + size] if header[1] == b"blob" else None)
                pos += size + 1
            else:                                                              # '<spec> missing'
                res.append(None)
    except ValueError:
        raise OSError("git cat-file --batch: unreadable answer") from None
    return res


def git_tree(repo: str, rev: str) -> dict:
    """{path: (mode, blob id)} of every entry of a commit."""
    out = _git(repo, "ls-tree", "-r", "-z", rev, binary=True)
    if out is None:
        raise OSError(f"git ls-tree failed for {rev}")             # an empty answer would read as "record deleted"
    tree = {}
    for entry in out.split(b"\0"):
        if entry:
            info, path = entry.split(b"\t", 1)
            mode, _kind, oid = info.decode("ascii").split()
            tree[path.decode("utf-8", "replace")] = (mode, oid)
    return tree


def git_commits(repo: str, branch: str, *paths: str) -> list:
    out = _git(repo, "rev-list", "--reverse", branch, "--", *paths)       # rev-list: `git log` output changes with log.showSignature
    if out is None:
        raise OSError(f"git rev-list failed for {branch!r} (not a git repository, or branch missing)")
    return [c for c in out.split() if c]


class RecordReader:
    """Reads the record files of one commit after the other; a file whose blob id did not change is neither re-read nor re-hashed."""

    def __init__(self, repo: str, data_dir: str):
        self.repo, self.prefix, self.last = repo, data_dir + "/", {}

    def read(self, tree: dict) -> tuple:
        cur = {}
        for path, (mode, oid) in tree.items():
            name = path[len(self.prefix):] if path.startswith(self.prefix) else ""
            if "/" in name or not is_record_file(name):
                continue
            if mode == "160000":                                               # R10-REC-02: a gitlink has no blob to read: damaged, not git trouble
                raise RecordError(f"{path}: not a regular file (a gitlink)")
            hit = self.last.get(name)
            if hit is None or hit[0] != oid:
                data = _git(self.repo, "cat-file", "blob", oid, binary=True)
                if data is None:                                               # R9-REC-07: git trouble, not a broken record
                    raise OSError(f"{path}: git cat-file failed for blob {oid[:12]} listed by the tree (run it again)")
                hit = (oid, data, sha256(data))
            cur[name] = hit
        self.last = cur
        return {n: h[1] for n, h in cur.items()}, {n: h[2] for n, h in cur.items()}


def verify_working_tree(repo: str, data_dir: str = DATA_DIR) -> int:
    base = os.path.join(repo, data_dir)
    files, ignored = {}, []
    for name in sorted(os.listdir(base)) if os.path.isdir(base) else []:
        p = os.path.join(base, name)
        if is_record_file(name):
            if not os.path.isfile(p):
                raise RecordError(f"{data_dir}/{name}: not a regular file")
            with open(p, "rb") as f:
                files[name] = f.read()
        elif name != "anchors" or not os.path.isdir(p):
            # R9-REC-06: a working tree also holds what the reader's own system writes (.DS_Store, desktop.ini, an editor's swap file). What was
            # PUBLISHED under data/forward is held to the rule by --history, so here it is reported, not failed
            ignored.append(name)
    snap = load_snapshot(files)
    m = snap["manifest"]
    docs_dir = os.path.join(repo, "docs")
    sidecars = sorted(set(FROZEN_SIDECARS) | set("docs/" + f for f in os.listdir(docs_dir) if f.endswith(".sha256"))) if os.path.isdir(docs_dir) else list(FROZEN_SIDECARS)

    def get(path):
        p = os.path.join(repo, path)
        if not os.path.isfile(p):
            return None
        with open(p, "rb") as f:
            return f.read()
    frozen = check_frozen_docs(get, sidecars)
    print(f"OK working tree: manifest {snap['manifest_sha256'][:12]}... generated {m['generated_at_utc']} rows {m['row_counts']} "
          f"max_id {m['max_id']} files {len(m['files'])} frozen docs {len(frozen)} verified against their sidecars")
    for name in ignored:
        print(f"WARN {data_dir}/{name}: not part of the record, ignored here (--history checks what is published)")
    return 0


class HistoryWalk:
    """Checks commits one after the other. A commit is looked at by the blob ids of its tree, so the cost follows what changed and not the size
    of the history: the files must be consistent with the manifest at that commit, a commit that leaves the manifest unchanged must leave every
    data file byte-identical (anchor-only commits), a changed manifest must chain to and extend the previous snapshot, and neither the manifest,
    an anchor nor a sidecar may ever disappear. The publishing job runs the same steps over the commits since its last run."""

    def __init__(self, repo: str, data_dir: str = DATA_DIR):
        self.repo, self.data_dir, self.manifest_path = repo, data_dir, f"{data_dir}/{MANIFEST}"
        self.record_prefix, self.anchor_prefix = data_dir + "/", data_dir + "/anchors/"
        self.reader, self.cache = RecordReader(repo, data_dir), {}
        self.prev, self.record_view, self.docs_view = None, None, None
        self.base = None
        self.snapshots = 0
        self.seen_manifest_sha, self.anchors_seen, self.last_sidecar = set(), {}, {}
        self.warnings, self.strays, self.stray_entries = [], set(), {}

    def _views(self, tree: dict) -> tuple:
        cut = len(self.record_prefix)
        record = {p: e for p, e in tree.items() if p.startswith(self.record_prefix) and "/" not in p[cut:]}
        return record, {p: e for p, e in tree.items() if p.startswith("docs/")}

    def _keep(self, snap: dict) -> None:
        self.prev = snap
        self.snapshots += 1
        self.seen_manifest_sha.add(snap["manifest_sha256"])
        used = {(n, d, tuple(info["columns"])) for info in snap["tables"].values() for n, d in info["digests"].items()}
        for memo in set(self.cache) - used:                                    # keep only the parsed files of the latest snapshot
            del self.cache[memo]

    def _snapshot(self, tree: dict) -> dict:
        files, digests = self.reader.read(tree)
        snap = load_snapshot(files, self.cache, digests)
        snap["files"] = files
        return snap

    def _is_anchor(self, path: str) -> bool:
        """R10-REC-01: only a file of the anchor name form directly under anchors/ is an anchor that may never leave; anything else there is a stray
        (a warning in the middle of the history, a failure at the tip) and one removal commit repairs it."""
        return path.startswith(self.anchor_prefix) and ANCHOR_RE.fullmatch(path[len(self.anchor_prefix):]) is not None

    def _is_permanent(self, path: str) -> bool:
        """R12-REC-01: an entry the walk never lets leave: an anchor, or a record file directly under data/forward (at a consistent tip the
        manifest lists every such file, so removing one fails as 'listed in manifest but missing' or 'record deleted')."""
        rest = path[len(self.record_prefix):] if path.startswith(self.record_prefix) else None
        return self._is_anchor(path) or (rest is not None and "/" not in rest and is_record_file(rest))

    def _blob(self, tree: dict, path: str):
        """Bytes of a path in this commit's tree, None when the tree has no such path. A listed blob that cannot be read is OSError (git trouble,
        run it again), never 'missing' (R9-REC-07)."""
        entry = tree.get(path)
        if entry is None:
            return None
        if entry[0] == "160000":                                               # R10-REC-02
            raise RecordError(f"{path}: not a regular file (a gitlink)")
        data = _git(self.repo, "cat-file", "blob", entry[1], binary=True)
        if data is None:
            raise OSError(f"git cat-file failed for {path} ({entry[1][:12]}) listed by the tree")
        return data

    def _check_paths(self, tree: dict, c: str) -> None:
        """Once a record exists, nothing under data/forward is anything but a regular record file or a named anchor. See finish()."""
        strays = set()
        for p, (mode, _oid) in tree.items():
            if p.startswith(self.record_prefix):
                rest = p[len(self.record_prefix):]
                legal = ANCHOR_RE.fullmatch(rest[len("anchors/"):]) if rest.startswith("anchors/") else ("/" not in rest and is_record_file(rest))
                if not legal or mode != "100644":
                    strays.add(p)
        self.warnings.extend(f"{c[:12]}: {p} does not belong to the record" for p in sorted(strays - self.strays))
        self.strays, self.stray_entries = strays, {p: tree[p] for p in strays}

    def finish(self) -> None:
        """At the tip a stray file sits beside the record, and a reader's glob would pick it up. In the middle of the history it changed no row, and
        failing for good would make one mistaken commit unrecoverable, so it stays a warning there."""
        if self.strays:
            first = sorted(self.strays)[0]
            mode, oid = self.stray_entries.get(first, ("", ""))
            raise StrayAtTip(first, self._is_anchor(first), self._is_permanent(first), mode, oid)

    def _published_before(self, sha: str) -> bool:
        """A resumed walk starts with one manifest; an anchor of an older one is looked up in the history before the starting point, once, in one
        batch, and not at all when the walk has seen that manifest already (R9-REC-08)."""
        if sha not in self.seen_manifest_sha and self.base is not None:
            commits = git_commits(self.repo, self.base, self.manifest_path)
            for data in git_batch(self.repo, [f"{c}:{self.manifest_path}" for c in commits]):
                if data is not None:
                    self.seen_manifest_sha.add(sha256(data))
            self.base = None
        return sha in self.seen_manifest_sha

    def start_from(self, commit: str) -> None:
        """Resume after a commit that was verified earlier: its state is the starting point, nothing before it is looked at."""
        tree = git_tree(self.repo, commit)
        self.base = commit
        self.record_view, self.docs_view = self._views(tree)
        if self.manifest_path in tree:
            self._keep(self._snapshot(tree))
            self._check_paths(tree, commit)                                    # R9-OPS-01: the starting commit meets the tip rule too (finish)
        self.anchors_seen = {p: e for p, e in tree.items() if self._is_anchor(p)}
        self.last_sidecar = {p: self._blob(tree, p) for p in self.docs_view if p.endswith(".sha256")}

    def step(self, c: str) -> None:
        tree = git_tree(self.repo, c)
        record, docs = self._views(tree)
        if self.manifest_path in tree or self.prev is not None:
            self._check_paths(tree, c)
        if record != self.record_view:
            self.record_view = record
            if self.manifest_path not in tree:
                if self.prev is not None:
                    raise RecordError(f"commit {c[:12]}: record deleted: {self.manifest_path} removed")
            else:
                try:
                    snap = self._snapshot(tree)
                    prev = self.prev
                    if prev is not None and snap["manifest_sha256"] == prev["manifest_sha256"]:
                        if snap["files"] != prev["files"]:                     # manifest unchanged => data unchanged
                            raise RecordError("record rewritten: a data file changed while manifest.json did not")
                    else:
                        if prev is not None:
                            rep = check_pair(prev, snap)
                            self.warnings.extend(f"{c[:12]}: {w}" for w in rep["warnings"])
                            for t, cols in rep["appended_columns"].items():
                                self.warnings.append(f"{c[:12]}: {t} appended columns {cols} (schema evolution, allowed)")
                        elif snap["manifest"]["prev_manifest_sha256"] is not None:
                            raise RecordError("the first snapshot names a previous manifest")
                        self._keep(snap)
                except RecordError as e:
                    raise RecordError(f"commit {c[:12]}: {e}") from None
        if docs != self.docs_view or (self.prev is not None and not self.last_sidecar):
            self.docs_view = docs
            sidecars = sorted(set(p for p in docs if p.endswith(".sha256")) | set(self.last_sidecar) | (set(FROZEN_SIDECARS) if self.prev is not None else set()))
            try:
                check_frozen_docs(lambda p: self._blob(tree, p), sidecars)
            except RecordError as e:
                raise RecordError(f"commit {c[:12]}: {e}") from None
            for sc in sidecars:
                cur_sc = self._blob(tree, sc)
                prev_sc = self.last_sidecar.get(sc)
                if prev_sc is not None and not cur_sc.startswith(prev_sc):
                    raise RecordError(f"commit {c[:12]}: sidecar {sc} is not append-only (earlier content changed)")
                self.last_sidecar[sc] = cur_sc
        for p, entry in self.anchors_seen.items():
            if p not in tree:
                raise RecordError(f"commit {c[:12]}: anchor {p} removed")
            if p.endswith(".manifest.json") and tree[p][1] != entry[1]:       # the bytes; a mode repair is not a rewrite (R10-REC-01)
                raise RecordError(f"commit {c[:12]}: anchor {p} rewritten")
        for p, entry in tree.items():
            if self._is_anchor(p) and p not in self.anchors_seen:
                self.anchors_seen[p] = entry
                if p.endswith(".manifest.json"):
                    b = self._blob(tree, p)
                    if not self._published_before(sha256(b)):
                        raise RecordError(f"commit {c[:12]}: anchor {p} does not equal any published manifest")
                    gen = json.loads(b.decode("utf-8"))["generated_at_utc"]
                    if os.path.basename(p) != gen.replace("-", "").replace(":", "") + ".manifest.json":
                        raise RecordError(f"commit {c[:12]}: anchor {p} is not named after its generated_at_utc {gen}")


def verify_history(repo: str, branch: str = "HEAD", data_dir: str = DATA_DIR) -> int:
    if (_git(repo, "rev-parse", "--is-shallow-repository") or "").strip() == "true":
        raise OSError("this is a shallow clone: run git fetch --unshallow first, the check needs the whole history")
    all_commits = git_commits(repo, branch)
    walk = HistoryWalk(repo, data_dir)
    for c in all_commits:
        walk.step(c)
    walk.finish()
    if walk.snapshots == 0:
        raise RecordError("no snapshot found in history")
    prev = walk.prev
    anchors = sum(1 for p in walk.anchors_seen if p.endswith(".manifest.json"))
    print(f"OK history: commits {len(all_commits)} snapshots {walk.snapshots} anchors {anchors} warnings {len(walk.warnings)}; "
          f"latest manifest {prev['manifest_sha256'][:12]}... generated {prev['manifest']['generated_at_utc']} rows {prev['manifest']['row_counts']}")
    for w in walk.warnings:
        print("WARN", w)
    return 0


def find_row(repo: str, branch: str, table: str, key_value: int, data_dir: str = DATA_DIR) -> int:
    if table not in ROW_TABLE_KEYS:
        raise RecordError(f"unknown table {table!r} (one of {list(ROW_TABLE_KEYS)})")
    key = ROW_TABLE_KEYS[table]
    searched = set()
    for c in git_commits(repo, branch, f"{data_dir}/{MANIFEST}"):
        mb = git_show(repo, c, f"{data_dir}/{MANIFEST}")
        if mb is None:
            continue
        m = json.loads(mb.decode("utf-8"))
        for fname, info in sorted(m["files"].items()):
            spec = row_file(fname)
            if spec is None or spec[0] != table or (fname, info.get("sha256")) in searched:
                continue
            searched.add((fname, info.get("sha256")))
            data = git_show(repo, c, f"{data_dir}/{fname}")
            if data is None:
                continue
            hit = next((r for r in parse_jsonl(data, fname) if r[key] == key_value), None)
            if hit is None:
                continue
            gen = m["generated_at_utc"]
            print(f"{table} {key}={key_value}: first published in commit {c[:12]} file {fname} (manifest sha256 {sha256(mb)[:12]}..., "
                  f"generated {gen}, commit date {_git(repo, 'show', '-s', '--no-show-signature', '--format=%cI', c).strip()})")
            print(f"  row logged_at={hit.get('logged_at')} bar_ts={hit.get('bar_ts', hit.get('t0_bar_ts'))}")
            compact = gen.replace("-", "").replace(":", "")
            tip = git_tree(repo, branch)
            anchors = sorted(p for p in tip if p.startswith(f"{data_dir}/anchors/") and p.endswith(".manifest.json"))
            later = [a for a in anchors if os.path.basename(a) >= compact + ".manifest.json"]
            if later:
                a = later[0]
                ots = a + ".ots" if (a + ".ots") in tip else "(no .ots yet)"
                print(f"  earliest anchor covering it: {a} {ots}  (verify: git show {branch}:{a} | ots verify ... or ots verify {ots})")
            else:
                print("  no OTS anchor at or after this snapshot yet (the chain still covers it from any later anchor)")
            return 0
    raise RecordError(f"{table} {key}={key_value} not found in any published snapshot")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Verify the structure-map forward record (stdlib only, offline).")
    ap.add_argument("--repo", default=os.path.dirname(os.path.abspath(__file__)), help="path of the public repository clone")
    ap.add_argument("--branch", default="HEAD")
    ap.add_argument("--data-dir", default=DATA_DIR)
    ap.add_argument("--history", action="store_true", help="verify every commit pair of the branch")
    ap.add_argument("--find-row", nargs=2, metavar=("TABLE", "KEY"), help="first commit/anchor containing a row")
    args = ap.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):                   # R11-REC-03: an odd file name on a cp949 console is never a traceback
        try:
            stream.reconfigure(errors="backslashreplace")
        except (AttributeError, ValueError, OSError):
            pass
    try:
        if args.find_row:
            return find_row(args.repo, args.branch, args.find_row[0], int(args.find_row[1]), args.data_dir)
        if args.history:
            return verify_history(args.repo, args.branch, args.data_dir)
        return verify_working_tree(args.repo, args.data_dir)
    except RecordError as e:
        print(f"FAIL: {e}")
        return 1
    except Exception as e:  # noqa: BLE001 — anything else in a hostile repository is a failed check too, never a traceback
        print(f"ERROR: {type(e).__name__}: {e}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
