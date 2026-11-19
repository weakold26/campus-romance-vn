#!/usr/bin/env python3
"""시나리오 전수 시뮬레이션.

- 그래프 도달성 BFS (끊긴 링크·도달 불가 노드·막다른 길)
- 호감도·플래그 상태 공간 탐색 (조건 분기·엔딩 도달 검증)
- 대사 품질(번역체·중복·길이) 점검
"""
import json
import os
import re
import sys
from collections import deque

HERE = os.path.dirname(os.path.abspath(__file__))
PATH = os.path.join(HERE, "..", "src", "data", "scenario.json")

with open(PATH, encoding="utf-8") as f:
    data = json.load(f)
nodes, meta = data["nodes"], data["meta"]
HERO = list(meta["heroines"].keys())
BGS = {"campus_day", "library", "clubroom", "campus_night"}
EXPRS = {"base", "blush", "surprised", "serious"}
errors, warnings = [], []

# ---------- 1. 구조 ----------
for nid, n in nodes.items():
    targets = []
    if n.get("next"):
        targets.append(n["next"])
    for c in n.get("choices", []):
        if c.get("next"):
            targets.append(c["next"])
    for b in n.get("branch", []):
        targets.append(b["next"])
    for t in targets:
        if t not in nodes:
            errors.append("broken link %s -> %s" % (nid, t))
    if not n.get("text") and not n.get("choices") and not n.get("branch") and not n.get("ending") and not n.get("next"):
        errors.append("dead end at %s" % nid)
    if n.get("ending") and n["ending"] not in meta["endings"]:
        errors.append("unknown ending %s at %s" % (n["ending"], nid))
    if n.get("choices") and len(n["choices"]) < 2:
        errors.append("choice with <2 options at %s" % nid)
    if n.get("bg") and n["bg"] not in BGS:
        errors.append("unknown bg %s at %s" % (n["bg"], nid))
    for key in ("show", "show2"):
        if n.get(key):
            if n[key]["id"] not in HERO:
                errors.append("unknown char %s at %s" % (n[key]["id"], nid))
            if n[key]["expr"] not in EXPRS:
                errors.append("unknown expr %s at %s" % (n[key]["expr"], nid))
    if n.get("who") and n["who"] not in ("나", "한서윤", "문채원"):
        errors.append("unknown speaker %s at %s" % (n["who"], nid))

# ---------- 2. 그래프 도달성 ----------


def static_next(nid):
    n = nodes[nid]
    out = []
    if n.get("next"):
        out.append(n["next"])
    out += [c["next"] for c in n.get("choices", []) if c.get("next")]
    out += [b["next"] for b in n.get("branch", [])]
    return out


reached = set()
stack = [meta["start"]]
while stack:
    u = stack.pop()
    if u in reached or u not in nodes:
        continue
    reached.add(u)
    stack.extend(static_next(u))

unreachable = [nid for nid in nodes if nid not in reached]
if unreachable:
    errors.append("도달 불가 노드 %d개: %s" % (len(unreachable), unreachable[:10]))

# ---------- 3. 상태 공간 ----------
RELEVANT_FLAGS = set()
for n in nodes.values():
    for c in n.get("choices", []):
        w = c.get("when") or {}
        if w.get("flag"):
            RELEVANT_FLAGS.add(w["flag"])
        if w.get("noflag"):
            RELEVANT_FLAGS.add(w["noflag"])
    for b in n.get("branch", []):
        w = b.get("if") or {}
        if w.get("flag"):
            RELEVANT_FLAGS.add(w["flag"])
        if w.get("noflag"):
            RELEVANT_FLAGS.add(w["noflag"])
print("relevant flags:", sorted(RELEVANT_FLAGS))


def test_cond(c, aff, flags):
    if not c:
        return True
    if c.get("flag") and c["flag"] not in flags:
        return False
    if c.get("noflag") and c["noflag"] in flags:
        return False
    for k, v in (c.get("affMin") or {}).items():
        if aff.get(k, 0) < v:
            return False
    for k, v in (c.get("affMax") or {}).items():
        if aff.get(k, 0) > v:
            return False
    return True


CLAMP = 14


def apply_eff(eff, aff, flags):
    a = dict(aff)
    f = set(flags)
    if eff:
        for k in HERO:
            if eff.get(k):
                a[k] = min(CLAMP, a.get(k, 0) + eff[k])
        if eff.get("flag") in RELEVANT_FLAGS:
            f.add(eff["flag"])
    return a, frozenset(f)


