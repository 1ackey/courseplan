#!/usr/bin/env python3
"""Smoke-test the course comment API (against a local panel)."""
import json
import sys
import urllib.request

BASE = "http://127.0.0.1:8766"


def call(method, path, payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        BASE + path, data=data, method=method,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode())


key = "testkey123456"
status, data = call("GET", "/api/comments/1?key=" + key)
print("GET empty:", status, data)
assert status == 200 and data["comments"] == []

status, data = call("POST", "/api/comments/1",
                    {"body": "第一门测试留言", "author": "测试同学", "key": key})
print("POST:", status, data)
assert status == 201
cid = data["id"]

status, data = call("GET", "/api/comments/1?key=" + key)
print("GET own:", status, [(c["author"], c["body"], c["can_edit"]) for c in data["comments"]])
assert data["comments"][0]["can_edit"] is True

status, data = call("GET", "/api/comments/1?key=otherkey")
print("GET other:", status, [(c["author"], c["can_edit"]) for c in data["comments"]])
assert data["comments"][0]["can_edit"] is False

status, data = call("POST", f"/api/comments/{cid}/edit",
                    {"key": "otherkey", "body": "篡改"})
print("EDIT wrong key:", status, data)
assert status == 403

status, data = call("POST", f"/api/comments/{cid}/edit",
                    {"key": key, "body": "改过的留言", "author": "测试同学2"})
print("EDIT right key:", status, data)
assert status == 200

status, data = call("GET", "/api/comments/1?key=" + key)
print("GET after edit:", status, [(c["author"], c["body"], bool(c["updated_at"])) for c in data["comments"]])
assert data["comments"][0]["body"] == "改过的留言"

status, data = call("POST", f"/api/comments/{cid}/delete", {"key": "otherkey"})
print("DELETE wrong key:", status, data)
assert status == 403

status, data = call("POST", f"/api/comments/{cid}/delete", {"key": key})
print("DELETE right key:", status, data)
assert status == 200

status, data = call("GET", "/api/comments/1?key=" + key)
print("GET after delete:", status, data)
assert data["comments"] == []

status, data = call("GET", "/api/comments/999999")
print("GET missing offering:", status, data)
assert status == 404

print("ALL COMMENT API TESTS PASSED")
