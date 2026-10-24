# aura/llm/qwen.py — Version 20261024v118  (AURA)
#   v118: Qwen3Engine entfernt; Kernels/Hilfen bleiben (von qwen35.py genutzt).
#   v86: Einlesen mit fp16-KV: eigener gemm-Kernel liest je uint 2 Werte (statt je Wert ein uint), wie K_LINEAR2.
#  
#   v85: KV-Cache in 16 Bit (fp16, 2 Werte je uint), Einstellung llm_kv16 (Standard an). Halber Speicher fuer den
#        KV-Cache; alle Attention-Kernels lesen ueber LD_K/LD_V. Alte .kv-Dateien (fp32) werden verworfen.
#  
#   v84: Split-K «splitr»: Block-Maximum per gemeinsamer Reduktion statt 128-mal je Thread. Varianten splitr_128/_64.
#  
#   v83: Split-K mit mehr Parallelitaet: Varianten split (256 Pos., max. 64 Teile), split_128 (128/128), split_64 (64/128).
#        Selbsttest misst alle und waehlt die schnellste gleiche (v82 split2 verworfen: 3,4x langsamer).
#    v28: Kontext bis 32k, Attention v1 nur bis 4k
#   v70: 8-Bit-Gewichte (int8 + 1 Skala je 128 Werte, symmetrisch). Umrechnung beim Laden auf der GPU (kein zweiter
#        Modellordner). Eigene Kernels fuer Schreiben (K_MV8), kleine Bloecke (K_MVT8) und Einlesen (k_linear8).
#        Selbsttest: int8 gegen bf16 (Genauigkeit) und die int8-Varianten untereinander (Tempo). Ohne Erfolg -> bf16.
#   v42: Split-K-Attention beim Schreiben (1 Token): Positionen auf viele GPU-Gruppen verteilt, danach zusammengefuehrt.
#        Selbsttest vergleicht mit v2 und waehlt nur, wenn gleich und schneller.
#   v43: Prompt-Cache. kv_ids merkt sich, welche Tokens im KV-Cache stehen; prefill liest nur den neuen Teil.
#        save_kv/load_kv: KV-Cache eines festen Vorspanns auf der Festplatte (data\kvcache).
#   v44: Attention beim Einlesen als Matrixmultiplikation («gemm»: S = Q·K^T, Softmax, O = S·V) statt Token fuer Token.
#        (Der Kachel-Kernel v3 aus v44b war auf Intel langsamer als v2 und ist entfernt.) Selbsttest vergleicht mit v2
#        bei langem Kontext und waehlt gemm nur, wenn gleich und schneller.
#   v44d: Gewichte fuer kleine Bloecke (2..64 Tokens, z.B. JSON-Geruest zwischen Feldern): K_MATVEC_T liest jede
#        Gewichtszeile einmal fuer bis zu 16 Tokens statt eine ganze 128er-Kachel zu rechnen. Selbsttest wie oben.
#   v44e: Split-K-Attention auch fuer kleine Bloecke (2..16 Tokens, Dispatch-Achse z = Token). T = 1 wie bisher.
# Native Qwen3-Engine (Qwen3ForCausalLM) auf DirectX 11 ueber ctypes - keine Installation.
# Gewichte bleiben bf16 (wie heruntergeladen) und werden erst in den GPU-Kernels zu float umgerechnet.
# Bausteine: RMSNorm, Q/K-Norm + RoPE, gruppierte Attention mit KV-Cache, SwiGLU, Prefill in Bloecken.

import ctypes, heapq, json, math, mmap, random, struct
from array import array
from pathlib import Path
from ..engine.gpu import GPU

MAXT = 32768         # Obergrenze Kontext (Prompt + Antwort); tatsaechlich: maxT-Parameter (native.py, llm_context)
ATTN1_MAX = 4096     # alter Attention-Kernel v1: groupshared-Puffer begrenzt auf 4096 Positionen
CHUNK = 512          # Prefill-Blockgroesse (Tokens pro Durchgang)
LMH_ROWS = 16384     # lm_head in Bloecke teilen (D3D11: max. 128 MB pro Puffer garantiert)
NSPLIT_MAX = 128     # v83: hoechstens so viele Teilstuecke je KV-Kopf (v42: 64)
SPLITS = {"split": (256, 64), "split_128": (128, 128), "split_64": (64, 128),
          "splitr_128": (128, 128), "splitr_64": (64, 128)}                 # v84: splitr = Kernel mit Reduktion   # v83: (min. Positionen je Teil, max. Teile)
SPLIT_MIN = 512      # v42: darunter lohnt Split-K nicht (Kontext kurz)
SPLIT_T = 16         # v44e: Split-K fuer bis zu so vielen Tokens je Durchgang
SMALL_MAX = 64       # v44d: bis so viele Tokens je Durchgang -> K_MATVEC_T (in Teilen zu 16)
PRE_MIN = 64         # v44: Attention gemm erst ab so vielen Tokens je Durchgang (kurze Stuecke: v2 reicht)

# ----------------------------------------------------------------------------- HLSL-Kernels
_BF = "float lo(uint u){return asfloat(u<<16);} float hi(uint u){return asfloat(u&0xffff0000);}\n"

K_LINEAR = _BF + r"""
cbuffer C:register(b0){ uint T; uint IN; uint OUT; uint PAD; };
RWStructuredBuffer<float> X:register(u0); RWStructuredBuffer<uint> W:register(u1);
RWStructuredBuffer<float> Y:register(u2);
groupshared float As[16][64]; groupshared float Ws[16][64];
[numthreads(16,16,1)]
void main(uint3 g:SV_GroupID, uint3 l:SV_GroupThreadID, uint li:SV_GroupIndex){
  uint t0=g.y*64, o0=g.x*64, i, j, r;
  float acc[4][4];
  [unroll] for(i=0;i<4;i++) [unroll] for(j=0;j<4;j++) acc[i][j]=0;
  for(uint k0=0;k0<IN;k0+=16){
    [unroll] for(r=0;r<4;r++){ uint idx=li+256*r; uint row=idx>>4, kk=idx&15; uint t=t0+row;
      As[kk][row]=(t<T)?X[t*IN+k0+kk]:0; }
    [unroll] for(r=0;r<2;r++){ uint idx=li+256*r; uint row=idx>>3, kp=idx&7; uint o=o0+row;
      uint u=(o<OUT)?W[(o*IN+k0)/2+kp]:0; Ws[kp*2][row]=lo(u); Ws[kp*2+1][row]=hi(u); }
    GroupMemoryBarrierWithGroupSync();
    [unroll] for(uint kk=0;kk<16;kk++){
      float a[4], w[4];
      [unroll] for(i=0;i<4;i++){ a[i]=As[kk][l.y+16*i]; w[i]=Ws[kk][l.x+16*i]; }
      [unroll] for(i=0;i<4;i++) [unroll] for(j=0;j<4;j++) acc[i][j]+=a[i]*w[j];
    }
    GroupMemoryBarrierWithGroupSync();
  }
  [unroll] for(i=0;i<4;i++){ uint t=t0+l.y+16*i;
    [unroll] for(j=0;j<4;j++){ uint o=o0+l.x+16*j; if(t<T&&o<OUT) Y[t*OUT+o]=acc[i][j]; } }
}"""