seen = set()
queue = deque([(meta["start"], dict.fromkeys(HERO, 0), frozenset())])
ending_hits = {}
maxaff = dict.fromkeys(HERO, 0)
choice_states = {}
guard = 0

while queue:
    nid, aff, flags = queue.popleft()
    path_guard = 0
    while True:
        guard += 1
        path_guard += 1
        if path_guard > 5000:
            errors.append("무한 루프 의심: %s" % nid)
            break
        if guard > 3_000_000:
            errors.append("상태 폭발")
            queue.clear()
            break
        n = nodes.get(nid)
        if not n:
            break
        if n.get("eff"):
            aff, flags = apply_eff(n["eff"], aff, flags)
        if n.get("ending"):
            ending_hits.setdefault(n["ending"], (nid, dict(aff), sorted(flags)))
            for k in HERO:
                maxaff[k] = max(maxaff[k], aff.get(k, 0))
            break
        if n.get("choices"):
            choice_states.setdefault(nid, []).append((aff, flags))
            for c in n["choices"]:
                if not test_cond(c.get("when"), aff, flags):
                    continue
                a2, f2 = apply_eff(c.get("eff"), aff, flags)
                for k in HERO:
                    maxaff[k] = max(maxaff[k], a2.get(k, 0))
                key = (c["next"], tuple(a2[k] for k in HERO), f2)
                if key not in seen:
                    seen.add(key)
                    queue.append((c["next"], a2, f2))
            break
        if n.get("branch"):
            taken = None
            for b in n["branch"]:
                if test_cond(b.get("if"), aff, flags):
                    taken = b["next"]
                    break
            if not taken:
                errors.append("branch fell through at %s" % nid)
                break
            key = (taken, tuple(aff[k] for k in HERO), flags)
            if key in seen:
                break
            seen.add(key)
            nid = taken
            continue
        nxt = n.get("next")
        if not nxt:
            errors.append("no next and no ending at %s" % nid)
            break
        key = (nxt, tuple(aff[k] for k in HERO), flags)
        if key in seen:
            break
        seen.add(key)
        nid = nxt

choice_count = sum(1 for n in nodes.values() if n.get("choices"))
for nid, states in choice_states.items():
    n = nodes[nid]
    for aff, flags in states:
        shown = sum(1 for c in n["choices"] if test_cond(c.get("when"), aff, flags))
        if shown < 2:
            warnings.append("%s 상태 %s에서 선택지 %d개" % (nid, aff, shown))

for eid in meta["endings"]:
    if eid not in ending_hits:
        errors.append("도달 불가 엔딩: %s" % eid)

# ---------- 4. 텍스트 ----------
TEXT_BAD = [
    (r"당신", "번역체 '당신'"),
    (r"그대(?!로)", "번역체 '그대'"),
    (r"\.\.\.\s*\.\.\.", "말줄임표 중복"),
    (r"!!", "느낌표 중복"),
    (r"\?\?", "물음표 중복"),
    (r"  +", "공백 중복"),
]
for nid, n in nodes.items():
    t = n.get("text") or ""
    for pat, msg in TEXT_BAD:
        if re.search(pat, t):
            warnings.append("%s '%s': %s" % (nid, t[:26], msg))
    if len(t) > 150:
        warnings.append("%s 대사 과다(%d자): %s" % (nid, len(t), t[:26]))

dups = {}
for nid, n in nodes.items():
    t = (n.get("text") or "").strip()
    if len(t) > 14:
        dups.setdefault(t, []).append(nid)
for t, ids in dups.items():
    if len(ids) > 1:
        warnings.append("중복 대사 %s: %s" % (ids, t[:36]))

print("nodes:", len(nodes))
print("choice nodes:", choice_count)
print("reachable:", len(reached), "/", len(nodes))
print("max affection:", maxaff)
print("states:", len(seen))
print("endings reached:")
for eid, hit in sorted(ending_hits.items()):
    print("   %-14s node=%s aff=%s flags=%s" % (eid, hit[0], hit[1], hit[2]))
if errors:
    print("\nERRORS (%d)" % len(errors))
    for e in errors:
        print(" -", e)
if warnings:
    print("\nWARNINGS (%d)" % len(warnings))
    for w in warnings[:40]:
        print(" -", w)
sys.exit(1 if errors else 0)
