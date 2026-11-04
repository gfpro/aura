# aura/engine/whisper_dml.py — Version 20261104v175  (AURA)
# v176: Encoder in Teil-Listen je Schicht (Windows bricht GPU-Laeufe ueber ca. 2 s ab), Stufe im Fehlertext.
# Whisper (HF-safetensors) ueber DirectML in FP16, nur mit gemm/add/multiply/mvn/softmax/erf/identity aus dml.py.
# Faltungen werden als drei gegeneinander versetzte gemm gerechnet; Decoder mit K/V-Cache (feste Kapazitaet CAP).
import json, math, os, struct, time
from array import array
from pathlib import Path
from . import dml, mel
from .dml import T as TD, F32, Op, ScaleBias
from .weights import SafeTensors

def f16(v): return struct.pack(f"<{len(v)}e", *v)

class Whisper:
    CAP = 224                                                         # max. Tokens je 30-s-Abschnitt
    MASK = -30000.0
    CHUNK = 4096

    def __init__(self, model_dir, progress=print):
        self.dir = Path(model_dir); self.progress = progress
        c = self.cfg = json.loads((self.dir / "config.json").read_text(encoding="utf-8"))
        self.H, self.NM, self.EL, self.DL = c["d_model"], c["num_mel_bins"], c["encoder_layers"], c["decoder_layers"]
        self.NH, self.EI = c["encoder_attention_heads"], c["encoder_ffn_dim"]
        self.DI = c["decoder_ffn_dim"]; self.D = self.H // self.NH; self.TE = c.get("max_source_positions", 1500)
        self.st = SafeTensors(self.dir / "model.safetensors")
        self.dev = dml.Device(); self._cast = {}; self.timing = {}; self.stage = "Laden"; self.fl = 1
        self._tok()

    # ------------------------------------------------------------ Tokenizer
    def _tok(self):
        v = json.loads((self.dir / "vocab.json").read_text(encoding="utf-8"))
        add = json.loads((self.dir / "added_tokens.json").read_text(encoding="utf-8"))
        tid = {**v, **add}; self.inv = {i: t for t, i in v.items()}
        self.eot = tid["<|endoftext|>"]
        self.prompt = [tid["<|startoftranscript|>"], tid["<|de|>"], tid["<|transcribe|>"], tid["<|notimestamps|>"]]
        self.first_special = min(add.values())
        g = self.dir / "generation_config.json"; gc = json.loads(g.read_text(encoding="utf-8")) if g.exists() else {}
        self.suppress = set(gc.get("suppress_tokens") or []); self.begin = set(gc.get("begin_suppress_tokens") or [self.eot])
        bs = list(range(33, 127)) + list(range(161, 173)) + list(range(174, 256)); cs = bs[:]; n = 0
        for b in range(256):
            if b not in bs: bs.append(b); cs.append(256 + n); n += 1
        self.bd = {chr(c): b for b, c in zip(bs, cs)}

    def decode(self, ids):
        s = "".join(self.inv.get(i, "") for i in ids if i < self.first_special)
        return bytes(self.bd[c] for c in s if c in self.bd).decode("utf-8", "replace").strip()

    # ------------------------------------------------------------ Gewichte
    def _f(self, name, *a):
        return self.st.floats(name, *a)
    def _vec(self, name):
        b = self.dev.buffer(self.st.shape(name)[0] * 2); self.dev.upload(b, f16(self._f(name))); return b
    def _vecs(self, names):
        v = array("f")
        for k in names:                                               # Whisper: k_proj hat keinen Bias -> Nullen
            v.extend(self._f(k) if k in self.st.t else array("f", bytes(self.H * 4)))
        b = self.dev.buffer(len(v) * 2); self.dev.upload(b, f16(v)); return b
    def _mat(self, names):
        d = self.dev; n = 0
        for k in names: sh = self.st.shape(k); n += sh[0] * sh[1]
        dst = d.buffer(n * 2)
        if self.st.dtype(names[0]) == "F16":
            off = 0
            for k in names: r = bytes(self.st.raw(k)); d.upload(dst, r, off); off += len(r)
            return dst
        if getattr(self, "_w32", None) is None or self._w32.size < n * 4: self._w32 = d.buffer(n * 4)
        off = 0
        for k in names: r = bytes(self.st.raw(k)); d.upload(self._w32, r, off); off += len(r)
        if n not in self._cast: self._cast[n] = Op(d, "cast", self.fl, In=TD((1, 1, 1, n), dtype=F32), Out=TD((1, 1, 1, n)))
        b = self._cast[n].bind([self._w32], [dst]); L = d.oneshot(); d.set_heap(L); d.dispatch(L, b); d.run(L)
        return dst
    def _conv(self, name):
        """[out, in, 3] -> je Kernelposition ein dichter Puffer [out, in]."""
        w = self._f(name); out = []
        for k in range(3):
            b = self.dev.buffer(len(w) // 3 * 2); self.dev.upload(b, f16(w[k::3])); out.append(b)
        return out

    def _layer(self, p, cross):
        s = p + "self_attn."
        w = {"wqkv": self._mat([s + f"{x}_proj.weight" for x in "qkv"]), "bqkv": self._vecs([s + f"{x}_proj.bias" for x in "qkv"]),
             "wo": self._mat([s + "out_proj.weight"]), "bo": self._vec(s + "out_proj.bias"),
             "g1": self._vec(p + "self_attn_layer_norm.weight"), "b1": self._vec(p + "self_attn_layer_norm.bias"),
             "wi": self._mat([p + "fc1.weight"]), "bi": self._vec(p + "fc1.bias"),
             "wf": self._mat([p + "fc2.weight"]), "bf": self._vec(p + "fc2.bias"),
             "g2": self._vec(p + "final_layer_norm.weight"), "b2": self._vec(p + "final_layer_norm.bias")}
        if cross:
            c = p + "encoder_attn."
            w.update({"xk": self._mat([c + f"{x}_proj.weight" for x in "kv"]), "xkb": self._vecs([c + f"{x}_proj.bias" for x in "kv"]),
                      "xq": self._mat([c + "q_proj.weight"]), "xqb": self._vec(c + "q_proj.bias"),
                      "xo": self._mat([c + "out_proj.weight"]), "xob": self._vec(c + "out_proj.bias"),
                      "g3": self._vec(p + "encoder_attn_layer_norm.weight"), "b3": self._vec(p + "encoder_attn_layer_norm.bias")})
        return w

    def _chk(self, name):
        """v178: Diagnose - nach jedem Ladeschritt pruefen, ob die GPU noch lebt (Abstuerze zeigen sich verzoegert)."""
        self.stage = "Laden: " + name
        if not os.environ.get("AURA_DIAG"): return                    # v182: normal keine Pausen
        time.sleep(0.3)
        if getattr(self, "_ping", None) is None: self._ping = self.dev.buffer(16)
        self.dev.upload(self._ping, bytes(16)); self.progress(f"   ok: {name}")

    def load(self):
        t0 = time.perf_counter(); d = self.dev
        if dml.SOFTMAX is None and not dml.selftest(d, self.progress):
            raise RuntimeError("DirectML-Selbsttest fehlgeschlagen")
        self.c1 = self._conv("model.encoder.conv1.weight"); self.c1b = self._vec("model.encoder.conv1.bias")
        self.c2 = self._conv("model.encoder.conv2.weight"); self.c2b = self._vec("model.encoder.conv2.bias")
        self._chk("Faltungen")
        self.pos = d.buffer(self.TE * self.H * 2)
        d.upload(self.pos, f16(self._f("model.encoder.embed_positions.weight", 0, self.TE * self.H)))
        self.enc = [self._layer(f"model.encoder.layers.{i}.", False) for i in range(self.EL)]
        self._chk("Encoder-Gewichte")
        self.eg, self.eb = self._vec("model.encoder.layer_norm.weight"), self._vec("model.encoder.layer_norm.bias")
        self.dec = [self._layer(f"model.decoder.layers.{i}.", True) for i in range(self.DL)]
        self.dg, self.db = self._vec("model.decoder.layer_norm.weight"), self._vec("model.decoder.layer_norm.bias")
        self._chk("Decoder-Gewichte")
        self.emb = self._mat(["model.decoder.embed_tokens.weight"])
        self.V0 = self.st.shape("model.decoder.embed_tokens.weight")[0]
        Vp = (self.V0 + self.CHUNK - 1) // self.CHUNK * self.CHUNK    # v181: mit Nullzeilen auf volle Stuecke auffuellen
        e2 = d.buffer(Vp * self.H * 2); L = d.oneshot(); d.copy(L, e2, self.emb, self.V0 * self.H * 2); d.run(L); self.emb = e2
        self._chk("Wort-Matrix")
        self.V = Vp
        self._plan_enc(); self._chk("Encoder-Plan")
        self._plan_dec(); self._chk("Decoder-Plan")
        self.load_s = time.perf_counter() - t0; self.progress(f"Whisper geladen in {self.load_s:.1f} s")

    # ------------------------------------------------------------ Bausteine
    def _ops(self, T, I):
        d, H, NH, D = self.dev, self.H, self.NH, self.D
        return {"mvn": Op(d, "mvn", self.fl, In=TD((T, 1, 1, H)), Scale=TD((T, 1, 1, H), (0, 0, 0, 1)), Bias=TD((T, 1, 1, H), (0, 0, 0, 1)),
                          Out=TD((T, 1, 1, H)), Cross=0, NormVar=1, Eps=1e-5),
                "add": Op(d, "add", self.fl, A=self._r(T, H), B=self._r(T, H), Out=self._r(T, H)),
                "i": self._lin(T, H, I), "f": self._lin(T, I, H), "o": self._lin(T, H, H), "qkv": self._lin(T, H, 3 * H)}
    def _r(self, T, n): return TD((1, 1, T, n))
    def _lin(self, T, K, N):
        return Op(self.dev, "gemm", self.fl, A=self._r(T, K), B=TD((1, 1, N, K)), C=TD((1, 1, T, N), (0, 0, 0, 1)), Out=self._r(T, N),
                  TA=0, TB=1, Alpha=1.0, Beta=1.0)
    def _gelu(self, T, n):
        d = self.dev
        return (Op(d, "erf", self.fl, In=self._r(T, n), Out=self._r(T, n), SB=ScaleBias(1 / math.sqrt(2), 0.0)),
                Op(d, "identity", self.fl, In=self._r(T, n), Out=self._r(T, n), SB=ScaleBias(0.5, 0.5)),
                Op(d, "multiply", self.fl, A=self._r(T, n), B=self._r(T, n), Out=self._r(T, n)))
    def _attn(self, Tq, Tk, sq, sk, sv):
        """Operatoren s/sm/pv: q (Tq Zeilen, Zeilenabstand sq), k/v (Tk Zeilen, Abstand sk/sv); Ergebnis Tq x H."""
        d, H, NH, D = self.dev, self.H, self.NH, self.D
        qT = TD((1, NH, Tq, D), (0, D, sq, 1)); kT = TD((1, NH, Tk, D), (0, D, sk, 1)); vT = TD((1, NH, Tk, D), (0, D, sv, 1))
        return {"s": Op(d, "gemm", self.fl, A=qT, B=kT, Out=TD((1, NH, Tq, Tk)), TA=0, TB=1, Alpha=1 / math.sqrt(D), Beta=0.0),
                "sm": dml.softmax_op(d, NH * Tq, Tk),
                "pv": Op(d, "gemm", self.fl, A=TD((1, NH, Tq, Tk)), B=vT, Out=TD((1, NH, Tq, D), (0, D, H, 1)), TA=0, TB=0, Alpha=1.0, Beta=0.0)}

    # ------------------------------------------------------------ Encoder
    def _plan_enc(self):
        d, H, N, TE = self.dev, self.H, self.NM, self.TE; TM = TE * 2
        BF = lambda n: d.buffer(n * 2)
        b = self.eb_ = {"mel": BF((TM + 2) * N), "x": BF(TE * H)}
        for k, n in (("c0", TM * H), ("c1", TM * H), ("c2", TM * H), ("ca", TM * H), ("cb", TM * H), ("cc", TM * H), ("cd", TM * H),
                     ("cp", (TM + 2) * H), ("d0", TE * H), ("d1", TE * H), ("d2", TE * H), ("da", TE * H), ("db", TE * H),
                     ("dc", TE * H), ("dd", TE * H), ("e", TE * H),
                     ("n", TE * H), ("qkv", TE * 3 * H), ("s", self.NH * TE * TE), ("sp", self.NH * TE * TE), ("ctx", TE * H), ("a", TE * H), ("x1", TE * H),
                     ("h", TE * self.EI), ("er", TE * self.EI), ("g", TE * self.EI), ("h2", TE * self.EI), ("f", TE * H)):
            b[k] = BF(n)
        z = dict(TA=0, TB=1, Alpha=1.0, Beta=0.0)
        o1 = Op(d, "gemm", self.fl, A=self._r(TM, N), B=TD((1, 1, H, N)), Out=self._r(TM, H), **z)
        add1 = Op(d, "add", self.fl, A=self._r(TM, H), B=self._r(TM, H), Out=self._r(TM, H))
        addb = Op(d, "add", self.fl, A=self._r(TM, H), B=TD((1, 1, TM, H), (0, 0, 0, 1)), Out=self._r(TM, H))
        g1 = self._gelu(TM, H)
        A2 = lambda: TD((1, 1, TE, H), (0, 0, 2 * H, 1))
        o2 = Op(d, "gemm", self.fl, A=A2(), B=TD((1, 1, H, H)), Out=self._r(TE, H), **z)
        add2 = Op(d, "add", self.fl, A=self._r(TE, H), B=self._r(TE, H), Out=self._r(TE, H))
        addb2 = Op(d, "add", self.fl, A=self._r(TE, H), B=TD((1, 1, TE, H), (0, 0, 0, 1)), Out=self._r(TE, H))
        g2 = self._gelu(TE, H)
        cpy = Op(d, "identity", self.fl, In=self._r(TM, H), Out=self._r(TM, H))
        ops = self._ops(TE, self.EI); ops.update(self._attn(TE, TE, 3 * H, 3 * H, 3 * H)); ge = self._gelu(TE, self.EI)
        self.lenc = []
        def neu():
            nonlocal L
            if L is not None: L.close()
            L = dml.CmdList(d.dev, d._objs); d.set_heap(L); self.lenc.append(L)
        L = None; neu(); D = lambda op, i, o: d.dispatch(L, op.bind(i, [o]))
        for k in range(3): D(o1, [(b["mel"], k * N * 2), self.c1[k], None], b[f"c{k}"])
        D(add1, [b["c0"], b["c1"]], b["ca"]); D(add1, [b["ca"], b["c2"]], b["cb"]); D(addb, [b["cb"], self.c1b], b["cc"])
        D(g1[0], [b["cc"]], b["ca"]); D(g1[1], [b["ca"]], b["cb"]); D(g1[2], [b["cc"], b["cb"]], b["cd"])
        neu()
        D(cpy, [b["cd"]], (b["cp"], H * 2))                           # eine Nullzeile vorne/hinten = Padding
        for k in range(3): D(o2, [(b["cp"], k * H * 2), self.c2[k], None], b[f"d{k}"])
        D(add2, [b["d0"], b["d1"]], b["da"]); D(add2, [b["da"], b["d2"]], b["db"]); D(addb2, [b["db"], self.c2b], b["dc"])
        D(g2[0], [b["dc"]], b["da"]); D(g2[1], [b["da"]], b["db"]); D(g2[2], [b["dc"], b["db"]], b["dd"])
        D(ops["add"], [b["dd"], self.pos], b["x"])
        H2 = H * 2
        for w in self.enc:
            neu()
            for n, i, o in [("mvn", [b["x"], w["g1"], w["b1"]], "n"), ("qkv", [b["n"], w["wqkv"], w["bqkv"]], "qkv"),
                            ("s", [b["qkv"], (b["qkv"], H2), None], "s")]:
                D(ops[n], i, b[o])
            D(ops["sm"], [b["s"]], b["sp"])
            D(ops["pv"], [b["sp"], (b["qkv"], 2 * H2), None], b["ctx"])
            D(ops["o"], [b["ctx"], w["wo"], w["bo"]], b["a"]); D(ops["add"], [b["a"], b["x"]], b["x1"])
            D(ops["mvn"], [b["x1"], w["g2"], w["b2"]], b["n"]); D(ops["i"], [b["n"], w["wi"], w["bi"]], b["h"])
            D(ge[0], [b["h"]], b["er"]); D(ge[1], [b["er"]], b["g"]); D(ge[2], [b["h"], b["g"]], b["h2"])
            D(ops["f"], [b["h2"], w["wf"], w["bf"]], b["f"]); D(ops["add"], [b["f"], b["x1"]], b["x"])
        D(ops["mvn"], [b["x"], self.eg, self.eb], b["n"])             # Ergebnis: b["n"]
        L.close()

    def encode(self, mel_rows):
        t0 = time.perf_counter(); b = self.eb_; N = self.NM
        raw = bytes(N * 2) + b"".join(struct.pack(f"<{N}e", *r) for r in mel_rows) + bytes(N * 2)
        self.dev.upload(b["mel"], raw); z = []
        for i, L in enumerate(self.lenc):
            self.stage = f"Encoder-Teil {i + 1}/{len(self.lenc)}"; t1 = time.perf_counter()
            self.dev.run(L); z.append(round(time.perf_counter() - t1, 2))
        self.timing["teile"] = z; self.stage = "Decoder"
        self.timing["encoder"] = time.perf_counter() - t0

    # ------------------------------------------------------------ Decoder
    def _plan_dec(self):
        d, H, C, TE = self.dev, self.H, self.CAP, self.TE; NH = self.NH
        BF = lambda n: d.buffer(n * 2); b = self.db_ = {}
        self.fl = 3                                                   # v179: Decoder ohne Treiber-Metacommands
        for k, n in (("x", H), ("n", H), ("qkv", 3 * H), ("s", NH * C), ("sp", NH * C), ("p", NH * C), ("mask", C), ("ctx", H), ("a", H),
                     ("x1", H), ("x2", H), ("xs", NH * TE), ("xp", NH * TE), ("xq", H), ("h", self.DI), ("er", self.DI), ("g", self.DI),
                     ("h2", self.DI), ("f", H), ("out", H), ("log", self.V)):
            b[k] = BF(n)
        ops = self._ops(1, self.DI); ge = self._gelu(1, self.DI); a = self._attn(1, C, 3 * H, H, H); x = self._attn(1, TE, H, 2 * H, 2 * H)
        self._chk("Decoder-Operatoren 1")
        lq = self._lin(1, H, H)
        mk = Op(d, "add", self.fl, A=TD((1, NH, 1, C)), B=TD((1, NH, 1, C), (0, 0, 0, 1)), Out=TD((1, NH, 1, C)))
        self.cpy = Op(d, "identity", self.fl, In=self._r(1, H), Out=self._r(1, H))
        def lop(n): return Op(d, "gemm", self.fl, A=self._r(1, H), B=TD((1, 1, n, H)), Out=self._r(1, n), TA=0, TB=1, Alpha=1.0, Beta=0.0)
        self._chk("Decoder-Operatoren 2")
        self.rows = {}; self.kv = [(BF(C * H), BF(C * H)) for _ in self.dec]
        self.xkv = [BF(TE * 2 * H) for _ in self.dec]
        self.dseq = []                                                # pro Schicht: vor Cache-Schreiben / danach
        seen = set()
        def S(op, i, o):
            r = op.bind(i, [o])
            if id(op) not in seen: seen.add(id(op)); self._chk(f"Init {op.kind} {[getattr(v, 'sizes', '') for v in op.keep[:2]]}")
            return r
        H2 = H * 2; E = self.eb_["n"]
        kl = self._lin(TE, H, 2 * H); L = self.lx = dml.CmdList(d.dev, d._objs); d.set_heap(L)
        for w, bx in zip(self.dec, self.xkv): d.dispatch(L, kl.bind([E, w["xk"], w["xkb"]], [bx]))
        L.close()
        for w, (K, Va), bx in zip(self.dec, self.kv, self.xkv):
            pre = [S(ops["mvn"], [b["x"], w["g1"], w["b1"]], b["n"]), S(ops["qkv"], [b["n"], w["wqkv"], w["bqkv"]], b["qkv"])]
            post = [S(a["s"], [b["qkv"], K, None], b["s"]), S(mk, [b["s"], b["mask"]], b["p"]), S(a["sm"], [b["p"]], b["sp"]),
                    S(a["pv"], [b["sp"], Va, None], b["ctx"]), S(ops["o"], [b["ctx"], w["wo"], w["bo"]], b["a"]),
                    S(ops["add"], [b["a"], b["x"]], b["x1"]),
                    S(ops["mvn"], [b["x1"], w["g3"], w["b3"]], b["n"]), S(lq, [b["n"], w["xq"], w["xqb"]], b["xq"]),
                    S(x["s"], [b["xq"], bx, None], b["xs"]), S(x["sm"], [b["xs"]], b["xp"]),
                    S(x["pv"], [b["xp"], (bx, H2), None], b["ctx"]), S(ops["o"], [b["ctx"], w["xo"], w["xob"]], b["a"]),
                    S(ops["add"], [b["a"], b["x1"]], b["x2"]),
                    S(ops["mvn"], [b["x2"], w["g2"], w["b2"]], b["n"]), S(ops["i"], [b["n"], w["wi"], w["bi"]], b["h"]),
                    S(ge[0], [b["h"]], b["er"]), S(ge[1], [b["er"]], b["g"]), S(ge[2], [b["h"], b["g"]], b["h2"]),
                    S(ops["f"], [b["h2"], w["wf"], w["bf"]], b["f"]), S(ops["add"], [b["f"], b["x2"]], b["x"])]
            self.dseq.append((pre, post, K, Va))
        # v180: Wort-Matrix in Stuecken (am Stueck stuerzt der Treiber bei der Vorbereitung ab)
        self.dfin = [S(ops["mvn"], [b["x"], self.dg, self.db], b["out"])]; C_ = self.CHUNK; vops = {}
        for a0 in range(0, self.V, C_):
            n = min(C_, self.V - a0); o = vops.get(n) or vops.setdefault(n, lop(n))
            self.dfin.append(S(o, [b["out"], (self.emb, a0 * H * 2), None], (b["log"], a0 * 2)))
        self._chk("Decoder-Bindungen")
        self.Ls = dml.CmdList(d.dev, d._objs); self.Ls_used = False

    def _row(self, src, off, dst, t):
        key = (id(src), off, id(dst), t); r = self.rows.get(key)
        if r is None: r = self.rows[key] = self.cpy.bind([(src, off)], [(dst, t * self.H * 2)])
        return r

    def _step(self, tok, t):
        d, b, H = self.dev, self.db_, self.H
        e = self._f("model.decoder.embed_tokens.weight", tok * H, H); p = self._f("model.decoder.embed_positions.weight", t * H, H)
        d.upload(b["x"], f16([u + v for u, v in zip(e, p)]))
        d.upload(b["mask"], f16([0.0] * (t + 1) + [self.MASK] * (self.CAP - t - 1)))
        L = self.Ls
        if self.Ls_used: L.reset()
        self.Ls_used = True; d.set_heap(L)
        for pre, post, K, Va in self.dseq:
            for x in pre: d.dispatch(L, x)
            d.dispatch(L, self._row(b["qkv"], H * 2, K, t)); d.dispatch(L, self._row(b["qkv"], H * 4, Va, t))
            for x in post: d.dispatch(L, x)
        for x in self.dfin: d.dispatch(L, x)
        d.run(L)
        return struct.unpack(f"<{self.V0}e", d.download(b["log"], self.V0 * 2))

    def generate(self, on_token=None):
        d = self.dev; t0 = time.perf_counter()
        d.run(self.lx); out = []
        for t, tok in enumerate(self.prompt): lg = self._step(tok, t)
        t1 = time.perf_counter(); t = len(self.prompt)
        while t < self.CAP:
            ban = self.suppress | (self.begin if not out else set())
            best, tok = -1e9, self.eot
            for i, v in enumerate(lg):
                if v > best and i not in ban: best, tok = v, i
            if tok == self.eot: break
            out.append(tok)
            if on_token: on_token(self.decode(out))
            lg = self._step(tok, t); t += 1
        t2 = time.perf_counter()
        self.timing.update(prompt=t1 - t0, decoder=t2 - t1, tokens=len(out))
        return out

    def transcribe(self, wav, on_token=None):
        """Nur die ersten 30 s. Rueckgabe: Text; Zeiten in self.timing."""
        t0 = time.perf_counter(); s = mel.read_wav(wav)
        rows, _ = mel.log_mel(s, self.NM); self.timing = {"audio": len(s) / mel.SR, "mel": time.perf_counter() - t0}
        self.encode(rows); return self.decode(self.generate(on_token))

    def close(self):
        self.dev.close()