K_MATVEC = _BF + r"""
cbuffer C:register(b0){ uint IN; uint YOFF; uint XOFF; uint PAD; };
RWStructuredBuffer<float> X:register(u0); RWStructuredBuffer<uint> W:register(u1);
RWStructuredBuffer<float> Y:register(u2);
groupshared float red[256];
[numthreads(256,1,1)]
void main(uint3 g:SV_GroupID, uint3 l:SV_GroupThreadID){
  uint o=g.x, i=l.x, h=IN/2, wb=o*h; float acc=0;
  for(uint p=i;p<h;p+=256){ uint u=W[wb+p]; acc+=X[XOFF+2*p]*lo(u)+X[XOFF+2*p+1]*hi(u); }
  red[i]=acc; GroupMemoryBarrierWithGroupSync();
  for(uint a=128;a>0;a>>=1){ if(i<a) red[i]+=red[i+a]; GroupMemoryBarrierWithGroupSync(); }
  if(i==0) Y[YOFF+o]=red[0];
}"""

# v44d: Matrix x wenige Tokens. Gruppe = 8 Ausgabezeilen; 256 Threads = 64 Gewichtspaare x 4 Zeilenpaare.
# Die Tokens T0..T0+T-1 (T <= 16) liegen je 128 Spalten im Gruppenspeicher; jede Gewichtszeile wird einmal gelesen.
K_MATVEC_T = _BF + r"""
cbuffer C:register(b0){ uint T; uint IN; uint OUT; uint T0; };
RWStructuredBuffer<float> X:register(u0); RWStructuredBuffer<uint> W:register(u1);
RWStructuredBuffer<float> Y:register(u2);
groupshared float Xs[16][130]; groupshared float red[256][17];
[numthreads(256,1,1)]
void main(uint3 g:SV_GroupID, uint3 l:SV_GroupThreadID){
  uint i=l.x, p=i&63, rg=i>>6, o0=g.x*8, h=IN/2, t, r, k0;
  uint oa=o0+rg*2, ob=oa+1;
  float a0[16], a1[16];
  [unroll] for(t=0;t<16;t++){ a0[t]=0; a1[t]=0; }
  for(k0=0;k0<IN;k0+=128){
    [unroll] for(r=0;r<8;r++){ uint idx=i+256*r; uint tt=idx>>7, kk=idx&127;
      Xs[tt][kk]=(tt<T&&k0+kk<IN)?X[(T0+tt)*IN+k0+kk]:0; }
    GroupMemoryBarrierWithGroupSync();
    uint pp=k0/2+p;
    uint ua=(oa<OUT&&pp<h)?W[oa*h+pp]:0, ub=(ob<OUT&&pp<h)?W[ob*h+pp]:0;
    float wa0=lo(ua), wa1=hi(ua), wb0=lo(ub), wb1=hi(ub);
    [unroll] for(t=0;t<16;t++){ float x0=Xs[t][2*p], x1=Xs[t][2*p+1]; a0[t]+=x0*wa0+x1*wa1; a1[t]+=x0*wb0+x1*wb1; }
    GroupMemoryBarrierWithGroupSync();
  }
  [unroll] for(r=0;r<2;r++){
    [unroll] for(t=0;t<16;t++) red[i][t]=(r==0)?a0[t]:a1[t];
    GroupMemoryBarrierWithGroupSync();
    if(i<64){ uint g2=i>>4, tt=i&15; float s=0; for(uint q=0;q<64;q++) s+=red[g2*64+q][tt];
      uint o=o0+g2*2+r; if(tt<T&&o<OUT) Y[(T0+tt)*OUT+o]=s; }
    GroupMemoryBarrierWithGroupSync();
  }
}"""

K_RMS = r"""
cbuffer C:register(b0){ uint T; uint H; float EPS; uint ADD; };
RWStructuredBuffer<float> A:register(u0); RWStructuredBuffer<float> R:register(u1);
RWStructuredBuffer<float> G:register(u2); RWStructuredBuffer<float> Y:register(u3);
groupshared float red[256];
[numthreads(256,1,1)]
void main(uint3 g:SV_GroupID, uint3 l:SV_GroupThreadID){
  uint t=g.x, i=l.x, k; float s=0;
  for(k=i;k<H;k+=256){ float v=R[t*H+k]; if(ADD){ v+=A[t*H+k]; R[t*H+k]=v; } s+=v*v; }
  red[i]=s; GroupMemoryBarrierWithGroupSync();
  for(uint a=128;a>0;a>>=1){ if(i<a) red[i]+=red[i+a]; GroupMemoryBarrierWithGroupSync(); }
  float r=rsqrt(red[0]/H+EPS);
  for(k=i;k<H;k+=256) Y[t*H+k]=R[t*H+k]*r*G[k];
}"""

K_QKROPE = r"""
cbuffer C:register(b0){ uint T; uint NHD; uint POS0; float EPS; };
RWStructuredBuffer<float> X:register(u0); RWStructuredBuffer<float> G:register(u1);
RWStructuredBuffer<float> CS:register(u2);
groupshared float red[64];
[numthreads(64,1,1)]
void main(uint3 g:SV_GroupID, uint3 l:SV_GroupThreadID){
  uint t=g.x, h=g.y, i=l.x, base=(t*NHD+h)*128;
  float a=X[base+i], b=X[base+i+64];
  red[i]=a*a+b*b; GroupMemoryBarrierWithGroupSync();
  for(uint s2=32;s2>0;s2>>=1){ if(i<s2) red[i]+=red[i+s2]; GroupMemoryBarrierWithGroupSync(); }
  float r=rsqrt(red[0]/128.0+EPS);
  a=a*r*G[i]; b=b*r*G[i+64];
  uint p=(POS0+t)*64+i; float c=CS[2*p], s=CS[2*p+1];
  X[base+i]=a*c-b*s; X[base+i+64]=b*c+a*s;
}"""

