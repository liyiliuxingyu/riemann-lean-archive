#!/usr/bin/env python3
"""Export a source-level proof walkthrough with exact, numbered source modules.

This is not a Lean elaboration trace or a kernel proof-term export.
"""
from pathlib import Path
import argparse
import hashlib
import json

AA = 'Development/AutomorphicArithmetic/'
CB = AA + 'CharacterBoxes/'
PC = AA + 'PrimitiveCosets/'
LT = AA + 'DedekindLFunctions/LandauTheorems/'
DT = AA + 'AutomorphicVarieties/ModularityArgument/ThresholdArguments/DenseThresholdCases/'

STAGES = [
 ('P01', '公开目标与最终声明',
  '目标是 Mathlib 的 RiemannHypothesis；其余四个公开声明涉及ζ及Dirichlet L函数。',
  'Main.lean 通过 rhOfAll、allChi、claimAll 和 critAll 给出最终声明。先核对 Statements 中的定义，不能只根据定理名称判断证明了什么。',
  ['Statements.lean','Main.lean','Supplements/Kernels/MainTheoremsCritical.lean']),
 ('P02', '将最终无零点结论接到上游输入',
  '输入是 Green、VWin 以及统一族的相容性条件。',
  'EveryCharacter.plugWin 调用 shapeWin 和 supplyChi；plugAll 再处理非本原特征。MainConclusion 给出原工程中最终接口的实例。这里保留原代码全部前提。',
  [CB+'MainConclusion.lean',CB+'EveryCharacter.lean']),
 ('P03', '上同调长度窗口',
  '输入来自原工程更深的Galois表示、模性与长度估计。',
  '本阶段输出的是VWin及相关长度窗口，不直接等同于G(x)的上界。其全部上游尚未被本文逐引理转写。',
  [CB+'ExistsPageN.lean',DT+'VwinOfRow.lean',DT+'TopMainZj.lean']),
 ('P04', '构造宿主与辅助条件',
  '对一个固定的本原Dirichlet特征ψ，构造满足需求GChi ψ的宿主族。',
  'Supply/HostOfField/SupplyChi 保留长度条件与辅助特征误差条件；模1专门化不会使所有辅助特征消失。',
  [CB+'Supply.lean',CB+'HostOfField.lean',CB+'SupplyChi.lean']),
 ('P05', '固定常数后选择小参数',
  'eD、eL及正阈值ε1必须在ε之前固定。',
  'FamilyClassConnected 与 DesWin、ShapeWin 的组合产生符合ChainTied的同一数据族。依赖ε或族的辅助常数不可误写成全体统一常数。',
  [CB+'DivinNOfHypV.lean',CB+'DesWin.lean',CB+'ShapeWin.lean']),
 ('P06', '在同一个好尺度汇合算术与几何',
  '数据族必须同时具有EFamC、Win和ChainTied。',
  'WindowInequalityOfArtinInputs/LevelGmLeOnFamilyScales 对每个好尺度选择可用宿主，合并阈值，并调用局部主项与误差界。',
  [PC+'WindowInequalityOfArtinInputs.lean',PC+'LevelGmLeOnFamilyScales.lean']),
 ('P07', '主项比较与辅助误差求和',
  '核心结构提供E=eD+eL≥0及主项比较，辅助误差给出4o的因子。',
  '模1时o=1，得到G(x)≤x^(1/2+(E+6)ε)+4x^(1/2+ε)。几何比较本身仍引用原工程；后续指数合并已在中文稿完整计算。',
  [LT+'ChTop.lean',LT+'ChCore.lean',PC+'CoreGm.lean',PC+'SigALe.lean']),
 ('P08', '合并指数并形成算术窗口',
  'x≥1、ε>0、E≥0，且好窗口可出现在任意远处。',
  '两项合并≤5x^(1/2+(E+6)ε)；超过x≥5^(1/ε)后，吸收常数5，得到指数1/2+(E+7)ε。再取固定K>|E+7|，得到中文稿的算术窗口定理。',
  ['Formalism/SharpRestriction/RamificationFrobenius/TotientGaloisClasses/TopWin.lean',CB+'ZeroFreeAllOfTopG.lean']),
 ('P09', '平滑素数函数及变换',
  'S(x)=Σ[n≤x]Λ(n)(x/n−1)，G(x)=S(x)−x log x+(1+γ)x。',
  '逐项计算Mellin变换，得到Φ=−ζ′/[s(s−1)ζ]−1/(s−1)^2+(1+γ)/(s−1)。中文稿专门化到ζ并检查s=1的可去奇点。',
  [AA+'DedekindLFunctions/CharFamily.lean',LT+'mellinGchiModOne.lean',LT+'poleData.lean']),
 ('P10', '单侧窗口控制高阶导数',
  '只有G(x)≤x^θ，不预先假设|G(x)|≤x^θ。',
  '取A_k=(-1)^k Φ^(k)/k!；使用|A_k(σ+it)|+Re A_k(σ)与|g|+g=2 max(g,0)。中文稿取σ=336、k=ceil(420U)，明确估计两侧尾部。',
  [LT+'landauWindowIneq.lean',LT+'landauTails.lean']),
 ('P11', '极点迫使导数增长并产生矛盾',
  'ζ的零点对应非零留数的单极点；ζ专门化另证明正实轴无极点。',
  '分离唯一最近极点，用Cauchy估计得到导数下界。结合窗口上界导出0<b≤(B+U+C)q^U→0，q∈(0,1)。',
  [LT+'LandauFinite.lean',LT+'LandauPoleAsym.lean',LT+'landauWindow.lean']),
 ('P12', '将排除边界推进到二分之一',
  '固定K后，可以任取足够小的正ε；好尺度无界。',
  '若β>1/2，选1/2<θ<min(β,1)，再取1/2+Kε<θ。窗口排除Re s>θ的零点，与β矛盾。',
  [LT+'WindowHypOfRpow.lean',LT+'ZeroFreeOfRpowWindow.lean',CB+'ZeroFreeAllOfTopG.lean']),
 ('P13', '模1专门化及函数方程收尾',
  '右侧无零点；排除ζ在0处及平凡零点的特殊情况。',
  'EveryCharacter在模1时给出ζ右半平面非消失。函数方程把左侧非平凡零点映到已排除的右侧，因此所有非平凡零点实部为1/2。',
  [CB+'RiemannHypothesisOfEveryCharacter.lean','Main.lean']),
]

