# aura/llm/qwen.py — Version 20261010v44  (AURA)  v28: Kontext bis 32k, Attention v1 nur bis 4k
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
NSPLIT_MAX = 64      # v42: hoechstens so viele Teilstuecke je KV-Kopf beim Schreiben
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

K_SILUMUL = r"""
cbuffer C:register(b0){ uint N; uint STRIDE; uint P1; uint P2; };
RWStructuredBuffer<float> G:register(u0); RWStructuredBuffer<float> U:register(u1);
[numthreads(256,1,1)]
void main(uint3 d:SV_DispatchThreadID){
  for(uint i=d.x;i<N;i+=STRIDE){ float x=G[i]; G[i]=x/(1.0+exp(-x))*U[i]; }
}"""

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
class Qwen3Engine:
    def __init__(self, model_dir, progress=lambda *a: None, layers=None, maxT=MAXT):
        self.dir = Path(model_dir)
        c = self.cfg = json.loads((self.dir / "config.json").read_text(encoding="utf-8"))
        self.H, self.I, self.L = c["hidden_size"], c["intermediate_size"], c["num_hidden_layers"]
        self.NH, self.NKV, self.D = c["num_attention_heads"], c["num_key_value_heads"], c.get("head_dim", 128)
        self.eps, self.V = c.get("rms_norm_eps", 1e-6), c["vocab_size"]
        if self.D != 128: raise ValueError("Engine erwartet head_dim = 128")
        if layers is not None: self.L = layers
        self.maxT = min(maxT, MAXT)
        self.st = ShardedSafeTensors(self.dir)
        g = self.g = GPU()
        self.k_lin, self.k_mv, self.k_rms = g._shader(K_LINEAR), g._shader(K_MATVEC), g._shader(K_RMS)
        self.k_rope, self.k_attn, self.k_silu = g._shader(K_QKROPE), g._shader(K_ATTN), g._shader(K_SILUMUL)
        self.k_copy = g._shader(K_COPY)
        self.k_lin2, self.k_attn2 = g._shader(K_LINEAR2), g._shader(K_ATTN2)
        try: self.k_split, self.k_merge = g._shader(K_ATTN_SPLIT), g._shader(K_ATTN_MERGE)      # v42
        except Exception as e: self.k_split = None; progress(f"Split-K-Attention nicht verfuegbar: {e}")
        self.k_mt = None; self.small_kernel = "v2"                                         # v44d
        try: self.k_mt = g._shader(K_MATVEC_T)
        except Exception as e: progress(f"Kernel fuer kleine Bloecke nicht verfuegbar: {e}")
        self.k_gemm = None; self.pre_kernel = "v2"                                         # v44
        try: self.k_gemm = (g._shader(k_gemm(False)), g._shader(k_gemm(True)), g._shader(K_SOFTMAX))
        except Exception as e: progress(f"Attention gemm nicht verfuegbar: {e}")
        self.dec_kernel = "v2"
        self.k_lins = {}
        for name, (tm, tn) in LIN_VARIANTS.items():
            try: self.k_lins[name] = (g._shader(k_linear_tiled(tm, tn)), 16 * tm, 16 * tn)
            except Exception as e: progress(f"Kernel {name} nicht verfuegbar: {e}")
        if self.NH % self.NKV or self.NH // self.NKV > 4: raise ValueError("Engine erwartet hoechstens 4 Q-Koepfe pro KV-Kopf")
        self.lin_kernel = "v2"; self.attn_kernel = "v2"; self.prof = None
        P = "model.layers.%d."; up = lambda k: g.buffer(len(self.st.raw(k)) // 4, self.st.raw(k))
        upf = lambda k: (lambda b: g.buffer(len(b) // 4, b))(self.st.f32(k))
        self.w = []
        for l in range(self.L):
            p = P % l; progress(f"Lade Sprachmodell: Schicht {l + 1}/{self.L}", l, self.L)
            d = {n: up(p + n + ".weight") for n in ("self_attn.q_proj", "self_attn.k_proj", "self_attn.v_proj",
                                                       "self_attn.o_proj", "mlp.gate_proj", "mlp.up_proj", "mlp.down_proj")}
            for n in ("input_layernorm", "post_attention_layernorm", "self_attn.q_norm", "self_attn.k_norm"):
                d[n] = upf(p + n + ".weight")
            self.w.append(d)
        self.norm = upf("model.norm.weight")
        emb = "model.embed_tokens.weight"; head = "lm_head.weight" if "lm_head.weight" in self.st else emb
        self.emb_raw = self.st.raw(emb); self.row_bytes = self.H * 2
        progress("Lade Sprachmodell: Ausgabeschicht", self.L, self.L)
        hr = self.st.raw(head); self.lmh = []
        for r0 in range(0, self.V, LMH_ROWS):
            r1 = min(self.V, r0 + LMH_ROWS)
            self.lmh.append((r0, r1, g.buffer((r1 - r0) * self.H // 2, hr[r0 * self.row_bytes: r1 * self.row_bytes])))
        # RoPE-Tabelle (cos, sin) in doppelter Genauigkeit auf der CPU berechnet
        theta = c.get("rope_theta", 1e6)
        inv = [1.0 / theta ** (2 * i / self.D) for i in range(self.D // 2)]
        cs = array("f")
        for p in range(self.maxT):
            for f in inv: cs.append(math.cos(p * f)); cs.append(math.sin(p * f))
        self.cs = g.buffer(len(cs), cs.tobytes())
        H, I, QD, KD, C = self.H, self.I, self.NH * 128, self.NKV * 128, CHUNK
        self.R, self.X, self.O = g.buffer(C * H), g.buffer(C * H), g.buffer(C * H)
        self.Q, self.A, self.K, self.Vb = g.buffer(C * QD), g.buffer(C * QD), g.buffer(C * KD), g.buffer(C * KD)
        self.Gt, self.Up = g.buffer(C * I), g.buffer(C * I)
        self.kc = [g.buffer(self.maxT * KD) for _ in range(self.L)]
        self.vc = [g.buffer(self.maxT * KD) for _ in range(self.L)]
        self.logits = g.buffer(self.V)
        self.kv_ids, self.reused = [], 0                                 # v43: Inhalt des KV-Caches (Token je Position)
        self.small_attn = "v2"                                           # v44e
        if self.k_split: self.PO, self.ML = g.buffer(SPLIT_T * NSPLIT_MAX * self.NH * 128), g.buffer(SPLIT_T * NSPLIT_MAX * self.NH * 2)
        if self.k_gemm:                                                  # v44: Zwischenpuffer S fuer mehrere Koepfe
            self.nb = max(1, min(self.NH, SMAX_MB * 1_000_000 // (C * self.maxT * 4)))
            self.S = g.buffer(self.nb * C * self.maxT)

    # ---- Bausteine
    def _lin(self, x, w, y, T, IN, OUT):
        if T == 1: self.g._run(self.k_mv, struct.pack("<4I", IN, 0, 0, 0), [x, w, y], (OUT, 1, 1))
        elif T <= SMALL_MAX and self.small_kernel == "mt":                            # v44d: wenige Tokens
            for t0 in range(0, T, 16):
                self.g._run(self.k_mt, struct.pack("<4I", min(16, T - t0), IN, OUT, t0), [x, w, y], ((OUT + 7) // 8, 1, 1))
        elif self.lin_kernel in self.k_lins:
            k, bt, bo = self.k_lins[self.lin_kernel]
            self.g._run(k, struct.pack("<4I", T, IN, OUT, 0), [x, w, y], ((OUT + bo - 1) // bo, (T + bt - 1) // bt, 1))
        elif self.lin_kernel == "v2":
            self.g._run(self.k_lin2, struct.pack("<4I", T, IN, OUT, 0), [x, w, y], ((OUT + 63) // 64, (T + 127) // 128, 1))
        else: self.g._run(self.k_lin, struct.pack("<4I", T, IN, OUT, 0), [x, w, y], ((OUT + 63) // 64, (T + 63) // 64, 1))
        self._tick("linear")

    def _attn(self, l, T, pos0):
        if pos0 + T >= SPLIT_MIN and ((T == 1 and self.dec_kernel == "split")            # v42: Schreiben mit Split-K
                                      or (1 < T <= SPLIT_T and self.small_attn == "split")):  # v44e: kleine Bloecke
            n = pos0 + T; L = max(256, (-(-n // NSPLIT_MAX) + 127) // 128 * 128); ns = -(-n // L)
            self.g._run(self.k_split, struct.pack("<4I", pos0, L, self.NH, self.NKV),
                        [self.Q, self.kc[l], self.vc[l], self.PO, self.ML], (ns, self.NKV, T))
            self.g._run(self.k_merge, struct.pack("<4I", ns, self.NH, 0, 0), [self.PO, self.ML, self.A], (self.NH, T, 1))
        elif T >= PRE_MIN and self.pre_kernel == "gemm":                              # v44: Einlesen als Matrixprodukt
            self._attn_gemm(l, T, pos0)
        elif self.attn_kernel == "v2" or pos0 + T > ATTN1_MAX:      # v1 kann nur bis 4096 Positionen
            self.g._run(self.k_attn2, struct.pack("<4I", T, pos0, self.NH, self.NKV), [self.Q, self.kc[l], self.vc[l], self.A], (T, self.NKV, 1))
        else:
            self.g._run(self.k_attn, struct.pack("<4I", T, pos0, self.NH, self.NKV), [self.Q, self.kc[l], self.vc[l], self.A], (T, self.NH, 1))
        self._tick("attention")

    def _attn_gemm(self, l, T, pos0):
        """v44: S = Q·K^T (nb Koepfe je Durchgang), Softmax mit Kausalmaske, O = S·V. Gleiche Werte wie K_ATTN2."""
        kt, kn, ks = self.k_gemm; N = pos0 + T; QD, KD, G = self.NH * 128, self.NKV * 128, self.NH // self.NKV
        for h0 in range(0, self.NH, self.nb):
            nz = min(self.nb, self.NH - h0)
            #                           M  N    KK   LDA LDB LDC H0  G  AH   AZ    BKV  CH   CZ
            self.g._run(kt, struct.pack("<16I", T, N, 128, QD, KD, N, h0, G, 128, 0, 128, 0, T * N, 0, 0, 0),
                        [self.Q, self.kc[l], self.S], ((N + 63) // 64, (T + 127) // 128, nz))
            self.g._run(ks, struct.pack("<4I", T, N, N, pos0), [self.S], (T, nz, 1))
            self.g._run(kn, struct.pack("<16I", T, 128, N, N, KD, QD, h0, G, 0, T * N, 128, 128, 0, 0, 0, 0),
                        [self.S, self.vc[l], self.A], (2, (T + 127) // 128, nz))

    def _tick(self, name):
        """Profil-Modus (nur fuer Messungen): nach jedem Schritt auf die GPU warten und Zeit zuordnen."""
        if self.prof is None: return
        import time
        self.g.sync(); now = time.perf_counter()
        self.prof[name] = self.prof.get(name, 0.0) + now - self.prof["_t"]; self.prof["_t"] = now
    def _rms(self, a, r, gw, y, T, add):
        self.g._run(self.k_rms, struct.pack("<IIfI", T, self.H, self.eps, 1 if add else 0), [a, r, gw, y], (T, 1, 1))
    def _copy(self, src, dst, nfloats, dst_off):
        groups = min((nfloats + 255) // 256, 65535)
        self.g._run(self.k_copy, struct.pack("<4I", nfloats, dst_off, groups * 256, 0), [src, dst], (groups, 1, 1))

    def layer(self, l, T, pos0, first):
        w, H, I, QD, KD = self.w[l], self.H, self.I, self.NH * 128, self.NKV * 128
        self._rms(self.O, self.R, w["input_layernorm"], self.X, T, add=not first)   # R += O (Rest vorher), X = norm(R)
        self._tick("andere")
        self._lin(self.X, w["self_attn.q_proj"], self.Q, T, H, QD)
        self._lin(self.X, w["self_attn.k_proj"], self.K, T, H, KD)
        self._lin(self.X, w["self_attn.v_proj"], self.Vb, T, H, KD)
        self.g._run(self.k_rope, struct.pack("<IIIf", T, self.NH, pos0, self.eps), [self.Q, w["self_attn.q_norm"], self.cs], (T, self.NH, 1))
        self.g._run(self.k_rope, struct.pack("<IIIf", T, self.NKV, pos0, self.eps), [self.K, w["self_attn.k_norm"], self.cs], (T, self.NKV, 1))
        self._copy(self.K, self.kc[l], T * KD, pos0 * KD); self._copy(self.Vb, self.vc[l], T * KD, pos0 * KD)
        self._tick("andere"); self._attn(l, T, pos0)
        self._lin(self.A, w["self_attn.o_proj"], self.O, T, QD, H)
        self._rms(self.O, self.R, w["post_attention_layernorm"], self.X, T, add=True)
        self._tick("andere")
        self._lin(self.X, w["mlp.gate_proj"], self.Gt, T, H, I)
        self._lin(self.X, w["mlp.up_proj"], self.Up, T, H, I)
        n = T * I; groups = min((n + 255) // 256, 65535)
        self.g._run(self.k_silu, struct.pack("<4I", n, groups * 256, 0, 0), [self.Gt, self.Up], (groups, 1, 1))
        self._tick("andere")
        self._lin(self.Gt, w["mlp.down_proj"], self.O, T, I, H)

    def embed_rows(self, ids):
        rb = self.row_bytes
        return b"".join(bf16_to_f32(self.emb_raw[t * rb:(t + 1) * rb]) for t in ids)

    def forward(self, ids, pos0, want_logits=True):
        """Rechnet die Tokens ids ab Position pos0 (fuellt den KV-Cache). Liefert Logits des letzten Tokens."""
        T = len(ids)
        kv = self.kv_ids[:pos0]                                          # v43: ab pos0 wird ueberschrieben
        self.kv_ids = kv + [None] * (pos0 - len(kv)) + list(ids)         # Luecke (z.B. Messung) = unbekannt
        self.g.write(self.R, self.embed_rows(ids))
        for l in range(self.L):
            self.layer(l, T, pos0, first=(l == 0))
            if T > 1: self.g.sync()                       # kurze GPU-Pakete -> kein Treiber-Timeout (TDR)
        self._rms(self.O, self.R, self.norm, self.X, T, add=True)
        if not want_logits: return None
        for r0, r1, wb in self.lmh:
            self.g._run(self.k_mv, struct.pack("<4I", self.H, r0, (T - 1) * self.H, 0), [self.X, wb, self.logits], (r1 - r0, 1, 1))
        return self.g.read(self.logits, self.V)

    def close(self): self.g.close()

    # ---- v43: KV-Cache eines festen Vorspanns speichern/laden
    def save_kv(self, path, n):
        import json as _j
        from pathlib import Path as _P
        KD = self.NKV * 128; p = _P(path); p.parent.mkdir(parents=True, exist_ok=True); tmp = p.with_suffix(".tmp")
        with open(tmp, "wb") as f:
            hd = _j.dumps({"modell": self.dir.name, "L": self.L, "kd": KD, "ids": self.kv_ids[:n]}).encode()
            f.write(struct.pack("<I", len(hd)) + hd)
            for l in range(self.L):
                for b in (self.kc[l], self.vc[l]): f.write(self.g.read(b, n * KD).tobytes())
        tmp.replace(p)

    def load_kv(self, path):
        """Laedt den gespeicherten Vorspann in den KV-Cache; Rueckgabe: Anzahl Tokens (0 = passt nicht)."""
        import json as _j
        KD = self.NKV * 128
        with open(path, "rb") as f:
            hd = _j.loads(f.read(struct.unpack("<I", f.read(4))[0]))
            n = len(hd["ids"])
            if hd["modell"] != self.dir.name or hd["L"] != self.L or hd["kd"] != KD or n >= self.maxT: return 0
            for l in range(self.L):
                for b in (self.kc[l], self.vc[l]): self.g.write(b, f.read(n * KD * 4))
        self.kv_ids = list(hd["ids"]); return n

    def self_check(self, progress=lambda *a: None):
        """Vergleicht alte und neue Kernels auf dieser GPU (Ergebnis + Tempo) und waehlt die schnellste korrekte Variante.
        Faellt bei Abweichungen automatisch auf die bewaehrten Kernels zurueck."""
        import time
        rnd = random.Random(1); H, I, QD, KD = self.H, self.I, self.NH * 128, self.NKV * 128
        T = min(CHUNK, self.maxT); res = {}
        rand = lambda n: array("f", [rnd.uniform(-1, 1) for _ in range(n)]).tobytes()
        def rel(a, b):
            m = max(abs(x) for x in a) or 1.0
            return max(abs(x - y) for x, y in zip(a, b)) / m
        def timed(fn, reps=2):
            fn(); self.g.sync(); t0 = time.perf_counter()
            for _ in range(reps): fn()
            self.g.sync(); return (time.perf_counter() - t0) / reps
        progress("Sprachmodell: Kernel-Selbsttest ...")
        self.g.write(self.X, rand(T * H)); w = self.w[0]["mlp.gate_proj"]; out = {}
        names = ["v1", "v2"] + list(self.k_lins); res["lin_names"] = names
        for v in names: res["lin_" + v] = 1e9
        for _ in range(3):                             # verschachtelt messen, je Variante das Minimum (robuster bei Last)
            for v in names:
                self.lin_kernel = v; res["lin_" + v] = min(res["lin_" + v], timed(lambda: self._lin(self.X, w, self.Gt, T, H, I), 1))
                if v not in out: out[v] = self.g.read(self.Gt, T * I)
        best = "v1"
        for v in names:
            res["gflops_" + v] = 2 * T * H * I / res["lin_" + v] / 1e9
            res["diff_" + v] = rel(out["v1"], out[v]) if v != "v1" else 0.0
            if res["diff_" + v] < 1e-3 and res["lin_" + v] < 0.9 * res["lin_" + best]: best = v
        res["lin_diff"] = res["diff_v2"]; self.lin_kernel = best; out = {}
        # v44d: kleine Bloecke (10 Tokens, wie das JSON-Geruest) - K_MATVEC_T gegen den gewaehlten Matrix-Kernel
        self.small_kernel = "v2"
        if self.k_mt:
            ts = 10
            for v in ("v2", "mt"):
                self.small_kernel = v; res["small_" + v] = timed(lambda: self._lin(self.X, w, self.Gt, ts, H, I), 3)
                out["small_" + v] = self.g.read(self.Gt, ts * I)
            res["small_diff"] = rel(out["small_v2"], out["small_mt"])
            ok = res["small_diff"] < 1e-3 and res["small_mt"] < res["small_v2"]
            self.small_kernel = "mt" if ok else "v2"
            progress(f"Matrix fuer {ts} Tokens: {self.lin_kernel} {res['small_v2'] * 1000:.1f} ms, mt {res['small_mt'] * 1000:.1f} ms, "
                     f"Abweichung {res['small_diff']:.1e} -> {self.small_kernel}")
            out = {}
        self.g.write(self.Q, rand(T * QD)); self.g.write(self.kc[0], rand(T * KD)); self.g.write(self.vc[0], rand(T * KD))
        for v in ("v1", "v2"):
            self.attn_kernel = v; res["attn_" + v] = timed(lambda: self._attn(0, T, 0))
            out[v] = self.g.read(self.A, T * QD)
        res["attn_diff"] = rel(out["v1"], out["v2"])
        self.attn_kernel = "v2" if res["attn_diff"] < 1e-3 and res["attn_v2"] < res["attn_v1"] else "v1"
        res["T"] = T
        # v42: Schreiben (1 Token) bei langem Kontext - Split-K gegen v2
        self.dec_kernel = "v2"
        if self.k_split and self.maxT > SPLIT_MIN:
            P = min(self.maxT, 8192) - 1; blk = rand(KD * 512)
            full = (blk * ((P + 1) // 512 + 1))[:(P + 1) * KD * 4]
            self.g.write(self.kc[0], full); self.g.write(self.vc[0], full)
            self.g.write(self.Q, rand(QD))
            for v in ("v2", "split"):
                self.dec_kernel = v; res["dec_" + v] = timed(lambda: self._attn(0, 1, P), 3)
                out[v] = self.g.read(self.A, QD)
            res["dec_diff"] = rel(out["v2"], out["split"]); res["dec_pos"] = P + 1
            ok = res["dec_diff"] < 1e-3 and res["dec_split"] < res["dec_v2"]
            self.dec_kernel = "split" if ok else "v2"
            progress(f"Attention beim Schreiben ({P + 1} Positionen): v2 {res['dec_v2'] * 1000:.1f} ms, Split-K "
                     f"{res['dec_split'] * 1000:.1f} ms, Abweichung {res['dec_diff']:.1e} -> {self.dec_kernel}")
            # v44e: 10 Tokens am Ende desselben Kontexts (wie das JSON-Geruest) - Split-K gegen den bisherigen Weg
            ts = 10; p0 = P + 1 - ts; self.g.write(self.Q, rand(ts * QD)); self.small_attn = "v2"
            for v in ("v2", "split"):
                self.small_attn = v; res["sattn_" + v] = timed(lambda: self._attn(0, ts, p0), 3)
                out["sattn_" + v] = self.g.read(self.A, ts * QD)
            res["sattn_diff"] = rel(out["sattn_v2"], out["sattn_split"])
            ok = res["sattn_diff"] < 1e-3 and res["sattn_split"] < res["sattn_v2"]
            self.small_attn = "split" if ok else "v2"
            progress(f"Attention fuer {ts} Tokens: v2 {res['sattn_v2'] * 1000:.1f} ms, Split-K {res['sattn_split'] * 1000:.1f} ms, "
                     f"Abweichung {res['sattn_diff']:.1e} -> {self.small_attn}")
        # v44: Einlesen (T Tokens) bei langem Kontext - Attention gemm gegen den bisherigen Kernel
        self.pre_kernel = "v2"
        if self.k_gemm and T >= PRE_MIN:
            pos = max(0, min(4096, self.maxT - T)); need = (pos + T) * KD; blk = rand(KD * 512)
            full = (blk * (need // (KD * 512) + 1))[:need * 4]
            self.g.write(self.kc[0], full); self.g.write(self.vc[0], full); self.g.write(self.Q, rand(T * QD))
            for v in ("v2", "gemm"):
                self.pre_kernel = v; res["pre_" + v] = timed(lambda: self._attn(0, T, pos), 1)
                out["pre_" + v] = self.g.read(self.A, T * QD)
            res["pre_diff"] = rel(out["pre_v2"], out["pre_gemm"]); res["pre_pos"] = pos
            ok = res["pre_diff"] < 1e-3 and res["pre_gemm"] < res["pre_v2"]
            self.pre_kernel = "gemm" if ok else "v2"
            progress(f"Attention beim Einlesen ({T} Tokens ab Position {pos}): v2 {res['pre_v2'] * 1000:.0f} ms, gemm "
                     f"{res['pre_gemm'] * 1000:.0f} ms, Abweichung {res['pre_diff']:.1e} -> {self.pre_kernel}")
        self.kv_ids = []                                                 # v43: Selbsttest hat den Cache beschrieben
        self.bench = res; return res

    def prefill(self, ids, progress=lambda *a: None, cancelled=lambda: False):
        """v43: Tokens, die schon im KV-Cache stehen (gleicher Anfang), werden nicht nochmals gerechnet.
        Das letzte Token wird immer gerechnet (liefert die Logits)."""
        c = min(common_prefix(self.kv_ids, ids), len(ids) - 1); self.reused = c
        if c: progress(f"Kontext: {c} von {len(ids)} Tokens aus dem Cache")
        logits = None
        for s in range(c, len(ids), CHUNK):
            if cancelled(): return None
            part = ids[s:s + CHUNK]; last = s + CHUNK >= len(ids)
            progress(f"Lese Kontext: {min(s + CHUNK, len(ids))}/{len(ids)} Tokens", s, len(ids))
            logits = self.forward(part, s, want_logits=last)
        return logits

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
