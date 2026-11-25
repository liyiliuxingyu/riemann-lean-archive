# 局部证明与公开类型验证

本目录记录四个目标定理在简化前后的独立验证。四份测试模块均实际编译成功，四个目标的完整类型结构、宇宙参数及公理依赖均通过对照。验证使用下面列出的固定工具链和 Mathlib 依赖。

**验证范围是这些独立证明及其公开类型；完整工程构建未执行，`full_project_build = false`。** 复现需要已经准备好的对应 Mathlib 环境及编译缓存，四份测试源码本身不构成完整工程。

## 文件与固定版本

| 文件 | 用途 |
| --- | --- |
| [ContinuousMkQBaseline.lean](ContinuousMkQBaseline.lean) | `continuous_mkQ` 原证明的独立基线，保留原来的 `first` 分支。 |
| [ContinuousMkQStandalone.lean](ContinuousMkQStandalone.lean) | 以 `(Submodule.isQuotientMap_mkQ Mplus).continuous` 直接证明同一声明。 |
| [GammaFactorBaseline.lean](GammaFactorBaseline.lean) | 三个 Gamma 因子非零定理的原证明及公开类型检查。 |
| [GammaFactorStandalone.lean](GammaFactorStandalone.lean) | 共享 Gamma 引理与兼容声明的候选版本及公开类型检查。 |
| [ExportApiTypes.lean](ExportApiTypes.lean) | 从编译产物读取 `ConstantInfo.type`，导出完整表达式结构和宇宙参数。 |
| [topology_verification.json](topology_verification.json) | 连续商映射的实际编译记录、源码 SHA-256 和类型／公理比较结果。 |
| [gamma_verification.json](gamma_verification.json) | 三个 Gamma 定理的对应记录。 |

| 项目 | 固定值 |
| --- | --- |
| Lean toolchain | `leanprover/lean4:v4.33.1` |
| Lean commit | `819816b2e0a3bf405af45ae5c7af2491d8f5bee6` |
| Mathlib commit | `0df444a360eaa60ab8c11dca51a86af692955474` |
| Mathlib 的传递依赖 | 使用该提交的 `lake-manifest.json` 所固定的版本。 |

实际显式传入的编译选项为 `autoImplicit=false`、`relaxedAutoImplicit=false`、`maxSynthPendingDepth=3`。证明编译使用 `-M4096 -j2`；最终类型导出每次只处理一个模块，使用 `-M4096 -j1`。这些是本次独立检查的选项，不表示执行过原工程全部目标及其全部构建配置。

测试所需的 Mathlib 入口为：

- `Mathlib.Topology.Algebra.Module.Basic`
- `Mathlib.NumberTheory.LSeries.DirichletContinuation`
- `Mathlib.Tactic.Linarith`，供 Gamma 原证明的基线使用。

## 已通过的四项检查

| 目标声明 | 基线／候选编译 | 原始类型结构 | 去除绑定名卫生标识后的结构 | 宇宙参数／公理 |
| --- | --- | --- | --- | --- |
| `ReciprocityTheory.Gal.continuous_mkQ` | 均 exit 0 | 匿名实例绑定名含不同测试模块名 | 完全相同 | 完全相同 |
| `Formalism.VW.gammaFactor_ne_zero` | 均 exit 0 | 完全相同 | 完全相同 | 完全相同 |
| `Claim.gamma_ne_zero` | 均 exit 0 | 匿名 `NeZero` 绑定名含不同测试模块名 | 完全相同 | 完全相同 |
| `GlobalTheory.Mem.An.zsym_gammaFactor_ne_zero` | 均 exit 0 | 完全相同 | 完全相同 | 完全相同 |

四个定理前后的 `#print axioms` 集合均为 `{Classical.choice, Quot.sound, propext}`，没有 `sorryAx`。两个 JSON 报告的 `all_passed` 均为 `true`。连续商映射的基线编译还报告 `continuous_coinduced_rng` 分支不可达，说明原 `first` 成功使用的是 `continuous_quot_mk`。

## 类型比较方法与卫生标识边界

导出器读取实际 `.olean` 中的 `ConstantInfo.type`，输出 `Lean.Expr` 的完整构造器表示 `reprStr`，以及 `ConstantInfo.levelParams`。它每个进程只导入一个测试模块；公理依赖另外取自该模块成功编译时的 `#print axioms` 输出。

每条 JSONL 记录包含：

- `type_expr`：未经归一的完整表达式结构。
- `type_expr_bound_name_hygiene_erased`：仅对 `forallE`、`lam`、`letE` 的绑定变量名应用 `Name.eraseMacroScopes` 后的完整结构。
- `level_parameters`：完整宇宙参数表示。
- `is_theorem`：目标常量是否仍是定理。

独立模块中的匿名实例参数会带上各自的模块来源，例如 `ContinuousMkQBaseline` 与 `ContinuousMkQStandalone`。上述归一只删除这种绑定名的宏作用域标识，保留普通用户变量名；常量名、`BinderInfo`（包括隐式及实例参数类别）、全部类型节点、宇宙层级和 metadata 均保持原样。归一后的结构和宇宙参数按字符串严格相等比较。

因此，报告中 `type_expr_identical = false` 的两项并不表示假设或参数类型改变；应同时查看 `type_expr_same_after_binder_hygiene_erasure` 及其余检查字段。比较过程没有把常量名、实例参数类别或额外假设一并忽略。

## 在已准备好的依赖环境中复现

以下 Bash 命令从仓库根目录开始，复用 `project/lean/original` 中已经按上述固定版本准备好的 Lake 环境。运行前应确保三个 Mathlib 入口及其传递依赖的编译缓存可用，并让 Python 3 可执行。输出写入新建的临时目录；命令仅编译本目录的独立测试模块和导出类型。