def sha(data): return hashlib.sha256(data).hexdigest()

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--source-root',required=True,type=Path)
    parser.add_argument('--output-dir',required=True,type=Path)
    args=parser.parse_args()
    root=args.source_root.resolve(); out=args.output_dir.resolve()
    out.mkdir(parents=True,exist_ok=True)
    modules={}; stages=[]
    for sid,title,premise,argument,paths in STAGES:
        records=[]
        for relative in paths:
            p=root/relative
            if not p.is_file():raise FileNotFoundError(p)
            if relative not in modules:
                raw=p.read_bytes(); body=raw.decode('utf-8')
                modules[relative]={'path':relative,'module':relative[:-5].replace('/','.'),
                    'sha256':sha(raw),'bytes':len(raw),'lines':len(body.splitlines()),
                    'source':body}
            records.append({k:v for k,v in modules[relative].items() if k!='source'})
        stages.append({'id':sid,'title':title,'premises':premise,'argument':argument,'sources':records})
    payload={'format':'source-proof-walkthrough-v1','date_beijing':'2026-11-22',
      'scope':'Source-level mathematical explanation and exact source excerpts. Not an elaboration trace, not a minimal theorem-dependency closure, and not a kernel NDJSON export.',
      'arithmetic_upstream_status':'Deep arithmetic geometry remains cited; interfaces and the analytic implication are expanded in the accompanying ctexbook manuscript.',
      'source_commit':'40e56bab026552e089d7afcfeff08d2defb9c005',
      'stages':stages,'modules':list(modules.values())}
    (out/'证明过程_结构化索引.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    with (out/'证明过程_数学说明与关键源码.txt').open('w',encoding='utf-8',newline='\n') as f:
        f.write('黎曼猜想：证明过程的数学说明与关键源码\n\n')
        f.write('版本：2026-11-22；原源码固定提交：'+payload['source_commit']+'\n')
        f.write('本文件按证明逻辑组织关键源码，并逐行编号。它不是Lean执行时逐tactic状态日志，也不是内核证明项NDJSON。原工程完整源码另见RH_AllSources.lean；中文纸面证明见配套ctexbook PDF。\n')
        f.write('算术几何上游仍有明确引用输入；本轮没有把全部上游证明转写完，也没有重新执行完整工程内核核验。\n\n')
        for s in stages:
            f.write('='*68+'\n'+s['id']+'　'+s['title']+'\n'+'='*68+'\n')
            f.write('前提与对象：'+s['premises']+'\n推导与输出：'+s['argument']+'\n源码：\n')
            for m in s['sources']:
                f.write('  '+m['path']+'\n  SHA256 '+m['sha256']+'\n')
            f.write('\n')
        f.write('\n第二部分：上述关键模块的逐行原文（重复引用的模块只收录一次）\n\n')
        for m in modules.values():
            f.write('='*68+'\n'+m['path']+'\nSHA256 '+m['sha256']+'\n'+'='*68+'\n')
            for i,line in enumerate(m['source'].splitlines(),1):f.write(f'{i:5d} | {line}\n')
            f.write('\n')
    summary={'stages':len(stages),'distinct_modules':len(modules),'source_bytes':sum(m['bytes'] for m in modules.values()),'all_paths_read':True}
    (out/'export_review.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(summary,ensure_ascii=False))

if __name__=='__main__':main()