K_ATTN = r"""
cbuffer C:register(b0){ uint T; uint POS0; uint NH; uint NKV; };
RWStructuredBuffer<float> Q:register(u0); RWStructuredBuffer<float> K:register(u1);
RWStructuredBuffer<float> V:register(u2); RWStructuredBuffer<float> O:register(u3);
groupshared float q[128]; groupshared float s[%d]; groupshared float red[128];
[numthreads(128,1,1)]
void main(uint3 g:SV_GroupID, uint3 l:SV_GroupThreadID){
  uint t=g.x, h=g.y, i=l.x, j, k, a;
  uint kvh=h/(NH/NKV), QD=NH*128, KD=NKV*128, P=POS0+t, kb=kvh*128;
  q[i]=Q[t*QD+h*128+i]; GroupMemoryBarrierWithGroupSync();
  float m=-1e30;
  for(j=i;j<=P;j+=128){ float d=0; for(k=0;k<128;k++) d+=q[k]*K[j*KD+kb+k]; d*=0.08838834764831845; s[j]=d; m=max(m,d); }
  red[i]=m; GroupMemoryBarrierWithGroupSync();
  for(a=64;a>0;a>>=1){ if(i<a) red[i]=max(red[i],red[i+a]); GroupMemoryBarrierWithGroupSync(); }
  m=red[0]; GroupMemoryBarrierWithGroupSync();
  float z=0; for(j=i;j<=P;j+=128){ float e=exp(s[j]-m); s[j]=e; z+=e; }
  red[i]=z; GroupMemoryBarrierWithGroupSync();
  for(a=64;a>0;a>>=1){ if(i<a) red[i]+=red[i+a]; GroupMemoryBarrierWithGroupSync(); }
  z=red[0];
  float acc=0; for(j=0;j<=P;j++) acc+=s[j]*V[j*KD+kb+i];
  O[t*QD+h*128+i]=acc/z;
}""" % ATTN1_MAX

# Schnellerer Matrix-Kernel fuer das Einlesen: Kachel 128 Tokens x 64 Ausgaben, je Thread 8 x 4 (float4).
K_LINEAR2 = _BF + r"""
cbuffer C:register(b0){ uint T; uint IN; uint OUT; uint PAD; };
RWStructuredBuffer<float> X:register(u0); RWStructuredBuffer<uint> W:register(u1);
RWStructuredBuffer<float> Y:register(u2);
groupshared float4 As[16][32]; groupshared float4 Ws[16][16];
[numthreads(16,16,1)]
void main(uint3 g:SV_GroupID, uint3 l:SV_GroupThreadID, uint li:SV_GroupIndex){
  uint t0=g.y*128, o0=g.x*64, i, r, c;
  float4 acc[8];
  [unroll] for(i=0;i<8;i++) acc[i]=0;
  uint h=IN/2;
  for(uint k0=0;k0<IN;k0+=16){
    [unroll] for(r=0;r<2;r++){ uint sl=li+256*r; uint kk=sl&15, q=sl>>4; uint t=t0+4*q; float4 v;
      v.x=(t  <T)?X[(t  )*IN+k0+kk]:0; v.y=(t+1<T)?X[(t+1)*IN+k0+kk]:0;
      v.z=(t+2<T)?X[(t+2)*IN+k0+kk]:0; v.w=(t+3<T)?X[(t+3)*IN+k0+kk]:0; As[kk][q]=v; }
    if(li<128){ uint kp=li&7, oq=li>>3; uint o=o0+4*oq, b=k0/2+kp; uint u0,u1,u2,u3;
      u0=(o  <OUT)?W[(o  )*h+b]:0; u1=(o+1<OUT)?W[(o+1)*h+b]:0;
      u2=(o+2<OUT)?W[(o+2)*h+b]:0; u3=(o+3<OUT)?W[(o+3)*h+b]:0;
      Ws[2*kp][oq]=float4(lo(u0),lo(u1),lo(u2),lo(u3)); Ws[2*kp+1][oq]=float4(hi(u0),hi(u1),hi(u2),hi(u3)); }
    GroupMemoryBarrierWithGroupSync();
    [unroll] for(uint kk=0;kk<16;kk++){
      float4 a0=As[kk][l.y*2], a1=As[kk][l.y*2+1], w=Ws[kk][l.x];
      acc[0]+=a0.x*w; acc[1]+=a0.y*w; acc[2]+=a0.z*w; acc[3]+=a0.w*w;
      acc[4]+=a1.x*w; acc[5]+=a1.y*w; acc[6]+=a1.z*w; acc[7]+=a1.w*w;
    }
    GroupMemoryBarrierWithGroupSync();
  }
  [unroll] for(i=0;i<8;i++){ uint t=t0+l.y*8+i; if(t<T){
    [unroll] for(c=0;c<4;c++){ uint o=o0+l.x*4+c; if(o<OUT) Y[t*OUT+o]=acc[i][c]; } } }
}"""

