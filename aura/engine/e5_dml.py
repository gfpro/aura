# aura/engine/e5_dml.py — Version 20261008v02 (Laengenstufen + Maske, Embedding auf der GPU)  (AURA)
# multilingual-e5-large (XLM-R-Encoder) komplett ueber DirectML (D3D12) in FP16.
# Gewichte: safetensors -> GPU (FP32 hochladen, auf der GPU nach FP16 wandeln). Formen werden je Tokenzahl T kompiliert.
import json, math, struct, time
from pathlib import Path
from . import dml
from .dml import T as TD, F16, F32, Op, ScaleBias
from .weights import SafeTensors

def f16(values): return struct.pack(f"<{len(values)}e", *values)

class E5DML:
    def __init__(self, model_dir, device=None, progress=print):
        self.dir = Path(model_dir); self.progress = progress
        self.cfg = json.loads((self.dir / "config.json").read_text(encoding="utf-8"))
        c = self.cfg; self.H, self.I, self.NH = c["hidden_size"], c["intermediate_size"], c["num_attention_heads"]
        self.L, self.eps, self.pad = c["num_hidden_layers"], c.get("layer_norm_eps", 1e-5), c.get("pad_token_id", 1)
        self.D = self.H // self.NH
        self.st = SafeTensors(self.dir / "model.safetensors")
        self.dev = device or dml.Device()
        self.plans = {}; self.casts = {}; self.w = None

    # ------------------------------------------------------------ Gewichte
    def _vec(self, name):
        b = self.dev.buffer(self.st.shape(name)[0] * 2); self.dev.upload(b, f16(self.st.floats(name))); return b

    def _mat(self, names):
        """Eine oder mehrere [out, in]-Matrizen untereinander in einen FP16-Puffer."""
        n = sum(self.st.shape(k)[0] * self.st.shape(k)[1] for k in names)
        dst = self.dev.buffer(n * 2)
        if all(self.st.dtype(k) == "F16" for k in names):
            off = 0
            for k in names: raw = bytes(self.st.raw(k)); self.dev.upload(dst, raw, off); off += len(raw)
            return dst
        if not hasattr(self, "_w32") or self._w32.size < n * 4: self._w32 = self.dev.buffer(n * 4)
        off = 0
        for k in names:
            raw = bytes(self.st.raw(k)) if self.st.dtype(k) == "F32" else f16(self.st.floats(k))   # F16 gemischt: selten
            self.dev.upload(self._w32, raw, off); off += len(raw)
        if n not in self.casts:
            self.casts[n] = Op(self.dev, "cast", In=TD((1, 1, 1, n), dtype=F32), Out=TD((1, 1, 1, n)))
        b = self.casts[n].bind([self._w32], [dst])
        L = self.dev.oneshot(); self.dev.set_heap(L); self.dev.dispatch(L, b); self.dev.run(L)
        return dst

    def load(self, layers=None):
        t0 = time.perf_counter(); self.nl = self.L if layers is None else layers
        if dml.SOFTMAX is None and not dml.selftest(self.dev, self.progress):
            raise RuntimeError("DirectML-Selbsttest fehlgeschlagen (Details im Log)")
        st, H = self.st, self.H
        self.ln_e = (self._vec("embeddings.LayerNorm.weight"), self._vec("embeddings.LayerNorm.bias"))
        self.type0 = st.floats("embeddings.token_type_embeddings.weight", 0, H)
        self.w = []
        for l in range(self.nl):
            p = f"encoder.layer.{l}."; a = p + "attention."
            qkv = [a + f"self.{x}" for x in ("query", "key", "value")]
            bq = []
            for k in qkv: bq.extend(st.floats(k + ".bias"))
            bqkv = self.dev.buffer(3 * H * 2); self.dev.upload(bqkv, f16(bq))
            self.w.append({
                "wqkv": self._mat([k + ".weight" for k in qkv]), "bqkv": bqkv,
                "wo": self._mat([a + "output.dense.weight"]), "bo": self._vec(a + "output.dense.bias"),
                "g1": self._vec(a + "output.LayerNorm.weight"), "b1": self._vec(a + "output.LayerNorm.bias"),
                "wi": self._mat([p + "intermediate.dense.weight"]), "bi": self._vec(p + "intermediate.dense.bias"),
                "wf": self._mat([p + "output.dense.weight"]), "bf": self._vec(p + "output.dense.bias"),
                "g2": self._vec(p + "output.LayerNorm.weight"), "b2": self._vec(p + "output.LayerNorm.bias")})
            self.progress(f"e5 (DirectML): Schicht {l + 1}/{self.nl} geladen")
        self.load_s = time.perf_counter() - t0

    # ------------------------------------------------------------ Rechenplan fuer eine Laengenstufe T
    BUCKETS = (32, 64, 128, 256, 512)
    MASK = -30000.0                                                   # FP16-tauglich; exp() -> 0

    def _postype(self):
        """Position + Token-Typ 0 fuer 512 Positionen, einmalig als FP16 auf die GPU."""
        H, n = self.H, self.BUCKETS[-1]
        pos = self.st.floats("embeddings.position_embeddings.weight", (self.pad + 1) * H, n * H)
        t = self.type0
        self.pos = self.dev.buffer(n * H * 2); self.dev.upload(self.pos, f16([pos[j] + t[j % H] for j in range(n * H)]))

    def _plan(self, T):
        if T in self.plans: return self.plans[T]
        d, H, I, NH, D = self.dev, self.H, self.I, self.NH, self.D
        if not hasattr(self, "pos"): self._postype()
        wf32 = self.st.dtype("embeddings.word_embeddings.weight") == "F32"
        B = lambda n: d.buffer(n * 2)
        b = {k: B(n) for k, n in (("w16", T * H), ("mask", T), ("e", T * H), ("x", T * H), ("qkv", T * 3 * H),
                                  ("s", NH * T * T), ("p", NH * T * T), ("ctx", T * H), ("a", T * H), ("a2", T * H),
                                  ("x1", T * H), ("h", T * I), ("er", T * I), ("g", T * I), ("h2", T * I), ("f", T * H),
                                  ("f2", T * H))}
        if wf32: b["w32"] = d.buffer(T * H * 4)
        bc = lambda n: TD((1, 1, T, n), (0, 0, 0, 1))                     # Bias, ueber alle Tokens verteilt
        row = lambda n: TD((1, 1, T, n))
        mvn = Op(d, "mvn", In=TD((T, 1, 1, H)), Scale=TD((T, 1, 1, H), (0, 0, 0, 1)), Bias=TD((T, 1, 1, H), (0, 0, 0, 1)),
                 Out=TD((T, 1, 1, H)), Cross=0, NormVar=1, Eps=self.eps)
        def lin(K, N): return Op(d, "gemm", A=row(K), B=TD((1, 1, N, K)), C=bc(N), Out=row(N), TA=0, TB=1, Alpha=1.0, Beta=1.0)
        qkvT = lambda: TD((1, NH, T, D), (0, D, 3 * H, 1))
        ops = {"mvn": mvn, "qkv": lin(H, 3 * H), "o": lin(H, H), "i": lin(H, I), "f": lin(I, H),
               "s": Op(d, "gemm", A=qkvT(), B=qkvT(), Out=TD((1, NH, T, T)), TA=0, TB=1, Alpha=1 / math.sqrt(D), Beta=0.0),
               "mask": Op(d, "add", A=TD((1, NH, T, T)), B=TD((1, NH, T, T), (0, 0, 0, 1)), Out=TD((1, NH, T, T))),
               "sm": dml.softmax_op(d, NH * T, T),
               "pv": Op(d, "gemm", A=TD((1, NH, T, T)), B=qkvT(), Out=TD((1, NH, T, D), (0, D, H, 1)), TA=0, TB=0,
                        Alpha=1.0, Beta=0.0),
               "add": Op(d, "add", A=row(H), B=row(H), Out=row(H)),
               "erf": Op(d, "erf", In=row(I), Out=row(I), SB=ScaleBias(1 / math.sqrt(2), 0.0)),
               "half": Op(d, "identity", In=row(I), Out=row(I), SB=ScaleBias(0.5, 0.5)),
               "mul": Op(d, "multiply", A=row(I), B=row(I), Out=row(I))}
        if wf32: ops["wcast"] = Op(d, "cast", In=TD((1, 1, T, H), dtype=F32), Out=row(H))
        L = dml.CmdList(d.dev, d._objs); d.set_heap(L)
        # Embedding auf der GPU: Wortvektoren (FP32->FP16) + Position/Typ, dann LayerNorm
        if wf32: d.dispatch(L, ops["wcast"].bind([b["w32"]], [b["w16"]]))
        d.dispatch(L, ops["add"].bind([b["w16"], self.pos], [b["e"]]))
        d.dispatch(L, mvn.bind([b["e"], self.ln_e[0], self.ln_e[1]], [b["x"]]))
        for w in self.w:
            seq = [("qkv", [b["x"], w["wqkv"], w["bqkv"]], b["qkv"]),
                   ("s", [b["qkv"], (b["qkv"], H * 2), None], b["s"]),
                   ("mask", [b["s"], b["mask"]], b["p"]),
                   ("sm", [b["p"]], b["s"]),
                   ("pv", [b["s"], (b["qkv"], 2 * H * 2), None], b["ctx"]),
                   ("o", [b["ctx"], w["wo"], w["bo"]], b["a"]),
                   ("add", [b["a"], b["x"]], b["a2"]),
                   ("mvn", [b["a2"], w["g1"], w["b1"]], b["x1"]),
                   ("i", [b["x1"], w["wi"], w["bi"]], b["h"]),
                   ("erf", [b["h"]], b["er"]),
                   ("half", [b["er"]], b["g"]),
                   ("mul", [b["h"], b["g"]], b["h2"]),
                   ("f", [b["h2"], w["wf"], w["bf"]], b["f"]),
                   ("add", [b["f"], b["x1"]], b["f2"]),
                   ("mvn", [b["f2"], w["g2"], w["b2"]], b["x"])]
            for name, ins, out in seq: d.dispatch(L, ops[name].bind(ins, [out]))
        L.close()
        self.plans[T] = plan = {"buf": b, "ops": ops, "list": L, "wf32": wf32}
        return plan

    # ------------------------------------------------------------ Rechnen
    @staticmethod
    def clip(ids, n=512):
        """Hoechstens n Tokens; das Schluss-Token (</s>) bleibt erhalten."""
        return ids if len(ids) <= n else ids[:n - 1] + ids[-1:]

    def hidden(self, ids):
        """Letzte Schicht fuer die n echten Tokens (Liste von n Zeilen). Gerechnet wird in der naechsten Laengenstufe,
        Fuelltokens sind per Maske unsichtbar. Zeitmessung in self.timing."""
        ids = self.clip(ids); n, H = len(ids), self.H
        T = next(t for t in self.BUCKETS if t >= n)
        t0 = time.perf_counter(); plan = self._plan(T); t1 = time.perf_counter()
        name = "embeddings.word_embeddings.weight"; es = 4 if plan["wf32"] else 2
        mv = self.st.raw(name); rb = H * es
        raw = b"".join(mv[t * rb:(t + 1) * rb] for t in ids) + bytes((T - n) * rb)
        b = plan["buf"]
        self.dev.upload(b["w32"] if plan["wf32"] else b["w16"], raw)
        self.dev.upload(b["mask"], f16([0.0] * n + [self.MASK] * (T - n))); t2 = time.perf_counter()
        self.dev.run(plan["list"]); t3 = time.perf_counter()
        raw = self.dev.download(b["x"], n * H * 2); t4 = time.perf_counter()
        x = struct.unpack(f"<{n * H}e", raw)
        self.timing = {"plan": t1 - t0, "cpu_embed": t2 - t1, "gpu": t3 - t2, "read": t4 - t3, "bucket": T}
        return [x[t * H:(t + 1) * H] for t in range(n)]

    def vector(self, ids):
        """e5: Mittelwert ueber alle echten Tokens, dann L2-normieren."""
        rows = self.hidden(ids); k = len(rows)
        v = [sum(c) / k for c in zip(*rows)]
        nrm = math.sqrt(sum(a * a for a in v)) or 1.0
        return [a / nrm for a in v]