```bash
set -euo pipefail
proof_repo_root="$(git rev-parse --show-toplevel)"
proof_tests_dir="$proof_repo_root/audits/lean_simplification_20261125/proof_tests"
proof_output_dir="$(mktemp -d "${TMPDIR:-/tmp}/lean-proof-tests.XXXXXXXX")"
cd "$proof_repo_root/project/lean/original"

lake env bash -s -- "$proof_tests_dir" "$proof_output_dir" <<'BASH'
set -euo pipefail
proof_tests_dir="$1"
proof_output_dir="$2"
export LEAN_PATH="$proof_output_dir${LEAN_PATH:+:$LEAN_PATH}"
lean --version

for proof_module in \
  ContinuousMkQBaseline ContinuousMkQStandalone \
  GammaFactorBaseline GammaFactorStandalone
do
  lean -M4096 -j2 \
    -DautoImplicit=false \
    -DrelaxedAutoImplicit=false \
    -DmaxSynthPendingDepth=3 \
    -R "$proof_tests_dir" \
    -o "$proof_output_dir/$proof_module.olean" \
    "$proof_tests_dir/$proof_module.lean" \
    > "$proof_output_dir/$proof_module.stdout.txt" \
    2> "$proof_output_dir/$proof_module.stderr.txt"
done

for proof_module in ContinuousMkQBaseline ContinuousMkQStandalone
do
  lean -M4096 -j1 -R "$proof_tests_dir" \
    --run "$proof_tests_dir/ExportApiTypes.lean" \
    "$proof_module" ReciprocityTheory.Gal.continuous_mkQ \
    > "$proof_output_dir/$proof_module.types.jsonl"
done

for proof_module in GammaFactorBaseline GammaFactorStandalone
do
  lean -M4096 -j1 -R "$proof_tests_dir" \
    --run "$proof_tests_dir/ExportApiTypes.lean" \
    "$proof_module" \
    Formalism.VW.gammaFactor_ne_zero \
    Claim.gamma_ne_zero \
    GlobalTheory.Mem.An.zsym_gammaFactor_ne_zero \
    > "$proof_output_dir/$proof_module.types.jsonl"
done
BASH

printf '验证输出目录：%s\n' "$proof_output_dir"
```

导出器的单模块接口为 `lean --run ExportApiTypes.lean MODULE DECLARATION...`；该模块的 `.olean` 必须位于 `LEAN_PATH` 中。上面的两组循环分别运行基线和候选，不会把两个大型导入环境同时保留在一个进程中。

在同一 shell 中继续执行下面的比较代码。它要求所有指定声明都有导出记录及真实的 `#print axioms` 输出，检查定理种类、完整归一类型、宇宙参数、公理集合相等，以及没有 `sorryAx`，并将结果写入输出目录的 `comparison.json`。

```bash
python3 - "$proof_output_dir" <<'PY'
from pathlib import Path
import json
import re
import sys

out = Path(sys.argv[1])
pairs = [
    ("ContinuousMkQBaseline", "ContinuousMkQStandalone",
     ["ReciprocityTheory.Gal.continuous_mkQ"]),
    ("GammaFactorBaseline", "GammaFactorStandalone",
     ["Formalism.VW.gammaFactor_ne_zero", "Claim.gamma_ne_zero",
      "GlobalTheory.Mem.An.zsym_gammaFactor_ne_zero"]),
]

def types(module):
    rows = [json.loads(line) for line in
            (out / f"{module}.types.jsonl").read_text().splitlines()]
    return {row["declaration"]: row for row in rows}

def axioms(module):
    result = {}
    for line in (out / f"{module}.stdout.txt").read_text().splitlines():
        match = re.fullmatch(r"'([^']+)' depends on axioms: \[(.*)\]", line)
        if match:
            result[match[1]] = sorted(
                name.strip() for name in match[2].split(",") if name.strip())
        match = re.fullmatch(r"'([^']+)' does not depend on any axioms", line)
        if match:
            result[match[1]] = []
    return result

results = []
for before_module, after_module, names in pairs:
    before, after = types(before_module), types(after_module)
    before_axioms, after_axioms = axioms(before_module), axioms(after_module)
    for name in names:
        b, a = before[name], after[name]
        checks = {
            "both_theorems": b["is_theorem"] and a["is_theorem"],
            "type_structure_equal": (
                b["type_expr_bound_name_hygiene_erased"] ==
                a["type_expr_bound_name_hygiene_erased"]),
            "universe_parameters_equal": (
                b["level_parameters"] == a["level_parameters"]),
            "axioms_equal": before_axioms[name] == after_axioms[name],
            "no_sorryAx": (
                "sorryAx" not in before_axioms[name] and
                "sorryAx" not in after_axioms[name]),
        }
        row = {
            "declaration": name,
            "raw_type_structure_equal": b["type_expr"] == a["type_expr"],
            "baseline_axioms": before_axioms[name],
            "candidate_axioms": after_axioms[name],
            **checks,
            "passed": all(checks.values()),
        }
        results.append(row)
        print(json.dumps(row, ensure_ascii=False))

(out / "comparison.json").write_text(
    json.dumps(results, ensure_ascii=False, indent=2) + "\n")
if not all(row["passed"] for row in results):
    raise SystemExit("局部证明／公开类型比较未全部通过")
PY
```

本目录的记录支持所列四个定理的局部简化。原工程其他模块的导入、实例与属性交互，以及全部默认构建目标能否一起通过，仍需完整工程构建另行确认。