def k_linear_tiled(TM, TN):
    """Matrix-Kernel-Familie wie v1 (konfliktfreie Einzelzugriffe), aber TM x TN Werte je Thread.
    Kachel = 16*TM Tokens x 16*TN Ausgaben. v1 entspricht TM = TN = 4."""
    BT, BO = 16 * TM, 16 * TN
    return _BF + r"""
cbuffer C:register(b0){ uint T; uint IN; uint OUT; uint PAD; };
RWStructuredBuffer<float> X:register(u0); RWStructuredBuffer<uint> W:register(u1);
RWStructuredBuffer<float> Y:register(u2);
groupshared float As[16][%(BT)d]; groupshared float Ws[16][%(BO)d];
[numthreads(16,16,1)]
void main(uint3 g:SV_GroupID, uint3 l:SV_GroupThreadID, uint li:SV_GroupIndex){
  uint t0=g.y*%(BT)d, o0=g.x*%(BO)d, i, j, r, h=IN/2;
  float acc[%(TM)d][%(TN)d];
  [unroll] for(i=0;i<%(TM)d;i++) [unroll] for(j=0;j<%(TN)d;j++) acc[i][j]=0;
  for(uint k0=0;k0<IN;k0+=16){
    [unroll] for(r=0;r<%(TM)d;r++){ uint idx=li+256*r; uint row=idx>>4, kk=idx&15; uint t=t0+row;
      As[kk][row]=(t<T)?X[t*IN+k0+kk]:0; }
    [unroll] for(r=0;r<%(TN2)d;r++){ uint idx=li+256*r; uint row=idx>>3, kp=idx&7; uint o=o0+row;
      uint u=(o<OUT)?W[o*h+k0/2+kp]:0; Ws[kp*2][row]=lo(u); Ws[kp*2+1][row]=hi(u); }
    GroupMemoryBarrierWithGroupSync();
    [unroll] for(uint kk=0;kk<16;kk++){
      float a[%(TM)d], w[%(TN)d];
      [unroll] for(i=0;i<%(TM)d;i++) a[i]=As[kk][l.y+16*i];
      [unroll] for(j=0;j<%(TN)d;j++) w[j]=Ws[kk][l.x+16*j];
      [unroll] for(i=0;i<%(TM)d;i++) [unroll] for(j=0;j<%(TN)d;j++) acc[i][j]+=a[i]*w[j];
    }
    GroupMemoryBarrierWithGroupSync();
  }
  [unroll] for(i=0;i<%(TM)d;i++){ uint t=t0+l.y+16*i;
    [unroll] for(j=0;j<%(TN)d;j++){ uint o=o0+l.x+16*j; if(t<T&&o<OUT) Y[t*OUT+o]=acc[i][j]; } }
}""" % dict(BT=BT, BO=BO, TM=TM, TN=TN, TN2=TN // 2)

LIN_VARIANTS = {"t48": (4, 8)}     # zusaetzlich zu v1 (4x4) und v2 (float4); 8x4/8x8 waren auf Intel 5x langsamer

# Attention mit KV-Gruppen (alle Q-Koepfe eines KV-Kopfs teilen sich K/V-Lesezugriffe) und Online-Softmax
# in Bloecken zu 128 Schluesseln -> keine Laengengrenze im Kernel selbst.
K_ATTN2 = r"""
cbuffer C:register(b0){ uint T; uint POS0; uint NH; uint NKV; };
RWStructuredBuffer<float> Q:register(u0); RWStructuredBuffer<float> K:register(u1);
RWStructuredBuffer<float> V:register(u2); RWStructuredBuffer<float> O:register(u3);
groupshared float q[4][128]; groupshared float sc[4][128];
[numthreads(128,1,1)]
void main(uint3 g:SV_GroupID, uint3 l:SV_GroupThreadID){
  uint t=g.x, kvh=g.y, i=l.x, G=NH/NKV, QD=NH*128, KD=NKV*128, P=POS0+t, kb=kvh*128, h, j, k;
  for(h=0;h<G;h++) q[h][i]=Q[t*QD+(kvh*G+h)*128+i];
  GroupMemoryBarrierWithGroupSync();
  float m[4], ls[4], acc[4];
  [unroll] for(h=0;h<4;h++){ m[h]=-1e30; ls[h]=0; acc[h]=0; }
  for(uint b0=0;b0<=P;b0+=128){
    uint j0=b0+i, n=min(128,P+1-b0);
    float d[4]; [unroll] for(h=0;h<4;h++) d[h]=0;
    if(i<n){ for(k=0;k<128;k++){ float kv=K[j0*KD+kb+k]; [unroll] for(h=0;h<4;h++) if(h<G) d[h]+=q[h][k]*kv; } }
    [unroll] for(h=0;h<4;h++) sc[h][i]=(i<n)?d[h]*0.08838834764831845:-1e30;
    GroupMemoryBarrierWithGroupSync();
    [unroll] for(h=0;h<4;h++) if(h<G){ float bm=m[h]; for(j=0;j<n;j++) bm=max(bm,sc[h][j]);
      float f=exp(m[h]-bm); acc[h]*=f; ls[h]*=f; m[h]=bm; }
    GroupMemoryBarrierWithGroupSync();
    [unroll] for(h=0;h<4;h++) sc[h][i]=(i<n&&h<G)?exp(sc[h][i]-m[h]):0;
    GroupMemoryBarrierWithGroupSync();
    for(j=0;j<n;j++){ float v=V[(b0+j)*KD+kb+i];
      [unroll] for(h=0;h<4;h++) if(h<G){ float pr=sc[h][j]; ls[h]+=pr; acc[h]+=pr*v; } }
    GroupMemoryBarrierWithGroupSync();
  }
  for(h=0;h<G;h++) O[t*QD+(kvh*G+h)*128+i]=acc[h]/ls[h];
}"""

# v42: Split-K fuer das Schreiben (T = 1). Gruppe (s, kvh) rechnet die Positionen [s*L, min((s+1)*L, P+1)) mit
# Online-Softmax wie K_ATTN2 und legt Teilsumme (acc), Maximum (m) und Nenner (l) ab. K_ATTN_MERGE fuehrt zusammen.
K_ATTN_SPLIT = r"""
cbuffer C:register(b0){ uint POS0; uint L; uint NH; uint NKV; };          // v44e: g.z = Token (Position POS0 + g.z)
RWStructuredBuffer<float> Q:register(u0); RWStructuredBuffer<float> K:register(u1);
RWStructuredBuffer<float> V:register(u2); RWStructuredBuffer<float> PO:register(u3);
RWStructuredBuffer<float> ML:register(u4);
groupshared float q[4][128]; groupshared float sc[4][128];
[numthreads(128,1,1)]
void main(uint3 g:SV_GroupID, uint3 l:SV_GroupThreadID){
  uint s=g.x, kvh=g.y, t=g.z, i=l.x, G=NH/NKV, KD=NKV*128, P=POS0+t, kb=kvh*128, h, j, k;
  uint jb=s*L, je=min(jb+L, P+1), so=(t*%(NS)d+s)*NH;
  for(h=0;h<G;h++) q[h][i]=Q[t*NH*128+(kvh*G+h)*128+i];
  GroupMemoryBarrierWithGroupSync();
  float m[4], ls[4], acc[4];
  [unroll] for(h=0;h<4;h++){ m[h]=-1e30; ls[h]=0; acc[h]=0; }
  for(uint b0=jb;b0<je;b0+=128){
    uint j0=b0+i, n=min(128,je-b0);
    float d[4]; [unroll] for(h=0;h<4;h++) d[h]=0;
    if(i<n){ for(k=0;k<128;k++){ float kv=K[j0*KD+kb+k]; [unroll] for(h=0;h<4;h++) if(h<G) d[h]+=q[h][k]*kv; } }
    [unroll] for(h=0;h<4;h++) sc[h][i]=(i<n)?d[h]*0.08838834764831845:-1e30;
    GroupMemoryBarrierWithGroupSync();
    [unroll] for(h=0;h<4;h++) if(h<G){ float bm=m[h]; for(j=0;j<n;j++) bm=max(bm,sc[h][j]);
      float f=exp(m[h]-bm); acc[h]*=f; ls[h]*=f; m[h]=bm; }
    GroupMemoryBarrierWithGroupSync();
    [unroll] for(h=0;h<4;h++) sc[h][i]=(i<n&&h<G)?exp(sc[h][i]-m[h]):0;
    GroupMemoryBarrierWithGroupSync();
    for(j=0;j<n;j++){ float v=V[(b0+j)*KD+kb+i];
      [unroll] for(h=0;h<4;h++) if(h<G){ float pr=sc[h][j]; ls[h]+=pr; acc[h]+=pr*v; } }
    GroupMemoryBarrierWithGroupSync();
  }
  for(h=0;h<G;h++){ uint qh=kvh*G+h; PO[(so+qh)*128+i]=acc[h];
    if(i==0){ ML[(so+qh)*2]=m[h]; ML[(so+qh)*2+1]=ls[h]; } }
}""" % dict(NS=NSPLIT_MAX)

# v84: wie K_ATTN_SPLIT, aber das Block-Maximum je Q-Kopf wird gemeinsam bestimmt (Baum-Reduktion ueber 128 Threads)
# statt von jedem Thread einzeln ueber alle 128 Werte. Gleiche Ablage (PO, ML), gleicher Merge.
K_ATTN_SPLITR = r"""
cbuffer C:register(b0){ uint POS0; uint L; uint NH; uint NKV; };
RWStructuredBuffer<float> Q:register(u0); RWStructuredBuffer<float> K:register(u1);
RWStructuredBuffer<float> V:register(u2); RWStructuredBuffer<float> PO:register(u3);
RWStructuredBuffer<float> ML:register(u4);
groupshared float q[4][128]; groupshared float sc[4][128]; groupshared float red[4][128];
[numthreads(128,1,1)]
void main(uint3 g:SV_GroupID, uint3 l:SV_GroupThreadID){
  uint s=g.x, kvh=g.y, t=g.z, i=l.x, G=NH/NKV, KD=NKV*128, P=POS0+t, kb=kvh*128, h, j, k, a;
  uint jb=s*L, je=min(jb+L, P+1), so=(t*%(NS)d+s)*NH;
  for(h=0;h<G;h++) q[h][i]=Q[t*NH*128+(kvh*G+h)*128+i];
  GroupMemoryBarrierWithGroupSync();
  float m[4], ls[4], acc[4];
  [unroll] for(h=0;h<4;h++){ m[h]=-1e30; ls[h]=0; acc[h]=0; }
  for(uint b0=jb;b0<je;b0+=128){
    uint j0=b0+i, n=min(128,je-b0);
    float d[4]; [unroll] for(h=0;h<4;h++) d[h]=0;
    if(i<n){ for(k=0;k<128;k++){ float kv=K[j0*KD+kb+k]; [unroll] for(h=0;h<4;h++) if(h<G) d[h]+=q[h][k]*kv; } }
    [unroll] for(h=0;h<4;h++){ float v=(i<n)?d[h]*0.08838834764831845:-1e30; sc[h][i]=v; red[h][i]=v; }
    GroupMemoryBarrierWithGroupSync();
    for(a=64;a>0;a>>=1){ if(i<a){ [unroll] for(h=0;h<4;h++) red[h][i]=max(red[h][i],red[h][i+a]); }
      GroupMemoryBarrierWithGroupSync(); }
    [unroll] for(h=0;h<4;h++) if(h<G){ float bm=max(m[h],red[h][0]); float f=exp(m[h]-bm); acc[h]*=f; ls[h]*=f; m[h]=bm; }
    [unroll] for(h=0;h<4;h++) sc[h][i]=(i<n&&h<G)?exp(sc[h][i]-m[h]):0;
    GroupMemoryBarrierWithGroupSync();
    for(j=0;j<n;j++){ float v=V[(b0+j)*KD+kb+i];
      [unroll] for(h=0;h<4;h++) if(h<G){ float pr=sc[h][j]; ls[h]+=pr; acc[h]+=pr*v; } }
    GroupMemoryBarrierWithGroupSync();
  }
  for(h=0;h<G;h++){ uint qh=kvh*G+h; PO[(so+qh)*128+i]=acc[h];
    if(i==0){ ML[(so+qh)*2]=m[h]; ML[(so+qh)*2+1]=ls[h]; } }
}""" % dict(NS=NSPLIT_MAX)

K_ATTN_MERGE = r"""
cbuffer C:register(b0){ uint NS; uint NH; uint P1; uint P2; };
RWStructuredBuffer<float> PO:register(u0); RWStructuredBuffer<float> ML:register(u1);
RWStructuredBuffer<float> O:register(u2);
[numthreads(128,1,1)]
void main(uint3 g:SV_GroupID, uint3 l:SV_GroupThreadID){
  uint h=g.x, t=g.y, i=l.x, s, b=t*%(NS)d; float M=-1e30, num=0, den=0;
  for(s=0;s<NS;s++) M=max(M, ML[((b+s)*NH+h)*2]);
  for(s=0;s<NS;s++){ float f=exp(ML[((b+s)*NH+h)*2]-M); num+=f*PO[((b+s)*NH+h)*128+i]; den+=f*ML[((b+s)*NH+h)*2+1]; }
  O[t*NH*128+h*128+i]=num/den;
}""" % dict(NS=NSPLIT_MAX)

# v44: Attention fuers Einlesen als zwei Matrixmultiplikationen (gleiche Kachelung wie K_LINEAR2, ~600 GFLOPS):
#   1) S = Q·K^T  je Q-Kopf (alle Schluessel 0..POS0+T-1)   2) Softmax je Zeile mit Kausalmaske   3) O = S·V
# Mehrere Koepfe pro Durchgang (Dispatch-Achse z); S-Puffer <= 120 MB.
def k_gemm(nn):
    """Float-Matrixmultiplikation C[z] = A[z]·B[z] (B transponiert gespeichert: nn=False wie K_LINEAR2; nn=True: B[k][o]).
    Basis je z: A = h*AH + z*AZ, B = (h/G)*BKV, C = h*CH + z*CZ mit h = H0 + z."""
    if nn: lb = """{ uint kk=li>>4, oq=li&15; uint o=o0+4*oq, k=k0+kk, bs=bb+k*LDB+o; float4 v;
      v.x=(k<KK&&o<N)?B[bs]:0; v.y=(k<KK&&o+1<N)?B[bs+1]:0; v.z=(k<KK&&o+2<N)?B[bs+2]:0; v.w=(k<KK&&o+3<N)?B[bs+3]:0;
      Bs[kk][oq]=v; }"""
    else: lb = """{ uint kk=li&15, oq=li>>4; uint o=o0+4*oq, k=k0+kk; float4 v;
      v.x=(k<KK&&o<N)?B[bb+o*LDB+k]:0; v.y=(k<KK&&o+1<N)?B[bb+(o+1)*LDB+k]:0;
      v.z=(k<KK&&o+2<N)?B[bb+(o+2)*LDB+k]:0; v.w=(k<KK&&o+3<N)?B[bb+(o+3)*LDB+k]:0; Bs[kk][oq]=v; }"""
    return r"""
cbuffer C:register(b0){ uint M; uint N; uint KK; uint LDA; uint LDB; uint LDC; uint H0; uint G;
                        uint AH; uint AZ; uint BKV; uint CH; uint CZ; uint P1; uint P2; uint P3; };
RWStructuredBuffer<float> A:register(u0); RWStructuredBuffer<float> B:register(u1); RWStructuredBuffer<float> Y:register(u2);
groupshared float4 As[16][32]; groupshared float4 Bs[16][16];
[numthreads(16,16,1)]
void main(uint3 g:SV_GroupID, uint3 l:SV_GroupThreadID, uint li:SV_GroupIndex){
  uint h=H0+g.z, t0=g.y*128, o0=g.x*64, i, r, c;
  uint ab=h*AH+g.z*AZ, bb=(h/G)*BKV, cb=h*CH+g.z*CZ;
  float4 acc[8];
  [unroll] for(i=0;i<8;i++) acc[i]=0;
  for(uint k0=0;k0<KK;k0+=16){
    [unroll] for(r=0;r<2;r++){ uint sl=li+256*r; uint kk=sl&15, q=sl>>4; uint t=t0+4*q, k=k0+kk; float4 v;
      v.x=(k<KK&&t  <M)?A[ab+(t  )*LDA+k]:0; v.y=(k<KK&&t+1<M)?A[ab+(t+1)*LDA+k]:0;
      v.z=(k<KK&&t+2<M)?A[ab+(t+2)*LDA+k]:0; v.w=(k<KK&&t+3<M)?A[ab+(t+3)*LDA+k]:0; As[kk][q]=v; }
    """ + lb + r"""
    GroupMemoryBarrierWithGroupSync();
    [unroll] for(uint kk=0;kk<16;kk++){
      float4 a0=As[kk][l.y*2], a1=As[kk][l.y*2+1], w=Bs[kk][l.x];
      acc[0]+=a0.x*w; acc[1]+=a0.y*w; acc[2]+=a0.z*w; acc[3]+=a0.w*w;
      acc[4]+=a1.x*w; acc[5]+=a1.y*w; acc[6]+=a1.z*w; acc[7]+=a1.w*w;
    }
    GroupMemoryBarrierWithGroupSync();
  }
  [unroll] for(i=0;i<8;i++){ uint t=t0+l.y*8+i; if(t<M){
    [unroll] for(c=0;c<4;c++){ uint o=o0+l.x*4+c; if(o<N) Y[cb+t*LDC+o]=acc[i][c]; } } }
}"""

def k_gemm16(nn):
    """v86: k_gemm mit B im fp16-KV-Cache (uint = 2 Werte). Je Lesezugriff 2 Werte, kein Verschnitt."""
    src = k_gemm(nn).replace("RWStructuredBuffer<float> B:register(u1)", "RWStructuredBuffer<uint> B:register(u1)")
    if nn:   # V: Zeile k, Spalten o..o+3 liegen nebeneinander -> 2 uint
        old = k_gemm(True).split("Bs[kk][oq]=v; }")[0].split("float4 As[16][32]; groupshared float4 Bs[16][16];")[1]
        new = """
  """
        body = """{ uint kk=li>>4, oq=li&15; uint o=o0+4*oq, k=k0+kk, bs=(bb+k*LDB+o)>>1; float4 v=0;
      if(k<KK&&o<N){ uint u0=B[bs], u1=(o+2<N)?B[bs+1]:0; v=float4(h0(u0),h1(u0),h0(u1),h1(u1)); }
      Bs[kk][oq]=v; }"""
        a = src.index("{ uint kk=li>>4, oq=li&15;"); b = src.index("Bs[kk][oq]=v; }", a) + len("Bs[kk][oq]=v; }")
    else:    # K: Zeile o, Werte k..k+1 nebeneinander -> wie Gewichte in K_LINEAR2
        body = """if(li<128){ uint kp=li&7, oq=li>>3; uint o=o0+4*oq, k=k0+2*kp; uint u0=0,u1=0,u2=0,u3=0;
      if(k<KK){ u0=(o  <N)?B[(bb+(o  )*LDB+k)>>1]:0; u1=(o+1<N)?B[(bb+(o+1)*LDB+k)>>1]:0;
                u2=(o+2<N)?B[(bb+(o+2)*LDB+k)>>1]:0; u3=(o+3<N)?B[(bb+(o+3)*LDB+k)>>1]:0; }
      Bs[2*kp][oq]=float4(h0(u0),h0(u1),h0(u2),h0(u3)); Bs[2*kp+1][oq]=float4(h1(u0),h1(u1),h1(u2),h1(u3)); }"""
        a = src.index("{ uint kk=li&15, oq=li>>4;"); b = src.index("Bs[kk][oq]=v; }", a) + len("Bs[kk][oq]=v; }")
    src = src[:a] + body + src[b:]
    fn = "float h0(uint u){ return f16tof32(u&0xffff); } float h1(uint u){ return f16tof32(u>>16); }\n"
    return src.replace("[numthreads", fn + "[numthreads", 1)

K_SOFTMAX = r"""
cbuffer C:register(b0){ uint M; uint N; uint LD; uint POS0; };
RWStructuredBuffer<float> S:register(u0);
groupshared float red[256];
[numthreads(256,1,1)]
void main(uint3 g:SV_GroupID, uint3 l:SV_GroupThreadID){
  uint t=g.x, i=l.x, base=(g.y*M+t)*LD, P=POS0+t, j, a; float m=-1e30;
  for(j=i;j<=P;j+=256) m=max(m,S[base+j]);
  red[i]=m; GroupMemoryBarrierWithGroupSync();
  for(a=128;a>0;a>>=1){ if(i<a) red[i]=max(red[i],red[i+a]); GroupMemoryBarrierWithGroupSync(); }
  m=red[0]; GroupMemoryBarrierWithGroupSync();
  float z=0; for(j=i;j<=P;j+=256){ float e=exp((S[base+j]-m)*0.08838834764831845); S[base+j]=e; z+=e; }
  red[i]=z; GroupMemoryBarrierWithGroupSync();
  for(a=128;a>0;a>>=1){ if(i<a) red[i]+=red[i+a]; GroupMemoryBarrierWithGroupSync(); }
  float iz=1.0/red[0];
  for(j=i;j<N;j+=256) S[base+j]=(j<=P)?S[base+j]*iz:0;
}"""

SMAX_MB = 120        # v44: Groesse des Zwischenpuffers S (D3D11 garantiert 128 MB je Puffer)

K_COPY = r"""
cbuffer C:register(b0){ uint N; uint DOFF; uint STRIDE; uint P; };
RWStructuredBuffer<float> S:register(u0); RWStructuredBuffer<float> D:register(u1);
[numthreads(256,1,1)]
void main(uint3 d:SV_DispatchThreadID){ for(uint i=d.x;i<N;i+=STRIDE) D[DOFF+i]=S[i]; }"""

# v85: KV-Cache in fp16. kv16() baut aus einem Kernel die 16-Bit-Fassung: Puffer als uint, Lesen X[i] -> LD_X(i).
K_COPY16 = r"""
cbuffer C:register(b0){ uint N; uint DOFF; uint STRIDE; uint P; };
RWStructuredBuffer<float> S:register(u0); RWStructuredBuffer<uint> D:register(u1);
[numthreads(256,1,1)]
void main(uint3 d:SV_DispatchThreadID){ for(uint i=d.x;i<N;i+=STRIDE) D[DOFF+i]=f32tof16(S[2*i])|(f32tof16(S[2*i+1])<<16); }"""

def kv16(src, names):
    import re
    for nm in names:
        src = src.replace(f"RWStructuredBuffer<float> {nm}:register", f"RWStructuredBuffer<uint> {nm}:register")
        out, pos, pat = [], 0, re.compile(r"(?<![A-Za-z0-9_])" + nm + r"\[")
        while True:
            m = pat.search(src, pos)
            if not m: out.append(src[pos:]); break
            out.append(src[pos:m.start()] + f"LD_{nm}("); i, depth = m.end(), 1
            while depth:
                c = src[i]; depth += (c == "[") - (c == "]"); i += 1
            out.append(src[m.end():i - 1] + ")"); pos = i
        src = "".join(out)
        fn = f"float LD_{nm}(uint i){{ uint u={nm}[i>>1]; return f16tof32((i&1)?(u>>16):(u&0xffff)); }}\n"
        src = src.replace("[numthreads", fn + "[numthreads", 1)
    return src

K_SILUMUL = r"""
cbuffer C:register(b0){ uint N; uint STRIDE; uint P1; uint P2; };
RWStructuredBuffer<float> G:register(u0); RWStructuredBuffer<float> U:register(u1);
[numthreads(256,1,1)]
void main(uint3 d:SV_DispatchThreadID){
  for(uint i=d.x;i<N;i+=STRIDE){ float x=G[i]; G[i]=x/(1.0+exp(-x))*U[i]; }
}"""


# ----------------------------------------------------------------------------- v70: 8-Bit-Gewichte
# Ablage: W8 = uint4-Puffer (16 int8 je Element, zeilenweise wie bf16), S = 1 float je 128 Werte (Index (o*IN+k)/128).
_I8 = r"""
float4 i8(uint u){ return float4((int)(u<<24)>>24, (int)(u<<16)>>24, (int)(u<<8)>>24, (int)u>>24); }
"""

# Umrechnung bf16 -> int8: ein Thread je Block zu 128 Werten (Block b = Werte b*128 .. b*128+127).
K_QUANT = _BF + r"""
cbuffer C:register(b0){ uint NB; uint P1; uint P2; uint P3; };
RWStructuredBuffer<uint> B:register(u0); RWStructuredBuffer<uint4> W8:register(u1); RWStructuredBuffer<float> S:register(u2);
uint q4(float a, float b, float c, float d, float inv){
  int4 q=clamp((int4)round(float4(a,b,c,d)*inv), -127, 127);
  return (uint)(q.x&255) | ((uint)(q.y&255)<<8) | ((uint)(q.z&255)<<16) | ((uint)(q.w&255)<<24); }
[numthreads(64,1,1)]
void main(uint3 d:SV_DispatchThreadID){
  uint b=d.x, i; if(b>=NB) return;
  uint base=b*64; float m=0;
  for(i=0;i<64;i++){ uint u=B[base+i]; m=max(m, max(abs(lo(u)), abs(hi(u)))); }
  float inv=(m>0)?127.0/m:0; S[b]=m/127.0;
  for(i=0;i<8;i++){ uint p=base+i*8; uint4 r;
    r.x=q4(lo(B[p  ]),hi(B[p  ]),lo(B[p+1]),hi(B[p+1]),inv); r.y=q4(lo(B[p+2]),hi(B[p+2]),lo(B[p+3]),hi(B[p+3]),inv);
    r.z=q4(lo(B[p+4]),hi(B[p+4]),lo(B[p+5]),hi(B[p+5]),inv); r.w=q4(lo(B[p+6]),hi(B[p+6]),lo(B[p+7]),hi(B[p+7]),inv);
    W8[b*8+i]=r; }
}"""

# Schreiben (1 Token): Gruppe = 8 Ausgabezeilen x 32 Threads; jeder Thread liest 16 Gewichte (uint4) am Stueck.
K_MV8 = _I8 + r"""
cbuffer C:register(b0){ uint IN; uint YOFF; uint XOFF; uint OUT; };
RWStructuredBuffer<float> X:register(u0); RWStructuredBuffer<uint4> W:register(u1);
RWStructuredBuffer<float> Y:register(u2); RWStructuredBuffer<float> S:register(u3);
groupshared float red[256];
[numthreads(256,1,1)]
void main(uint3 g:SV_GroupID, uint3 l:SV_GroupThreadID){
  uint li=l.x, j=li&31, o=g.x*8+(li>>5), n16=IN/16; float acc=0;
  if(o<OUT){ uint wb=o*n16, sb=o*(IN/128);
    for(uint q=j;q<n16;q+=32){ uint4 u=W[wb+q]; uint k=XOFF+q*16;
      float d=dot(i8(u.x), float4(X[k],X[k+1],X[k+2],X[k+3])) + dot(i8(u.y), float4(X[k+4],X[k+5],X[k+6],X[k+7]))
            + dot(i8(u.z), float4(X[k+8],X[k+9],X[k+10],X[k+11])) + dot(i8(u.w), float4(X[k+12],X[k+13],X[k+14],X[k+15]));
      acc+=d*S[sb+(q>>3)]; } }
  red[li]=acc; GroupMemoryBarrierWithGroupSync();
  for(uint a=16;a>0;a>>=1){ if(j<a) red[li]+=red[li+a]; GroupMemoryBarrierWithGroupSync(); }
  if(j==0&&o<OUT) Y[YOFF+o]=red[li];
}"""

# Wenige Tokens (T <= 16): Gruppe = 32 Zeilen x 8 Threads; Tokens je 128 Spalten im Gruppenspeicher.
K_MVT8 = _I8 + r"""
cbuffer C:register(b0){ uint T; uint IN; uint OUT; uint T0; };
RWStructuredBuffer<float> X:register(u0); RWStructuredBuffer<uint4> W:register(u1);
RWStructuredBuffer<float> Y:register(u2); RWStructuredBuffer<float> S:register(u3);
groupshared float Xs[16][128]; groupshared float red[256][17];
[numthreads(256,1,1)]
void main(uint3 g:SV_GroupID, uint3 l:SV_GroupThreadID){
  uint li=l.x, j=li&7, r=li>>3, o=g.x*32+r, t, c, k0, rr;
  float acc[16]; [unroll] for(t=0;t<16;t++) acc[t]=0;
  for(k0=0;k0<IN;k0+=128){
    [unroll] for(rr=0;rr<8;rr++){ uint idx=li+256*rr; uint tt=idx>>7, kk=idx&127;
      Xs[tt][kk]=(tt<T)?X[(T0+tt)*IN+k0+kk]:0; }
    GroupMemoryBarrierWithGroupSync();
    uint4 u=(o<OUT)?W[(o*IN+k0)/16+j]:uint4(0,0,0,0); float s=(o<OUT)?S[(o*IN+k0)/128]:0;
    float4 w0=i8(u.x)*s, w1=i8(u.y)*s, w2=i8(u.z)*s, w3=i8(u.w)*s; uint kb=j*16;
    [unroll] for(t=0;t<16;t++){
      acc[t]+=dot(w0,float4(Xs[t][kb],Xs[t][kb+1],Xs[t][kb+2],Xs[t][kb+3]))+dot(w1,float4(Xs[t][kb+4],Xs[t][kb+5],Xs[t][kb+6],Xs[t][kb+7]))
             +dot(w2,float4(Xs[t][kb+8],Xs[t][kb+9],Xs[t][kb+10],Xs[t][kb+11]))+dot(w3,float4(Xs[t][kb+12],Xs[t][kb+13],Xs[t][kb+14],Xs[t][kb+15])); }
    GroupMemoryBarrierWithGroupSync();
  }
  [unroll] for(t=0;t<16;t++) red[li][t]=acc[t];
  GroupMemoryBarrierWithGroupSync();
  [unroll] for(rr=0;rr<2;rr++){ uint e=li+256*rr; uint ro=e>>4, tt=e&15; float sm=0;
    for(c=0;c<8;c++) sm+=red[ro*8+c][tt];
    uint oo=g.x*32+ro; if(tt<T&&oo<OUT) Y[(T0+tt)*OUT+oo]=sm; }
}"""

def k_linear8(TM, TN):
    """Einlesen mit int8-Gewichten: wie k_linear_tiled, je Ausgabezeile wird ein uint4 (16 Werte = ganze k-Scheibe) gelesen."""
    BT, BO = 16 * TM, 16 * TN
    return _I8 + r"""
cbuffer C:register(b0){ uint T; uint IN; uint OUT; uint PAD; };
RWStructuredBuffer<float> X:register(u0); RWStructuredBuffer<uint4> W:register(u1);
RWStructuredBuffer<float> Y:register(u2); RWStructuredBuffer<float> S:register(u3);
groupshared float As[16][%(BT)d]; groupshared float Ws[16][%(BO)d];
[numthreads(16,16,1)]
void main(uint3 g:SV_GroupID, uint3 l:SV_GroupThreadID, uint li:SV_GroupIndex){
  uint t0=g.y*%(BT)d, o0=g.x*%(BO)d, i, j, r;
  float acc[%(TM)d][%(TN)d];
  [unroll] for(i=0;i<%(TM)d;i++) [unroll] for(j=0;j<%(TN)d;j++) acc[i][j]=0;
  for(uint k0=0;k0<IN;k0+=16){
    [unroll] for(r=0;r<%(TM)d;r++){ uint idx=li+256*r; uint row=idx>>4, kk=idx&15; uint t=t0+row;
      As[kk][row]=(t<T)?X[t*IN+k0+kk]:0; }
    if(li<%(BO)d){ uint o=o0+li; uint4 u=(o<OUT)?W[(o*IN+k0)/16]:uint4(0,0,0,0); float s=(o<OUT)?S[(o*IN+k0)/128]:0;
      float4 a=i8(u.x)*s, b=i8(u.y)*s, c=i8(u.z)*s, d=i8(u.w)*s;
      Ws[0][li]=a.x; Ws[1][li]=a.y; Ws[2][li]=a.z; Ws[3][li]=a.w; Ws[4][li]=b.x; Ws[5][li]=b.y; Ws[6][li]=b.z; Ws[7][li]=b.w;
      Ws[8][li]=c.x; Ws[9][li]=c.y; Ws[10][li]=c.z; Ws[11][li]=c.w; Ws[12][li]=d.x; Ws[13][li]=d.y; Ws[14][li]=d.z; Ws[15][li]=d.w; }
    GroupMemoryBarrierWithGroupSync();
    [unroll] for(uint kk=0;kk<16;kk++){
      float a2[%(TM)d], w[%(TN)d];
      [unroll] for(i=0;i<%(TM)d;i++) a2[i]=As[kk][l.y+16*i];
      [unroll] for(j=0;j<%(TN)d;j++) w[j]=Ws[kk][l.x+16*j];
      [unroll] for(i=0;i<%(TM)d;i++) [unroll] for(j=0;j<%(TN)d;j++) acc[i][j]+=a2[i]*w[j];
    }
    GroupMemoryBarrierWithGroupSync();
  }
  [unroll] for(i=0;i<%(TM)d;i++){ uint t=t0+l.y+16*i;
    [unroll] for(j=0;j<%(TN)d;j++){ uint o=o0+l.x+16*j; if(t<T&&o<OUT) Y[t*OUT+o]=acc[i][j]; } }
}""" % dict(BT=BT, BO=BO, TM=TM, TN=TN)

LIN8_VARIANTS = {"q44": (4, 4), "q48": (4, 8)}

# ----------------------------------------------------------------------------- Gewichte
def bf16_to_f32(raw):
    """bf16-Bytes -> float32-Bytes (little endian: 2 Nullbytes davor)."""
    raw = bytes(raw); out = bytearray(len(raw) * 2)
    out[2::4] = raw[0::2]; out[3::4] = raw[1::2]
    return bytes(out)

class ShardedSafeTensors:
    """Liest model.safetensors oder model-0000X-of-0000Y.safetensors (+ index.json) per mmap."""
    def __init__(self, d):
        d = Path(d); idx = d / "model.safetensors.index.json"
        # index.json ist optional: sonst einfach alle *.safetensors im Ordner nehmen
        files = sorted(set(json.loads(idx.read_text(encoding="utf-8"))["weight_map"].values())) if idx.exists() \
            else sorted(p.name for p in d.glob("*.safetensors"))
        if not files: raise FileNotFoundError(f"Keine .safetensors-Dateien in {d}")
        missing = [f for f in files if not (d / f).exists()]
        if missing: raise FileNotFoundError(f"In {d} fehlen: {', '.join(missing)}")
        self.t, self._keep = {}, []
        for f in files:
            fh = open(d / f, "rb"); mm = mmap.mmap(fh.fileno(), 0, access=mmap.ACCESS_READ); self._keep += [fh, mm]
            n = struct.unpack("<Q", mm[:8])[0]; hdr = json.loads(mm[8:8 + n]); hdr.pop("__metadata__", None)
            for k, v in hdr.items(): self.t[k] = (mm, 8 + n, v)
    def __contains__(self, k): return k in self.t
    def shape(self, k): return self.t[k][2]["shape"]
    def dtype(self, k): return self.t[k][2]["dtype"]
    def raw(self, k):
        mm, base, v = self.t[k]; a, b = v["data_offsets"]
        return memoryview(mm)[base + a: base + b]
    def f32(self, k):
        if self.dtype(k) == "F32": return bytes(self.raw(k))
        if self.dtype(k) != "BF16": raise ValueError(f"{k}: Datentyp {self.dtype(k)} nicht unterstuetzt (erwartet BF16)")
        return bf16_to_f32(self.raw(k))

# ----------------------------------------------------------------------------- Engine
# v118: class Qwen3Engine entfernt (nur noch Qwen3.5, aura/llm/qwen35.py). Diese Datei = Kernel-Bibliothek + Hilfsfunktionen.

def common_prefix(a, b):
    n = min(len(a), len(b)); i = 0
    while i < n and a[i] == b[i] and a[i] is not None: i += 1
    return i

def sample(logits, temperature=0.3, top_k=20, top_p=0.8, rng=random):
    if temperature <= 0: return logits.index(max(logits))          # gierig: beide Aufrufe laufen in C (schnell)
    top = heapq.nlargest(top_k, range(len(logits)), key=logits.__getitem__)
    m = logits[top[0]]; ps = [math.exp((logits[i] - m) / temperature) for i in top]; z = sum(ps)
    acc, keep = 0.0, []
    for i, p in zip(top, ps):
        keep.append((i, p)); acc += p / z
        if acc >= top_p: break
    r = rng.random() * sum(p for _, p in keep)
    for i, p in keep:
        r -= p
        if r <= 0: return i
    return keep[-1][0]
