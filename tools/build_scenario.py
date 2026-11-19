#!/usr/bin/env python3
"""시나리오 DSL 컴파일러.

문법
  @bg key            다음 대사부터 배경 전환
  @bgm mood          다음 대사부터 BGM 무드
  @ch 1일차 · 월요일  챕터 카드
  @show seoyun base  주역 캐릭터
  @show2 chaewon blush 조역 캐릭터
  @hide / @hide2     캐릭터 내리기
  @aff seoyun+2      다음 노드에서 호감도 변화 (여러 줄 가능)
  @flag name         다음 노드에서 플래그 설정
  @fx rain           연출(비)
  한서윤[blush]: 대사
  나: 대사
  - 나레이션
  ? 선택지 텍스트 | seoyun+2 | when=flag:cards_found
      (들여쓰기한 본문)
  @branch
  * seoyun>=12 & flag:comfort -> label
  * -> label2
  ::label            라벨
  -> label           이동
  >> ending_id       엔딩
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "script")
OUT = os.path.join(HERE, "..", "src", "data", "scenario.json")

HEROINES = {"한서윤": "seoyun", "문채원": "chaewon"}


class Node:
    def __init__(self, nid):
        self.id = nid
        self.data = {}
        self.next = None
        self.open = True

    def set(self, k, v):
        self.data[k] = v


class Compiler:
    def __init__(self):
        self.nodes = {}
        self.order = []
        self.counter = 0
        self.pending = []          # nodes waiting for a next node
        self.labels = {}
        self.gotos = []            # (node, label)
        self.pending_joins = []    # option dicts waiting for join
        self.buf = {}
        self.errors = []

    def new_id(self):
        self.counter += 1
        return "n%04d" % self.counter

    def add(self, **data):
        return self.make_node(data)

    # --------------------------------------------------------------
    def make_node(self, data, open_=True):
        nid = self.new_id()
        n = Node(nid)
        n.data.update(data)
        n.open = open_
        # 앞에서 대기하던 노드들을 이 노드로 연결
        for t in self.pending:
            if t.next is None:
                t.next = nid
        self.pending = [n] if open_ else []
        self.nodes[nid] = n
        self.order.append(nid)
        # 선택지 조인 대기
        for opt in self.pending_joins:
            if opt.get("next") is None:
                opt["next"] = nid
        self.pending_joins = []
        return n

    def flush_buf(self):
        b = self.buf
        self.buf = {}
        return b

    # --------------------------------------------------------------
    def parse(self, lines, path):
        self.compile_block(lines, path)

    def compile_block(self, lines, path):
        i = 0
        n = len(lines)
        while i < n:
            raw = lines[i]
            line = raw.rstrip("\n")
            stripped = line.strip()
            indent = len(line) - len(line.lstrip(" "))
            if not stripped or stripped.startswith("#"):
                i += 1
                continue
            if indent:
                self.errors.append("%s:%d 예상치 못한 들여쓰기: %s" % (path, i + 1, stripped))
                i += 1
                continue

            if stripped.startswith("@"):
                i = self.directive(stripped, lines, i, path)
                continue
            if stripped.startswith("::"):
                label = stripped[2:].strip()
                self.labels[label] = ("pending", len(self.pending))
                self._pending_label = label
                # 라벨은 다음 노드에 붙는다
                self.label_marks = getattr(self, "label_marks", {})
                self.label_marks[label] = True
                i += 1
                continue
            if stripped.startswith("->"):
                label = stripped[2:].strip()
                if not self.pending:
                    self.pending = []
                # 현재 열린 노드에 이동 표시
                if self.pending:
                    t = self.pending[-1]
                    t.data["goto"] = label
                    t.open = False
                    self.pending.pop()
                self.gotos.append((self.order[-1] if self.order else None, label))
                i += 1
                continue
            if stripped.startswith(">>"):
                eid = stripped[2:].strip()
                data = self.flush_buf()
                data["ending"] = eid
                # 텍스트 없이 엔딩
                self.make_node(data, open_=False)
                i += 1
                continue
            if stripped.startswith("?"):
                i = self.parse_choice(lines, i, path)
                continue
            if stripped.startswith("*"):
                self.errors.append("%s:%d 선택지 밖의 *: %s" % (path, i + 1, stripped))
                i += 1
                continue

            # 대사 / 나레이션
            data = self.flush_buf()
            m = re.match(r"^([^:\[\]]+?)(?:\[([a-z]+)\])?:\s?(.*)$", stripped)
            if m and not stripped.startswith("-"):
                who = m.group(1).strip()
                expr = m.group(2)
                text = m.group(3)
                data["who"] = who
                if expr:
                    data["e"] = expr
                data["text"] = text
            elif stripped.startswith("-"):
                data["text"] = stripped[1:].strip()
            else:
                data["text"] = stripped
            node = self.make_node(data)
            self.attach_label(node)
            i += 1

    def attach_label(self, node):
        marks = getattr(self, "label_marks", {})
        for label in list(marks):
            self.labels[label] = ("node", node.id)
            del marks[label]

    # --------------------------------------------------------------
    def directive(self, s, lines, i, path):
        parts = s[1:].split(None, 1)
        key = parts[0]
        arg = parts[1].strip() if len(parts) > 1 else ""
        if key == "bg":
            self.buf["bg"] = arg
        elif key == "bgm":
            self.buf["bgm"] = arg
        elif key == "ch":
            self.buf["ch"] = arg
        elif key == "show":
            cid, expr = (arg.split() + ["base"])[:2]
            self.buf["show"] = {"id": HEROINES.get(cid, cid), "expr": expr}
        elif key == "show2":
            cid, expr = (arg.split() + ["base"])[:2]
            self.buf["show2"] = {"id": HEROINES.get(cid, cid), "expr": expr}
        elif key == "hide":
            self.buf["hide"] = True
        elif key == "hide2":
            self.buf["hide2"] = True
        elif key == "aff":
            eff = self.buf.setdefault("eff", {})
            for chunk in arg.split():
                k, v = chunk.split("+")
                eff[HEROINES.get(k, k)] = eff.get(HEROINES.get(k, k), 0) + int(v)
        elif key == "flag":
            eff = self.buf.setdefault("eff", {})
            eff["flag"] = arg
        elif key == "fx":
            self.buf["fx"] = arg
        elif key == "branch":
            return self.parse_branch(lines, i, path)
        else:
            self.errors.append("%s:%d 알 수 없는 지시자: %s" % (path, i + 1, key))
        return i + 1

    # --------------------------------------------------------------
    def read_option_body(self, lines, i):
        """i: '?' 또는 '*' 줄 인덱스. (본문 줄 목록, 다음 인덱스) 반환."""
        j = i + 1
        body = []
        while j < len(lines):
            l = lines[j]
            st = l.strip()
            if not st:
                body.append(l)
                j += 1
                continue
            if not l.startswith(" "):
                break
            body.append(l[2:] if l.startswith("  ") else l[1:])
            j += 1
        return body, j

    def parse_choice(self, lines, i, path):
        options = []
        j = i
        while j < len(lines):
            l = lines[j]
            if not l.strip().startswith("?"):
                break
            spec = l.strip()[1:].strip()
            body, j = self.read_option_body(lines, j)
            head, *rest = spec.split("|")
            goto = None
            if "->" in head:
                head, goto = head.rsplit("->", 1)
                head = head.strip()
                goto = goto.strip()
                opt_goto = goto
            else:
                opt_goto = None
            conds = [r.strip() for r in rest if r.strip()]
            opt = {"t": head.strip(), "eff": {}, "when": None}
            if opt_goto:
                opt["goto"] = opt_goto
            for chunk in conds:
                if chunk.startswith("->"):
                    opt["goto"] = chunk[2:].strip()
                    continue
                for c in chunk.split():
                    if c.startswith("when="):
                        opt["when"] = parse_cond(c[5:])
                    elif c.startswith("flag="):
                        opt["eff"]["flag"] = c.split("=", 1)[1]
                    else:
                        m = re.match(r"^([가-힣A-Za-z]+)\+(\d+)$", c)
                        if m:
                            key = HEROINES.get(m.group(1), m.group(1))
                            opt["eff"][key] = opt["eff"].get(key, 0) + int(m.group(2))
                        else:
                            self.errors.append("%s:%d 선택지 옵션 해석 실패: %s" % (path, j + 1, c))
            options.append((opt, body))
            # 같은 들여쓰기 '?' 만 이어서
            k = j
            while k < len(lines) and not lines[k].strip():
                k += 1
            if k < len(lines) and lines[k].strip().startswith("?") and not lines[k].startswith(" "):
                j = k
                continue
            break

        choice_node = self.make_node({"choices": [o for o, _ in options]}, open_=False)
        self.attach_label(choice_node)
        # 본문 컴파일
        exits = []
        for opt, body in options:
            start = len(self.order)
            self.pending = []
            self.compile_block(body, path)
            if len(self.order) > start:
                opt["next"] = self.order[start]
                if self.pending:
                    exits.extend(self.pending)
            else:
                self.pending_joins.append(opt)
        self.pending = exits
        return j

    def parse_branch(self, lines, i, path):
        branches = []
        j = i + 1
        while j < len(lines):
            l = lines[j]
            st = l.strip()
            if not st:
                j += 1
                continue
            if not st.startswith("*"):
                break
            spec = st[1:].strip()
            if "->" in spec:
                cond, target = spec.rsplit("->", 1)
                cond = cond.strip()
                target = target.strip()
            else:
                cond, target = "", spec
            item = {"next": target}
            if cond:
                item["if"] = parse_cond(cond)
            branches.append(item)
            j += 1
        self.make_node({"branch": branches}, open_=False)
        return j

    # --------------------------------------------------------------
    def finish(self):
        # 라벨 해석
        for nid in self.order:
            n = self.nodes[nid]
            if n.next and "next" not in n.data and "choices" not in n.data and "branch" not in n.data and "ending" not in n.data:
                n.data["next"] = n.next
            for k in ("next",):
                if n.data.get(k) == "__next__":
                    n.data[k] = None
            if "goto" in n.data:
                label = n.data.pop("goto")
                if label not in self.labels:
                    self.errors.append("없는 라벨: %s (from %s)" % (label, nid))
                else:
                    n.data["next"] = self.labels[label][1]
            for c in n.data.get("choices", []):
                if c.get("goto"):
                    label = c.pop("goto")
                    if label not in self.labels:
                        self.errors.append("없는 라벨: %s (choice %s)" % (label, nid))
                    else:
                        c["next"] = self.labels[label][1]
                if c.get("next") is None:
                    self.errors.append("선택지 도착지 없음 (%s): %s" % (nid, c["t"]))
            for b in n.data.get("branch", []):
                if b["next"] not in self.labels and b["next"] not in self.nodes:
                    self.errors.append("브랜치 도착지 없음 (%s): %s" % (nid, b["next"]))
                else:
                    b["next"] = self.labels.get(b["next"], ("node", b["next"]))[1]
            if n.data.get("next") not in (None,) and n.data["next"] not in self.nodes:
                self.errors.append("끊긴 링크 %s -> %s" % (nid, n.data["next"]))
            # 빈 노드 정리
            if not n.data:
                self.errors.append("빈 노드 %s" % nid)

        out = {nid: self.clean(self.nodes[nid].data) for nid in self.order}
        return out

    def clean(self, d):
        d = dict(d)
        if d.get("eff"):
            e = d["eff"]
            out = {}
            for k in ("seoyun", "chaewon"):
                if e.get(k):
                    out[k] = e[k]
            if e.get("flag"):
                out["flag"] = e["flag"]
            d["eff"] = out
        else:
            d.pop("eff", None)
        if d.get("next") is None:
            d.pop("next", None)
        return d


def parse_cond(s):
    """'seoyun>=12 & flag:cards_found & !flag:x' -> dict"""
    cond = {}
    for part in [p.strip() for p in s.split("&")]:
        if not part:
            continue
        if part.startswith("!"):
            cond["noflag"] = part[6:] if part.startswith("!flag:") else part[1:]
        elif part.startswith("flag:"):
            cond["flag"] = part[5:]
        else:
            m = re.match(r"^([a-z]+)\s*(>=|<=|>|<)\s*(-?\d+)$", part)
            if not m:
                raise ValueError("조건 해석 실패: %s" % part)
            key, op, val = m.group(1), m.group(2), int(m.group(3))
            if op in (">=", ">"):
                cond.setdefault("affMin", {})[key] = val + (1 if op == ">" else 0)
            else:
                cond.setdefault("affMax", {})[key] = val - (1 if op == "<" else 0)
    return cond


def main():
    files = sorted(os.listdir(SRC))
    files = [f for f in files if f.endswith(".txt")]
    c = Compiler()
    for f in files:
        with open(os.path.join(SRC, f), encoding="utf-8") as fp:
            lines = fp.read().split("\n")
        c.parse(lines, f)
    nodes = c.finish()

    meta_path = os.path.join(SRC, "meta.json")
    with open(meta_path, encoding="utf-8") as fp:
        meta = json.load(fp)
    meta["count"] = len(nodes)
    data = {"meta": meta, "nodes": nodes}
    with open(OUT, "w", encoding="utf-8") as fp:
        json.dump(data, fp, ensure_ascii=False, indent=1)
    print("nodes:", len(nodes), "->", OUT)
    if c.errors:
        print("ERRORS:")
        for e in c.errors:
            print(" -", e)
        sys.exit(1)


if __name__ == "__main__":
    main()
